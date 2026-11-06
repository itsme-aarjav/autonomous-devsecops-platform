"""
Autonomous AIOps Platform — Production Agent Runtime Entrypoint

Runs the AIOps reasoning engine in a controlled stand-by daemon mode with:
- Internal HTTP health endpoints (/health/live, /health/ready)
- Alertmanager webhook receiver (POST /api/v1/alerts) with constant-time Bearer auth
- Bounded concurrency HTTP server (prevents thread-per-request exhaustion)
- Alertmanager v0.27.0 JSON payload validation and 1 MiB hard body limit
- Durable SQS FIFO alert queue (with in-memory fallback for local tests)
- Amazon DynamoDB episode deduplication and atomic lease lifecycle management
- Bedrock invocation safety switch (AIOPS_BEDROCK_ENABLED=false default)
- Graceful signal handling (SIGTERM, SIGINT)

DURABLE QUEUE & PERSISTENCE ARCHITECTURE (Stage 6.4.3):
- Alert intake pushes firing alerts to SQS FIFO before returning HTTP 202 Accepted.
- Dual-write prevention: resolved alerts are persisted to DynamoDB first; firing alerts
  are enqueued to SQS without creating a premature DynamoDB reservation.
- Workers poll SQS, atomically claim episodes in DynamoDB via conditional updates,
  maintain visibility heartbeats during investigation, and delete messages from SQS
  only after RCA report persistence is verified.
- Graph failures and error states from LangGraph are detected explicitly (not masked),
  failing the episode lease and allowing SQS redrive to DLQ after 3 receive attempts.
"""

import os
import sys
import time
import signal
import logging
import threading
from typing import Optional
from datetime import datetime, timezone

from .config import AgentConfig
from .schemas import alert_to_incident_input
from .adapters.factory import create_production_evidence_adapter
from .sanitization import EvidenceSanitizer
from .bedrock_client import BedrockConverseClient
from .persistence import (
    BasePersistenceAdapter,
    LocalFilePersistenceAdapter,
    DynamoDBPersistenceAdapter,
)
from .graph import create_aiops_graph
from .alert_queue import (
    BaseAlertQueue,
    InMemoryAlertQueue,
    SQSAlertQueue,
    QueueMessage,
)
from .episode_store import (
    BaseEpisodeStore,
    InMemoryEpisodeStore,
    DynamoDBEpisodeStore,
)
from .remediation import (
    BaseGitHubProvider,
    GitHubApiProvider,
    BaseRemediationStore,
    InMemoryRemediationStore,
    LocalFileRemediationStore,
    GitOpsRemediationEngine,
    RemediationPolicyEngine,
    ManifestPatchRenderer,
    TrustedTokenApprovalAuthenticator,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("aiops.runtime")


# Import and re-export HTTP Server & Health types for backward compatibility
from .health_server import (
    HealthServerState,
    WebhookBatch,
    BoundedThreadingHTTPServer,
    HealthRequestHandler,
    EpisodeLifecycleManager,
)



# AIOps Agent Runtime Manager
class AIOpsAgentRuntime:
    """Manages the lifecycle, component wiring, background worker, and health server."""

    def __init__(self, port: int = 8080, config: Optional[AgentConfig] = None):
        self.port = port
        self.config = config or AgentConfig()
        self.server_state = HealthServerState()
        self.server_state.model_id = self.config.bedrock_model_id
        self.server_state.webhook_enabled = self.config.webhook_enabled
        self.server_state.bedrock_enabled = self.config.bedrock_enabled
        self.server: Optional[BoundedThreadingHTTPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self.worker_thread: Optional[threading.Thread] = None
        self.dlq_reconciler_thread: Optional[threading.Thread] = None
        self.shutdown_event = threading.Event()
        self.graph = None

        # 1. Initialize Alert Queue
        self.alert_queue: BaseAlertQueue = self._init_alert_queue()
        self.worker_queue = self.alert_queue

        # 2. Initialize Episode Store & RCA Persistence
        self.episode_store, self.persistence_adapter = self._init_stores()
        self.episode_manager = self.episode_store

        # 3. Initialize Remediation Components (Stage 6.5)
        self.remediation_store, self.github_provider, self.remediation_engine = self._init_remediation()

    def _init_alert_queue(self) -> BaseAlertQueue:
        if self.config.queue_backend == "sqs":
            q_url = (self.config.sqs_queue_url or "").strip()
            d_url = (self.config.sqs_dlq_url or "").strip()
            q_name = (self.config.sqs_queue_name or "").strip()
            d_name = (self.config.sqs_dlq_name or "").strip()

            has_names = bool(q_name or d_name)
            if has_names and (q_url or d_url):
                raise ValueError(
                    "Ambiguous SQS queue configuration: both queue URLs and queue names were provided. "
                    "Specify either queue names (AIOPS_SQS_QUEUE_NAME, AIOPS_SQS_DLQ_NAME) or "
                    "queue URLs (AIOPS_SQS_QUEUE_URL, AIOPS_SQS_DLQ_URL), not both."
                )

            if has_names:
                if not q_name:
                    raise ValueError("AIOPS_QUEUE_BACKEND is set to 'sqs' but AIOPS_SQS_QUEUE_NAME is missing or empty")
                if not d_name:
                    raise ValueError("AIOPS_QUEUE_BACKEND is set to 'sqs' but AIOPS_SQS_DLQ_NAME is missing or empty")

                logger.info("Initializing durable SQS alert queue by queue names (%s, dlq: %s)...", q_name, d_name)
                return SQSAlertQueue(
                    queue_name=q_name,
                    dlq_name=d_name,
                    region_name=self.config.aws_region,
                    visibility_timeout_seconds=self.config.sqs_visibility_timeout_seconds,
                )

            if not q_url:
                raise ValueError("AIOPS_QUEUE_BACKEND is set to 'sqs' but AIOPS_SQS_QUEUE_URL is missing or empty")
            if not d_url:
                raise ValueError("AIOPS_QUEUE_BACKEND is set to 'sqs' but AIOPS_SQS_DLQ_URL is missing or empty")

            logger.info("Initializing durable SQS alert queue by explicit URLs (%s, dlq: %s)...", q_url, d_url)
            return SQSAlertQueue(
                queue_url=q_url,
                dlq_url=d_url,
                region_name=self.config.aws_region,
                visibility_timeout_seconds=self.config.sqs_visibility_timeout_seconds,
            )

        if self.config.queue_backend == "memory":
            logger.info("Initializing in-memory alert queue (capacity: %d)...", self.config.webhook_max_queue_size)
            return InMemoryAlertQueue(maxsize=self.config.webhook_max_queue_size)

        raise ValueError(f"Unsupported AIOPS_QUEUE_BACKEND: '{self.config.queue_backend}'. Must be 'sqs' or 'memory'")

    def _init_stores(self):
        if self.config.persistence_backend == "dynamodb":
            ep_table = (self.config.dynamodb_episodes_table or "").strip()
            rca_table = (self.config.dynamodb_rca_table or "").strip()
            if not ep_table:
                raise ValueError("AIOPS_PERSISTENCE_BACKEND is set to 'dynamodb' but AIOPS_DYNAMODB_EPISODES_TABLE is missing or empty")
            if not rca_table:
                raise ValueError("AIOPS_PERSISTENCE_BACKEND is set to 'dynamodb' but AIOPS_DYNAMODB_RCA_TABLE is missing or empty")

            logger.info("Initializing DynamoDB episode store (%s) and RCA adapter (%s)...", ep_table, rca_table)
            episode_store = DynamoDBEpisodeStore(
                table_name=ep_table,
                region_name=self.config.aws_region,
                ttl_seconds=self.config.episode_ttl_seconds,
            )
            persistence_adapter = DynamoDBPersistenceAdapter(
                table_name=rca_table,
                region_name=self.config.aws_region,
                ttl_seconds=self.config.rca_ttl_seconds,
            )
            return episode_store, persistence_adapter

        if self.config.persistence_backend == "memory":
            logger.info("Initializing in-memory episode store (TTL: %ds)...", self.config.webhook_dedup_ttl_seconds)
            episode_store = InMemoryEpisodeStore(ttl_seconds=self.config.webhook_dedup_ttl_seconds)
            persistence_adapter = LocalFilePersistenceAdapter()
            return episode_store, persistence_adapter

        raise ValueError(f"Unsupported AIOPS_PERSISTENCE_BACKEND: '{self.config.persistence_backend}'. Must be 'dynamodb' or 'memory'")

    def _init_remediation(self):
        # Remediation proposal persistence: DynamoDB when dynamodb backend is active, else in-memory.
        if self.config.persistence_backend == "dynamodb":
            from .remediation.store import DynamoDBRemediationStore
            remediations_table = os.getenv("AIOPS_DYNAMODB_REMEDIATIONS_TABLE", "").strip() or "boutique-aiops-remediations"
            store: BaseRemediationStore = DynamoDBRemediationStore(
                region=self.config.aws_region,
                table_name=remediations_table,
            )
            logger.info("Remediation store: DynamoDBRemediationStore (table: %s)", remediations_table)
        else:
            store = InMemoryRemediationStore()
            logger.info("Remediation store: InMemoryRemediationStore (local/test mode)")

        provider = None
        if self.config.github_token:
            provider = GitHubApiProvider(
                repository=self.config.github_repository,
                token=self.config.github_token,
                api_base_url=self.config.github_api_url,
            )

        # Wire approval authenticator from AIOPS_APPROVAL_TOKENS env var.
        # Format: "token1:operator_id1,token2:operator_id2"
        # Loaded from the aiops-approval-secret Kubernetes secret or CloudShell env — never from CLI args.
        approval_authenticator = None
        _raw_tokens = os.getenv("AIOPS_APPROVAL_TOKENS", "").strip()
        if _raw_tokens:
            authorized_operators: dict = {}
            for entry in _raw_tokens.split(","):
                parts = entry.strip().split(":", 1)
                if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                    authorized_operators[parts[0].strip()] = parts[1].strip()
            if authorized_operators:
                approval_authenticator = TrustedTokenApprovalAuthenticator(authorized_operators)
                logger.info(
                    "Approval authenticator configured with %d authorized operator(s).",
                    len(authorized_operators),
                )
            else:
                logger.warning(
                    "AIOPS_APPROVAL_TOKENS is set but contains no valid token:operator entries. "
                    "Approval authenticator will NOT be configured — apply_approved_remediation will fail closed."
                )
        else:
            logger.info(
                "AIOPS_APPROVAL_TOKENS not set. Approval authenticator not configured — "
                "apply_approved_remediation will fail closed until tokens are provisioned."
            )

        engine = None
        if self.config.remediation_enabled:
            engine = GitOpsRemediationEngine(
                repo_root=self.config.git_repo_root,
                policy_engine=RemediationPolicyEngine(min_confidence=self.config.remediation_min_confidence),
                renderer=ManifestPatchRenderer(repo_root=self.config.git_repo_root, github_provider=provider),
                github_provider=provider,
                store=store,
                approval_authenticator=approval_authenticator,
                min_confidence=self.config.remediation_min_confidence,
            )
        return store, provider, engine

    def start_health_server(self, start_worker: bool = False):
        """Starts the bounded multi-threaded health & webhook server."""
        # Inject dependencies into handler (for backwards-compat/tests)
        HealthRequestHandler.config = self.config
        HealthRequestHandler.alert_queue = self.alert_queue
        HealthRequestHandler.worker_queue = self.worker_queue
        HealthRequestHandler.episode_store = self.episode_store
        HealthRequestHandler.episode_manager = self.episode_manager
        HealthRequestHandler.state = self.server_state

        self.server = BoundedThreadingHTTPServer(
            ("0.0.0.0", self.port),
            HealthRequestHandler,
            max_concurrency=self.config.http_max_concurrency,
            request_timeout=self.config.http_request_timeout,
            server_state=self.server_state,
            config=self.config,
            alert_queue=self.alert_queue,
            episode_store=self.episode_store,
            worker_queue=self.worker_queue,
            episode_manager=self.episode_manager,
        )
        self.port = self.server.server_address[1]
        self.server_thread = threading.Thread(
            target=self.server.serve_forever, daemon=True, name="aiops-http-server"
        )
        self.server_thread.start()

        logger.info(
            "HTTP server listening on port %d (concurrency: %d, queue_backend: %s, persistence_backend: %s, webhook_enabled: %s, bedrock_enabled: %s)",
            self.port,
            self.config.http_max_concurrency,
            self.config.queue_backend,
            self.config.persistence_backend,
            self.config.webhook_enabled,
            self.config.bedrock_enabled,
        )

        if start_worker:
            self.start_worker()

    def start_dlq_reconciler(self) -> bool:
        """Starts the background DLQ reconciler thread."""
        if self.dlq_reconciler_thread and self.dlq_reconciler_thread.is_alive():
            return True
        self.dlq_reconciler_thread = threading.Thread(
            target=self._dlq_reconciler_loop, daemon=True, name="aiops-dlq-reconciler"
        )
        self.dlq_reconciler_thread.start()
        logger.info("AIOps DLQ reconciler thread started.")
        return True

    def start_worker(self) -> bool:
        """Starts the background investigation worker and DLQ reconciler threads only after initialization."""
        if not self.server_state.is_ready or not self.graph:
            logger.warning("Cannot start worker thread: LangGraph workflow not compiled or runtime not ready.")
            return False
        self.start_dlq_reconciler()
        if self.worker_thread and self.worker_thread.is_alive():
            return True
        self.worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="aiops-worker-thread"
        )
        self.worker_thread.start()
        logger.info("AIOps investigation worker thread started.")
        return True

    def initialize_components(self) -> bool:
        """Initializes production adapters, Bedrock client, and LangGraph workflow."""
        try:
            logger.info("Initializing Autonomous AIOps Agent production components...")
            self.server_state.model_id = self.config.bedrock_model_id
            self.server_state.webhook_enabled = self.config.webhook_enabled
            self.server_state.bedrock_enabled = self.config.bedrock_enabled

            if self.config.webhook_enabled and not (self.config.webhook_bearer_token or "").strip():
                raise ValueError(
                    "AIOPS_WEBHOOK_BEARER_TOKEN is required when AIOPS_WEBHOOK_ENABLED is true. "
                    "Fail-closed: refusing to activate webhook receiver without authentication secret."
                )

            # 1. Build production composite adapter (STRICTLY NO MOCK ADAPTER)
            logger.info("Initializing production telemetry adapters (Kubernetes & Prometheus)...")
            evidence_adapter = create_production_evidence_adapter(self.config)

            # 2. Evidence sanitizer
            sanitizer = EvidenceSanitizer(
                max_log_lines=self.config.max_log_lines,
                max_log_bytes=self.config.max_log_bytes,
            )

            # 3. Bedrock client with EKS Pod Identity / default credential chain
            logger.info("Initializing Bedrock Converse client (Model: %s)...", self.config.bedrock_model_id)
            bedrock_client = BedrockConverseClient(config=self.config)

            # 4. Compile LangGraph workflow
            logger.info("Compiling LangGraph StateGraph pipeline...")
            self.graph = create_aiops_graph(
                config=self.config,
                evidence_adapter=evidence_adapter,
                bedrock_client=bedrock_client,
                sanitizer=sanitizer,
                persistence_adapter=self.persistence_adapter,
                episode_store=self.episode_store,
                remediation_engine=self.remediation_engine,
            )

            # Mark ready
            self.server_state.is_ready = True
            self.server_state.init_error = None
            self.server_state.initialized_at = datetime.now(timezone.utc).isoformat()
            logger.info("Autonomous AIOps Agent initialization COMPLETE. Ready for controlled operations.")
            return True

        except Exception as e:
            err_msg = f"Runtime initialization failed: {str(e)}"
            logger.error(err_msg, exc_info=True)
            self.server_state.init_error = err_msg
            self.server_state.is_ready = False
            self.graph = None
            return False

    def reconcile_dlq_once(self) -> Optional[str]:
        """
        Single DLQ reconciliation pass:
        1. Receives a message from the DLQ (with visibility timeout to avoid tight polling).
        2. Reconciles the DynamoDB episode state to 'dead_lettered' via atomic conditional update.
        3. NEVER deletes the DLQ message (preserves it intact for operator inspection and re-drive).
        4. Does NOT invoke Bedrock or perform any Kubernetes mutations.
        Returns episode_id if reconciled, or None.
        """
        try:
            poll_wait = 1 if self.config.queue_backend == "memory" else 10
            message = self.alert_queue.receive_dlq_alert(
                wait_time_seconds=poll_wait,
                visibility_timeout=self.config.sqs_visibility_timeout_seconds,
            )
        except Exception as e:
            logger.error("Error receiving message from DLQ during reconciliation: %s", str(e))
            return None

        if message is None:
            return None

        ep_id = message.episode_id
        err_msg = f"Reconciled from SQS DLQ (receive_count: {message.receive_count})"
        logger.info("DLQ reconciler inspecting episode %s from DLQ (receive_count: %d)", ep_id, message.receive_count)

        try:
            reconciled = self.episode_store.reconcile_dead_lettered(ep_id, error_message=err_msg)
            if reconciled:
                logger.info("Successfully reconciled episode %s to dead_lettered from DLQ", ep_id)
            else:
                logger.info("Episode %s from DLQ skipped (not eligible or already terminal)", ep_id)
        except Exception as e:
            logger.error("Error during DLQ reconciliation for episode %s: %s", ep_id, str(e))

        # CRITICAL INVARIANT: DO NOT DELETE DLQ MESSAGE!
        # DLQ messages are preserved intact for manual operator triage and redrive.
        return ep_id

    def _dlq_reconciler_loop(self):
        """
        Background DLQ reconciliation loop:
        Periodically checks the dead-letter queue and reconciles episode states
        for abruptly terminated worker processes.
        Active and safe during controlled standby (even when Bedrock is disabled).
        """
        logger.info("AIOps DLQ reconciliation thread started.")
        interval = 0.5 if self.config.queue_backend == "memory" else 15.0
        while not self.shutdown_event.is_set():
            try:
                self.reconcile_dlq_once()
            except Exception as e:
                logger.error("Unexpected error in DLQ reconciliation loop: %s", str(e))
            self.shutdown_event.wait(interval)
        logger.info("AIOps DLQ reconciliation thread exited.")

    def _worker_loop(self):
        """
        Background worker loop: consumes alert messages sequentially from alert queue.
        Executes single investigation at a time to prevent resource contention.
        """
        worker_id = f"worker-{os.getpid()}-{threading.get_ident()}"
        while not self.shutdown_event.is_set():
            # Invariant: do not poll or process queue before LangGraph workflow is ready
            if not self.server_state.is_ready or not self.graph:
                time.sleep(0.5)
                continue

            # Invariant: in durable SQS mode, do not consume messages while Bedrock is disabled (controlled standby)
            if self.config.queue_backend == "sqs" and not self.config.bedrock_enabled:
                time.sleep(1.0)
                continue

            try:
                poll_wait = 1 if self.config.queue_backend == "memory" else self.config.worker_poll_wait_seconds
                message = self.alert_queue.receive_alert(
                    wait_time_seconds=poll_wait,
                    visibility_timeout=self.config.sqs_visibility_timeout_seconds,
                )
            except Exception as e:
                logger.error("Error receiving alert from queue: %s", str(e))
                time.sleep(1.0)
                continue

            if message is None:
                continue

            try:
                self.server_state.active_worker_busy = True
                self._process_webhook_batch(message)
            except Exception as e:
                logger.error("Error processing queue message %s: %s", message.message_id, str(e), exc_info=True)
            finally:
                self.server_state.active_worker_busy = False

    def _process_webhook_batch(self, message_or_batch):
        """Worker dispatch method supporting both QueueMessage and WebhookBatch."""
        worker_id = f"worker-{os.getpid()}-{threading.get_ident()}"
        if isinstance(message_or_batch, QueueMessage):
            self._process_queue_message(message_or_batch, worker_id)
        elif hasattr(message_or_batch, "new_alerts"):
            for ep_id, alert in message_or_batch.new_alerts:
                msg = QueueMessage(
                    message_id=f"batch-msg-{ep_id[:8]}",
                    receipt_handle=f"batch-rcpt-{ep_id[:8]}",
                    body={},
                    receive_count=1,
                    episode_id=ep_id,
                    alert=alert,
                    cluster_identity=message_or_batch.cluster_identity,
                    truncated_alerts=message_or_batch.truncated_alerts,
                )
                self._process_queue_message(msg, worker_id)

    def _record_episode_failure(self, ep_id: str, worker_id: str, receipt: str, receive_count: int, err_msg: str):
        if receive_count >= 3:
            logger.error("Episode %s reached max receive count (%d). Marking dead-lettered.", ep_id, receive_count)
            self.episode_store.mark_dead_lettered(ep_id, worker_id, err_msg)
            if self.config.queue_backend == "memory":
                self.alert_queue.delete_alert(receipt)
        else:
            self.episode_store.fail_episode(ep_id, worker_id, err_msg)

    def _process_queue_message(self, message: QueueMessage, worker_id: str):
        """
        Processes a single dequeued alert message:
        1. Checks if alert was already resolved (cancels investigation without Bedrock).
        2. Atomically claims episode in episode store.
        3. Spawns heartbeat thread to extend visibility timeout and renew lease.
        4. Enforces Bedrock safety switch.
        5. Executes LangGraph pipeline and detects errors explicitly.
        6. Persists RCA report and deletes message from queue only after persistence.
        """
        ep_id = message.episode_id
        alert = message.alert
        receipt = message.receipt_handle
        cluster_id = message.cluster_identity
        truncated = message.truncated_alerts

        # 0. Invariant: in durable SQS mode, do not consume or delete messages while Bedrock is disabled (controlled standby)
        if self.config.queue_backend == "sqs" and not self.config.bedrock_enabled:
            logger.info(
                "Controlled standby mode (AIOPS_BEDROCK_ENABLED=false with queue_backend=sqs): "
                "Preserving SQS message for episode %s untouched in durable queue.",
                ep_id,
            )
            return

        # 1. Pre-check: Check if alert resolved before processing
        if self.episode_store.is_episode_resolved(ep_id):
            logger.info("Episode %s was already marked resolved. Cancelling investigation.", ep_id)
            self.episode_store.mark_resolved_cancelled(ep_id)
            self.alert_queue.delete_alert(receipt)
            return

        # 2. Atomic episode claim in episode store
        claimed, ep_data, reason = self.episode_store.claim_episode(
            episode_id=ep_id,
            alert=alert,
            worker_id=worker_id,
            lease_duration=self.config.worker_lease_duration_seconds,
            cluster_identity=cluster_id,
        )

        if not claimed:
            if reason in ("resolved", "completed"):
                logger.info("Episode %s is already %s. Acknowledging queue message.", ep_id, reason)
                self.alert_queue.delete_alert(receipt)
            else:
                logger.warning("Episode %s could not be claimed (reason: %s). Leaving in queue for retry.", ep_id, reason)
            return

        # 3. Start background visibility and lease heartbeat thread
        stop_heartbeat = threading.Event()
        lease_lost = threading.Event()

        def heartbeat_worker():
            interval = max(0.01, float(self.config.worker_heartbeat_interval_seconds))
            while not stop_heartbeat.wait(interval):
                try:
                    logger.debug("Extending lease and visibility for episode %s", ep_id)
                    renewed = self.episode_store.renew_lease(
                        ep_id, worker_id, self.config.worker_lease_duration_seconds
                    )
                    if not renewed:
                        logger.warning("Lease renewal failed for %s (worker: %s). Lease lost!", ep_id, worker_id)
                        lease_lost.set()
                        break
                    vis_extended = self.alert_queue.change_visibility(
                        receipt, self.config.sqs_visibility_timeout_seconds
                    )
                    if not vis_extended:
                        logger.warning("Visibility extension failed for %s. Lease lost!", ep_id)
                        lease_lost.set()
                        break
                except Exception as hb_err:
                    logger.warning("Heartbeat renewal failed for %s: %s", ep_id, str(hb_err))
                    lease_lost.set()
                    break

        hb_thread = threading.Thread(target=heartbeat_worker, daemon=True, name=f"aiops-hb-{ep_id[:8]}")
        hb_thread.start()

        try:
            # 4. Check Bedrock safety switch
            if not self.config.bedrock_enabled:
                logger.info(
                    "Bedrock execution disabled by policy (AIOPS_BEDROCK_ENABLED=false). "
                    "Diagnostic intake recorded for episode %s.",
                    ep_id,
                )
                if lease_lost.is_set():
                    logger.warning("Worker %s lost lease for %s during standby intake. Skipping ack.", worker_id, ep_id)
                    return
                self.episode_store.record_model_disabled(ep_id, worker_id=worker_id)
                self.alert_queue.delete_alert(receipt)
                return

            # Pre-inference resolution check: cancel if resolved while in-flight
            if self.episode_store.is_episode_resolved(ep_id):
                logger.info("Episode %s resolved prior to analysis. Cancelling and acknowledging message.", ep_id)
                self.episode_store.mark_resolved_cancelled(ep_id, worker_id=worker_id)
                if not lease_lost.is_set():
                    self.alert_queue.delete_alert(receipt)
                return

            # 5. Execute LangGraph diagnostic workflow
            incident_input = alert_to_incident_input(
                alert=alert,
                cluster_identity=cluster_id,
                is_truncated=(truncated > 0),
                truncated_count=truncated,
            )

            if not self.graph:
                raise RuntimeError("LangGraph workflow is not compiled")

            logger.info("Executing LangGraph diagnostic pipeline for episode %s...", ep_id)
            result = self.graph.invoke({
                "raw_incident": incident_input.model_dump(),
                "incident_id": ep_id,
            })

            # Check if episode was resolved mid-investigation (or returned resolved_cancelled)
            if result.get("status") == "resolved_cancelled" or self.episode_store.is_episode_resolved(ep_id):
                logger.info("Episode %s resolved during investigation. Cancelling and acknowledging message.", ep_id)
                self.episode_store.mark_resolved_cancelled(ep_id, worker_id=worker_id)
                if not lease_lost.is_set():
                    self.alert_queue.delete_alert(receipt)
                return

            # 6. LangGraph Error Inspection (Fixing the error-masking bug)
            is_failed = (
                result.get("status") == "failed"
                or bool(result.get("errors"))
                or not result.get("root_cause_analysis")
            )

            if is_failed:
                err_msg = "; ".join(result.get("errors") or ["Diagnostic workflow failed"])
                logger.error("LangGraph pipeline failed for episode %s: %s", ep_id, err_msg)
                if not lease_lost.is_set():
                    self._record_episode_failure(ep_id, worker_id, receipt, message.receive_count, err_msg)
                else:
                    logger.warning("Worker %s lost lease for %s; aborting failure state update.", worker_id, ep_id)
                return

            # 7. Success Path: Verify lease before completion, complete episode, then delete message
            if lease_lost.is_set():
                logger.warning(
                    "Worker %s lost lease for episode %s during investigation. Aborting completion and message deletion.",
                    worker_id,
                    ep_id,
                )
                return

            completed = self.episode_store.complete_episode(ep_id, worker_id)
            if not completed:
                logger.error(
                    "Failed to mark episode %s completed by worker %s (lease lost or concurrent modification). NOT deleting SQS message.",
                    ep_id,
                    worker_id,
                )
                return

            logger.info("Investigation succeeded for episode %s. Acknowledging message.", ep_id)
            self.alert_queue.delete_alert(receipt)

        except Exception as proc_err:
            logger.error("Unhandled exception during episode %s processing: %s", ep_id, str(proc_err), exc_info=True)
            if not lease_lost.is_set():
                self._record_episode_failure(ep_id, worker_id, receipt, message.receive_count, str(proc_err))
        finally:
            stop_heartbeat.set()
            hb_thread.join(timeout=1.0)

    def shutdown(self):
        """Gracefully shuts down health server and worker queue."""
        self.shutdown_event.set()
        self.server_state.is_alive = False
        self.server_state.is_ready = False
        HealthRequestHandler.state.is_alive = False
        HealthRequestHandler.state.is_ready = False
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)
        if self.dlq_reconciler_thread and self.dlq_reconciler_thread.is_alive():
            self.dlq_reconciler_thread.join(timeout=2.0)

    def run(self):
        """Main process loop with signal handling."""
        self.start_health_server(start_worker=False)
        if self.initialize_components():
            self.start_worker()
        else:
            logger.error("AIOps Agent initialization failed. Worker thread will NOT be started.")

        def signal_handler(signum, frame):
            sig_name = signal.Signals(signum).name
            logger.info("Received termination signal %s. Initiating graceful shutdown...", sig_name)
            self.shutdown()

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        logger.info("AIOps Agent runtime active in standby mode (PID: %d). Awaiting signals.", os.getpid())
        self.shutdown_event.wait()
        logger.info("AIOps Agent runtime exited cleanly.")
        sys.exit(0)


if __name__ == "__main__":
    port = int(os.getenv("AIOPS_HEALTH_PORT", "8080"))
    runtime = AIOpsAgentRuntime(port=port)
    runtime.run()
