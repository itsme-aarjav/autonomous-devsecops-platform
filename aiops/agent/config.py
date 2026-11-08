"""
Autonomous AIOps Platform — Configuration Settings
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentConfig:
    """Configurable settings for the Autonomous AIOps Agent."""

    # AWS & Bedrock Configuration
    # Model ID reconciled with boutique-dev-eks-aiops-agent-role IAM authorization policy
    aws_region: str = os.getenv("AWS_REGION", "us-east-2")
    bedrock_model_id: str = os.getenv(
        "AIOPS_BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"
    )
    bedrock_max_tokens: int = int(os.getenv("AIOPS_BEDROCK_MAX_TOKENS", "2048"))
    bedrock_temperature: float = float(os.getenv("AIOPS_BEDROCK_TEMPERATURE", "0.0"))
    bedrock_timeout_seconds: int = int(os.getenv("AIOPS_BEDROCK_TIMEOUT_SECONDS", "30"))
    bedrock_max_retries: int = int(os.getenv("AIOPS_BEDROCK_MAX_RETRIES", "3"))

    # Evidence & Sanitization Limits
    max_log_lines: int = int(os.getenv("AIOPS_MAX_LOG_LINES", "300"))
    max_log_bytes: int = int(os.getenv("AIOPS_MAX_LOG_BYTES", "65536"))
    max_events_count: int = int(os.getenv("AIOPS_MAX_EVENTS_COUNT", "50"))

    # Kubernetes Adapter Configuration (Read-Only)
    k8s_timeout_seconds: float = float(os.getenv("K8S_TIMEOUT_SECONDS", "5.0"))
    k8s_max_log_lines: int = int(os.getenv("K8S_MAX_LOG_LINES", "100"))
    k8s_max_log_bytes: int = int(os.getenv("K8S_MAX_LOG_BYTES", "32768"))
    k8s_max_events: int = int(os.getenv("K8S_MAX_EVENTS", "25"))

    # Prometheus Adapter Configuration (Read-Only)
    prometheus_base_url: str = os.getenv(
        "PROMETHEUS_BASE_URL", "http://prometheus-operated.monitoring.svc.cluster.local:9090"
    )
    prometheus_timeout_seconds: float = float(os.getenv("PROMETHEUS_TIMEOUT_SECONDS", "5.0"))
    prometheus_max_response_bytes: int = int(os.getenv("PROMETHEUS_MAX_BYTES", "65536"))

    # Validation Thresholds
    min_confidence_score: float = float(os.getenv("AIOPS_MIN_CONFIDENCE_SCORE", "0.3"))

    # S3 Diagnostics Bucket
    diagnostics_bucket: str = os.getenv(
        "AIOPS_DIAGNOSTICS_BUCKET", "boutique-aiops-node-diagnostics-us-east-2"
    )

    # Durable Queue & Persistence Backend Configuration (Stage 6.4.3)
    queue_backend: str = os.getenv("AIOPS_QUEUE_BACKEND", "memory").lower()
    persistence_backend: str = os.getenv("AIOPS_PERSISTENCE_BACKEND", "memory").lower()
    sqs_queue_url: str = os.getenv("AIOPS_SQS_QUEUE_URL", "")
    sqs_dlq_url: str = os.getenv("AIOPS_SQS_DLQ_URL", "")
    sqs_queue_name: str = os.getenv("AIOPS_SQS_QUEUE_NAME", "")
    sqs_dlq_name: str = os.getenv("AIOPS_SQS_DLQ_NAME", "")
    dynamodb_episodes_table: str = os.getenv("AIOPS_DYNAMODB_EPISODES_TABLE", "boutique-aiops-episodes")
    dynamodb_rca_table: str = os.getenv("AIOPS_DYNAMODB_RCA_TABLE", "boutique-aiops-rca-reports")
    sqs_visibility_timeout_seconds: int = int(os.getenv("AIOPS_SQS_VISIBILITY_TIMEOUT", "300"))
    worker_poll_wait_seconds: int = int(os.getenv("AIOPS_WORKER_POLL_WAIT_SECONDS", "20"))
    worker_lease_duration_seconds: int = int(os.getenv("AIOPS_WORKER_LEASE_DURATION_SECONDS", "180"))
    worker_heartbeat_interval_seconds: float = float(os.getenv("AIOPS_WORKER_HEARTBEAT_INTERVAL_SECONDS", "60"))
    episode_ttl_seconds: int = int(os.getenv("AIOPS_EPISODE_TTL_SECONDS", "86400"))  # 24 hours
    rca_ttl_seconds: int = int(os.getenv("AIOPS_RCA_TTL_SECONDS", "2592000"))  # 30 days

    # Webhook Receiver & Queue Configuration (Stage 6.4.2A / 6.4.3)
    webhook_enabled: bool = os.getenv("AIOPS_WEBHOOK_ENABLED", "false").lower() in ("true", "1")
    webhook_bearer_token: str = os.getenv("AIOPS_WEBHOOK_BEARER_TOKEN", "")
    webhook_max_queue_size: int = int(os.getenv("AIOPS_WEBHOOK_MAX_QUEUE_SIZE", "10"))
    webhook_max_payload_bytes: int = int(os.getenv("AIOPS_WEBHOOK_MAX_PAYLOAD_BYTES", "1048576"))  # 1 MiB
    webhook_dedup_ttl_seconds: int = int(os.getenv("AIOPS_WEBHOOK_DEDUP_TTL_SECONDS", "86400"))  # 24 hours
    cluster_identity: str = os.getenv("AIOPS_CLUSTER_IDENTITY", "boutique-dev-eks")
    http_max_concurrency: int = int(os.getenv("AIOPS_HTTP_MAX_CONCURRENCY", "16"))
    http_request_timeout: float = float(os.getenv("AIOPS_HTTP_REQUEST_TIMEOUT", "10.0"))

    # Bedrock Execution Gate (Safety Switch: disabled by default for prototype)
    bedrock_enabled: bool = os.getenv("AIOPS_BEDROCK_ENABLED", "false").lower() in ("true", "1")

    # GitOps Remediation PR Generator Configuration (Stage 6.5)
    remediation_enabled: bool = os.getenv("AIOPS_REMEDIATION_ENABLED", "true").lower() in ("true", "1")
    remediation_min_confidence: float = float(os.getenv("AIOPS_REMEDIATION_MIN_CONFIDENCE", "0.70"))
    github_repository: str = os.getenv(
        "AIOPS_GITHUB_REPOSITORY", "itsme-aarjav/autonomous-devsecops-platform"
    )
    github_token: str = os.getenv("AIOPS_GITHUB_TOKEN", os.getenv("GITHUB_TOKEN", ""))
    github_api_url: str = os.getenv("AIOPS_GITHUB_API_URL", "https://api.github.com")
    git_repo_root: str = os.getenv("AIOPS_GIT_REPO_ROOT", ".")
