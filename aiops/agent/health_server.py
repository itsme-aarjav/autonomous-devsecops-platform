"""
Autonomous AIOps Platform — Health & Webhook HTTP Server

Provides bounded, authenticated HTTP endpoints for:
- /healthz (liveness probe)
- /readyz, /health/ready (readiness probe)
- /metrics (Prometheus telemetry export)
- /webhook/alerts (Alertmanager v4 alert ingestion)
"""

import json
import time
import hmac
import queue
import logging
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Optional, Any, List, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, field

from .config import AgentConfig
from .schemas import (
    AlertStatus,
    AlertItem,
    AlertmanagerWebhookPayload,
)
from .alert_queue import BaseAlertQueue
from .episode_store import (
    BaseEpisodeStore,
    InMemoryEpisodeStore,
)

logger = logging.getLogger("aiops.runtime")

# Server State & Backward-Compatibility Types
class HealthServerState:
    """Shared state for runtime health, readiness, and webhook metrics."""

    def __init__(self):
        self.is_alive: bool = True
        self.is_ready: bool = False
        self.started_at: str = datetime.now(timezone.utc).isoformat()
        self.initialized_at: Optional[str] = None
        self.model_id: Optional[str] = None
        self.init_error: Optional[str] = None
        self.webhook_enabled: bool = False
        self.bedrock_enabled: bool = False
        self.active_worker_busy: bool = False
        self.accepted_batches_count: int = 0
        self.deduplicated_alerts_count: int = 0
        self.resolved_alerts_count: int = 0


# Backwards-compatibility alias for test suites
EpisodeLifecycleManager = InMemoryEpisodeStore


@dataclass
class WebhookBatch:
    """Represents a validated batch of alerts enqueued for sequential worker processing."""

    payload: AlertmanagerWebhookPayload
    new_alerts: List[Tuple[str, AlertItem]]  # [(episode_id, alert)]
    truncated_alerts: int
    cluster_identity: str
    enqueued_at: float = field(default_factory=time.time)


# Bounded Concurrency HTTP Server
class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """
    Multi-threaded HTTP server with bounded concurrency and socket timeouts.
    Guarantees health probes are non-blocking while preventing thread exhaustion attacks.
    """

    daemon_threads = True

    def __init__(
        self,
        server_address,
        RequestHandlerClass,
        max_concurrency: int = 16,
        request_timeout: float = 10.0,
        server_state: Optional[HealthServerState] = None,
        config: Optional[AgentConfig] = None,
        alert_queue: Optional[BaseAlertQueue] = None,
        episode_store: Optional[BaseEpisodeStore] = None,
        worker_queue: Optional[Any] = None,
        episode_manager: Optional[Any] = None,
    ):
        self.max_concurrency = max_concurrency
        self.request_timeout = request_timeout
        self.server_state = server_state or HealthServerState()
        self.config = config
        self.alert_queue = alert_queue or worker_queue
        self.episode_store = episode_store or episode_manager
        # Backward-compatibility attributes
        self.worker_queue = self.alert_queue
        self.episode_manager = self.episode_store
        self._concurrency_semaphore = threading.BoundedSemaphore(max_concurrency)
        super().__init__(server_address, RequestHandlerClass)

    def process_request(self, request, client_address):
        """Processes request in a new daemon thread, bounded by semaphore."""
        acquired = self._concurrency_semaphore.acquire(blocking=False)
        if not acquired:
            try:
                request.settimeout(2.0)
                body = b'{"status":"error","message":"Server concurrency limit reached"}'
                response = (
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n"
                    b"Connection: close\r\n\r\n" + body
                )
                request.sendall(response)
            except Exception:
                pass
            finally:
                self.shutdown_request(request)
            return

        def run_bounded():
            try:
                request.settimeout(self.request_timeout)
                self.finish_request(request, client_address)
            except Exception:
                self.handle_error(request, client_address)
            finally:
                try:
                    self.shutdown_request(request)
                finally:
                    self._concurrency_semaphore.release()

        t = threading.Thread(target=run_bounded, daemon=True, name="aiops-http-worker")
        t.start()


# HTTP Request Handler
class HealthRequestHandler(BaseHTTPRequestHandler):
    """
    HTTP handler for:
    - Kubernetes liveness & readiness probes (GET /health/live, GET /health/ready)
    - Prometheus Alertmanager webhook intake (POST /api/v1/alerts)
    """

    # Shared class-level references (fallback / testing)
    state: HealthServerState = HealthServerState()
    config: Optional[AgentConfig] = None
    alert_queue: Optional[BaseAlertQueue] = None
    episode_store: Optional[BaseEpisodeStore] = None
    worker_queue: Optional[Any] = None
    episode_manager: Optional[Any] = None

    @property
    def server_state(self) -> HealthServerState:
        return getattr(self.server, "server_state", None) or HealthRequestHandler.state

    @property
    def runtime_config(self) -> AgentConfig:
        return getattr(self.server, "config", None) or HealthRequestHandler.config or AgentConfig()

    @property
    def active_queue(self) -> Optional[BaseAlertQueue]:
        return (
            getattr(self.server, "alert_queue", None)
            or getattr(self.server, "worker_queue", None)
            or HealthRequestHandler.alert_queue
            or HealthRequestHandler.worker_queue
        )

    @property
    def active_episode_store(self) -> BaseEpisodeStore:
        return (
            getattr(self.server, "episode_store", None)
            or getattr(self.server, "episode_manager", None)
            or HealthRequestHandler.episode_store
            or HealthRequestHandler.episode_manager
            or InMemoryEpisodeStore()
        )

    def _send_405(self, allow: str, message: str = "Method Not Allowed"):
        self.send_response(405)
        self.send_header("Allow", allow)
        self._send_json_response(405, {"status": "error", "message": message}, add_headers=False)

    def do_GET(self):
        """Handles GET requests: health probes and method rejection."""
        st = self.server_state
        if self.path == "/health/live":
            status = 200 if st.is_alive else 503
            body = {
                "status": "alive" if st.is_alive else "terminating",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "started_at": st.started_at,
            } if st.is_alive else {"status": "terminating"}
            self._send_json_response(status, body)

        elif self.path == "/health/ready":
            if st.is_ready:
                self._send_json_response(200, {
                    "status": "ready",
                    "initialized": True,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "initialized_at": st.initialized_at,
                    "model_id": st.model_id,
                    "webhook_enabled": st.webhook_enabled,
                    "bedrock_enabled": st.bedrock_enabled,
                })
            else:
                self._send_json_response(503, {
                    "status": "not_ready",
                    "initialized": False,
                    "error": st.init_error or "Initialization in progress",
                })

        elif self.path == "/api/v1/alerts":
            self._send_405("POST", "Method Not Allowed. Use POST for webhook ingestion.")

        else:
            self._send_json_response(404, {"error": "Not Found"})

    def do_POST(self):
        """Handles POST requests: Alertmanager webhook ingestion."""
        if self.path == "/api/v1/alerts":
            self._handle_alerts_webhook()
        elif self.path in ("/health/live", "/health/ready"):
            self._send_405("GET", "Method Not Allowed. Use GET for health endpoints.")
        else:
            self._send_json_response(404, {"error": "Not Found"})

    def do_PUT(self):
        self._send_405("GET, POST")

    def do_DELETE(self):
        self._send_405("GET, POST")

    def do_PATCH(self):
        self._send_405("GET, POST")

    # --------------------------------------------------------------------------
    # Alertmanager Webhook Ingestion Logic
    # --------------------------------------------------------------------------
    def _handle_alerts_webhook(self):
        """
        Validates, authenticates, deduplicates, and enqueues Alertmanager notifications.
        Enforces:
        - Standby feature disable check (503)
        - Constant-time Bearer token check BEFORE reading body (401)
        - Content-Type: application/json (415)
        - Unsupported Transfer-Encoding rejection (400)
        - Streaming 1 MiB body size limit (413 / 400)
        - Pydantic v2 Alertmanager v4 validation (400)
        - Resolved state handling persisted directly to store (200)
        - Deduplication check against active episodes (200)
        - Bounded worker queue capacity check (429 backpressure)
        - SQS FIFO durable delivery before HTTP 202
        - DUAL-WRITE PREVENTION: Never create a pending reservation before queue send!
        """
        st = self.server_state
        cfg = self.runtime_config
        q = self.active_queue
        store = self.active_episode_store

        # 1. Feature disabled check
        if not st.webhook_enabled:
            self._send_json_response(503, {
                "status": "error",
                "message": "AIOps webhook receiver is currently disabled (controlled standby mode).",
            })
            return

        # 2. Runtime liveness check
        if not st.is_alive:
            self._send_json_response(503, {
                "status": "error",
                "message": "AIOps runtime is shutting down.",
            })
            return

        # 3. Authenticate Bearer token BEFORE reading or allocating memory for body
        auth_header = self.headers.get("Authorization", "")
        if not self._authenticate_bearer_token(auth_header, cfg):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Bearer realm="AIOps Alertmanager Webhook"')
            self._send_json_response(401, {
                "status": "error",
                "message": "Unauthorized: Missing or invalid Bearer token.",
            }, add_headers=False)
            return

        # 4. Media Type check
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("application/json"):
            self._send_json_response(415, {
                "status": "error",
                "message": f"Unsupported Media Type: expected 'application/json', got '{content_type}'",
            })
            return

        # 5. Transfer-Encoding check
        transfer_encoding = self.headers.get("Transfer-Encoding")
        if transfer_encoding:
            self._send_json_response(400, {
                "status": "error",
                "message": f"Unsupported Transfer-Encoding '{transfer_encoding}'. Explicit Content-Length required.",
            })
            return

        # 6. Read and enforce streaming body size limit (max 1 MiB)
        max_bytes = cfg.webhook_max_payload_bytes if cfg else (1024 * 1024)
        raw_body, err_code, err_msg = self._read_request_body_bounded(max_bytes=max_bytes)
        if err_code:
            self._send_json_response(err_code, {"status": "error", "message": err_msg})
            return

        # 7. Parse JSON body
        try:
            payload_data = json.loads(raw_body.decode("utf-8"))
        except Exception as e:
            self._send_json_response(400, {
                "status": "error",
                "message": f"Malformed JSON payload: {str(e)}",
            })
            return

        # 8. Validate Alertmanager v4 JSON schema via Pydantic v2
        try:
            payload = AlertmanagerWebhookPayload.model_validate(payload_data)
        except Exception as e:
            self._send_json_response(400, {
                "status": "error",
                "message": f"Alertmanager payload schema validation failed: {str(e)}",
            })
            return

        cluster_id = cfg.cluster_identity if cfg else "boutique-dev-eks"

        # 9. Handle resolved alerts (Persist directly to episode store before handling firing)
        firing_alerts = [a for a in payload.alerts if a.status == AlertStatus.FIRING]
        resolved_alerts = [a for a in payload.alerts if a.status == AlertStatus.RESOLVED]

        resolved_count = 0
        for res_alert in resolved_alerts:
            ep_id = BaseEpisodeStore.calculate_episode_id(cluster_id, res_alert.fingerprint, res_alert.startsAt)
            store.record_resolved_episode(ep_id, res_alert)
            resolved_count += 1

        st.resolved_alerts_count += resolved_count

        if not firing_alerts:
            # Batch contains only resolved alerts; never trigger Bedrock
            self._send_json_response(200, {
                "status": "ok",
                "message": "Resolved alerts updated. No investigation triggered.",
                "resolved_count": resolved_count,
            })
            return

        # 10. Evaluate firing alerts against episode store deduplication
        new_firing_alerts: List[Tuple[str, AlertItem]] = []
        dedup_count = 0
        for alert in firing_alerts:
            ep_id = BaseEpisodeStore.calculate_episode_id(cluster_id, alert.fingerprint, alert.startsAt)
            if store.is_episode_resolved(ep_id):
                # Alert has already been resolved; ignore
                resolved_count += 1
            elif store.is_episode_active(ep_id):
                dedup_count += 1
            else:
                new_firing_alerts.append((ep_id, alert))

        st.deduplicated_alerts_count += dedup_count

        if not new_firing_alerts:
            # All firing alerts in this notification are duplicates of active episodes or already resolved
            self._send_json_response(200, {
                "status": "ok",
                "message": "All alerts in batch are duplicates of active episodes or already resolved.",
                "deduplicated_count": dedup_count,
                "resolved_count": resolved_count,
            })
            return

        # 11. Bounded Worker Queue Capacity Check & Enqueue
        # CRITICAL SAFETY & DUAL-WRITE PREVENTION:
        # Do NOT reserve episode IDs before successful queue insertion!
        if q is None:
            self._send_json_response(503, {
                "status": "error",
                "message": "Worker queue not initialized.",
            })
            return

        queued_episodes: List[str] = []
        try:
            for ep_id, alert in new_firing_alerts:
                q.send_alert(
                    episode_id=ep_id,
                    alert=alert,
                    cluster_identity=cluster_id,
                    truncated_alerts=payload.truncatedAlerts,
                )
                queued_episodes.append(ep_id)
        except queue.Full:
            # Bounded queue is full: apply backpressure (HTTP 429) for Alertmanager retry
            # DO NOT reserve episode IDs in episode store!
            logger.warning(
                "Worker queue capacity (%s) reached. Returning HTTP 429 backpressure.",
                getattr(q, "maxsize", "bounded"),
            )
            self._send_json_response(429, {
                "status": "error",
                "message": "Worker queue is full. Backpressure applied for Alertmanager retry.",
            })
            return
        except Exception as e:
            # Durable queue (SQS) error: return 503 so Alertmanager will retry
            # DO NOT reserve episode IDs in episode store!
            logger.error("Failed to enqueue alert to durable queue: %s", str(e), exc_info=True)
            self._send_json_response(503, {
                "status": "error",
                "message": "Failed to enqueue alert to durable queue. Alertmanager will retry.",
            })
            return

        # 12. Only AFTER successful enqueue: record accepted episode IDs
        for ep_id, alert in new_firing_alerts:
            if hasattr(store, "record_accepted_episode"):
                store.record_accepted_episode(
                    ep_id=ep_id,
                    fingerprint=alert.fingerprint,
                    starts_at=alert.startsAt.isoformat(),
                    alert_name=alert.labels.get("alertname", "unknown"),
                    workload=alert.labels.get("workload") or alert.labels.get("pod") or "unknown",
                    namespace=alert.labels.get("namespace", "boutique"),
                    is_truncated=(payload.truncatedAlerts > 0),
                    truncated_count=payload.truncatedAlerts,
                )

        st.accepted_batches_count += 1

        logger.info(
            "Accepted alert batch: %d new episodes enqueued, %d deduplicated, %d resolved. "
            "Queue depth: %d.",
            len(new_firing_alerts),
            dedup_count,
            resolved_count,
            q.approximate_size(),
        )

        # 13. Acknowledge with HTTP 202 Accepted
        delivery_mode = "durable-sqs-fifo" if cfg.queue_backend == "sqs" else "non-durable-in-memory-prototype"
        self._send_json_response(202, {
            "status": "accepted",
            "message": "Alert batch accepted for background investigation.",
            "queued_episodes": queued_episodes,
            "deduplicated_count": dedup_count,
            "resolved_count": resolved_count,
            "delivery": delivery_mode,
        })

    def _authenticate_bearer_token(self, auth_header: str, config: Optional[AgentConfig]) -> bool:
        """Constant-time Bearer token authentication."""
        cfg = config or self.runtime_config
        if not cfg or not cfg.webhook_bearer_token:
            return False
        if not auth_header:
            return False
        parts = auth_header.strip().split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return False
        provided = parts[1].strip()
        expected = cfg.webhook_bearer_token.strip()
        return hmac.compare_digest(provided, expected)

    def _read_request_body_bounded(self, max_bytes: int) -> Tuple[Optional[bytes], Optional[int], Optional[str]]:
        """
        Reads request body in streaming chunks up to max_bytes.
        Returns: (body_bytes, error_status_code, error_message).
        """
        raw_len = self.headers.get("Content-Length")
        if raw_len is None:
            return None, 400, "Missing Content-Length header."
        try:
            content_length = int(raw_len)
        except ValueError:
            return None, 400, "Invalid Content-Length header."

        if content_length < 0:
            return None, 400, "Negative Content-Length header."
        if content_length > max_bytes:
            return None, 413, f"Request body exceeds maximum allowed limit of {max_bytes} bytes."

        bytes_read = 0
        chunks: List[bytes] = []
        chunk_size = 65536

        while bytes_read < content_length:
            to_read = min(chunk_size, content_length - bytes_read)
            chunk = self.rfile.read(to_read)
            if not chunk:
                return None, 400, "Unexpected EOF while reading request body."
            chunks.append(chunk)
            bytes_read += len(chunk)
            if bytes_read > max_bytes:
                return None, 413, f"Request body exceeded maximum allowed limit of {max_bytes} bytes."

        return b"".join(chunks), None, None

    def _send_json_response(self, status_code: int, data: dict, add_headers: bool = True):
        """Sends a JSON response with Content-Type and Content-Length."""
        body = json.dumps(data).encode("utf-8")
        if add_headers:
            self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Suppress noisy probe access logs; sanitize any logged request lines
        if self.path in ("/health/live", "/health/ready"):
            return
        logger.info("%s - %s", self.address_string(), format % args)
