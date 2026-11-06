"""
Autonomous AIOps Platform — Data Schemas & Validation Models
"""

import re
import hashlib
from enum import Enum
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


SUPPORTED_INCIDENT_CATEGORIES = [
    "Kubernetes Pod CrashLoopBackOff",
    "Pod OOMKilled",
    "Deployment replicas unavailable",
    "Node MemoryPressure",
    "Node DiskPressure",
    "High CPU utilization",
    "Application HTTP 5xx spike",
    "PostgreSQL connectivity failure",
]


class IncidentCategory(str, Enum):
    """Supported incident categories for autonomous investigation."""

    POD_CRASH_LOOP = "Kubernetes Pod CrashLoopBackOff"
    POD_OOM_KILLED = "Pod OOMKilled"
    DEPLOYMENT_UNAVAILABLE = "Deployment replicas unavailable"
    NODE_MEMORY_PRESSURE = "Node MemoryPressure"
    NODE_DISK_PRESSURE = "Node DiskPressure"
    HIGH_CPU_UTILIZATION = "High CPU utilization"
    HTTP_5XX_SPIKE = "Application HTTP 5xx spike"
    POSTGRES_FAILURE = "PostgreSQL connectivity failure"


class IncidentSeverity(str, Enum):
    """Normalized incident severity levels."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    WARNING = "WARNING"
    INFO = "INFO"


class IncidentInput(BaseModel):
    """Schema for raw incoming alert or incident payload."""

    incident_id: str = Field(..., min_length=1, description="Unique incident identifier")
    title: Optional[str] = Field(None, description="Human readable incident or alert title")
    alert_name: Optional[str] = Field(None, description="Prometheus or system alert name")
    category: str = Field(..., description="Incident category")
    severity: str = Field("warning", description="Alert severity level")
    affected_workload: str = Field(..., min_length=1, description="Workload or service name")
    namespace: str = Field("default", min_length=1, description="Kubernetes namespace")
    description: Optional[str] = Field("", description="Detailed incident description")
    timestamp: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc), description="Detection timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context labels and annotations")

    @model_validator(mode="before")
    @classmethod
    def populate_title_or_alert_name(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("title") and data.get("alert_name"):
                data["title"] = data["alert_name"]
            elif not data.get("alert_name") and data.get("title"):
                data["alert_name"] = data["title"]
            if not data.get("title"):
                raise ValueError("Either 'title' or 'alert_name' must be provided")
        return data

    @field_validator("severity")
    @classmethod
    def normalize_severity(cls, v: str) -> IncidentSeverity:
        raw = str(v).strip().upper()
        if raw in ("CRITICAL", "PAGE", "FATAL"):
            return IncidentSeverity.CRITICAL
        elif raw in ("HIGH", "ERROR"):
            return IncidentSeverity.HIGH
        elif raw in ("WARN", "WARNING", "MEDIUM"):
            return IncidentSeverity.WARNING
        elif raw in ("INFO", "INFORMATION", "LOW"):
            return IncidentSeverity.INFO
        return IncidentSeverity.INFO


class NormalizedIncident(BaseModel):
    """Cleaned, deduplicated internal incident representation."""

    incident_id: str
    title: str
    category: str
    severity: IncidentSeverity
    affected_workload: str
    namespace: str
    timestamp: datetime
    dedup_key: str
    description: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_input(cls, inp: IncidentInput) -> "NormalizedIncident":
        ts = inp.timestamp or datetime.now(timezone.utc)
        date_hour = ts.strftime("%Y-%m-%d-%H")
        hash_input = f"{inp.namespace}:{inp.affected_workload}:{inp.category}:{date_hour}"
        dedup_key = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

        return cls(
            incident_id=inp.incident_id,
            title=inp.title or inp.alert_name or "Incident",
            category=inp.category,
            severity=IncidentSeverity(inp.severity),
            affected_workload=inp.affected_workload,
            namespace=inp.namespace,
            timestamp=ts,
            dedup_key=dedup_key,
            description=inp.description or "",
            metadata=inp.metadata,
        )


FORBIDDEN_COMMAND_PATTERNS = [
    r"\brm\s+-[a-zA-Z]*rf?\b",
    r"\bkubectl\s+delete\b",
    r"\bkubectl\s+drain\b",
    r"\bhelm\s+uninstall\b",
    r"\bterraform\s+destroy\b",
    r"\bdrop\s+database\b",
    r"\bdrop\s+table\b",
    r"\btruncate\b",
    r"\bkill\s+-9\b",
    r"\bchmod\s+777\b",
    r"\bchown\b",
    r"\baws\s+.*\s+delete\b",
]


class RootCauseAnalysis(BaseModel):
    """Validated structured root cause analysis produced by Amazon Bedrock."""

    incident_id: str
    category: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    summary: str
    root_cause: str
    supporting_evidence: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    is_destructive: bool = False

    @field_validator("supporting_evidence")
    @classmethod
    def validate_supporting_evidence(cls, v: List[str]) -> List[str]:
        if not v or len(v) == 0:
            raise ValueError("Root cause analysis must include at least one supporting evidence item")
        return v

    @field_validator("confidence_score")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError("Confidence score must be strictly between 0.0 and 1.0")
        return round(v, 2)

    @field_validator("recommended_actions")
    @classmethod
    def validate_safe_recommendations(cls, v: List[str]) -> List[str]:
        for action in v:
            for pattern in FORBIDDEN_COMMAND_PATTERNS:
                if re.search(pattern, action, re.IGNORECASE):
                    raise ValueError(
                        f"Action contains forbidden destructive command matching pattern '{pattern}': {action}"
                    )
        return v


# Prometheus Alertmanager v0.27.0 (Webhook Version 4) Schemas
class AlertStatus(str, Enum):
    """Alert status reported by Alertmanager."""

    FIRING = "firing"
    RESOLVED = "resolved"


class AlertItem(BaseModel):
    """
    Single alert item within an Alertmanager v4 webhook notification.
    Enforces RFC3339 timestamps, non-empty fingerprint, and required labels.
    """

    status: AlertStatus
    labels: Dict[str, str] = Field(default_factory=dict)
    annotations: Dict[str, str] = Field(default_factory=dict)
    startsAt: datetime
    endsAt: Optional[datetime] = None
    generatorURL: Optional[str] = ""
    fingerprint: str = Field(..., min_length=1, description="Unique Prometheus alert fingerprint")

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, v: Dict[str, str]) -> Dict[str, str]:
        if not isinstance(v, dict):
            raise ValueError("Labels must be a key-value dictionary")
        if not v:
            raise ValueError("Alert labels dictionary cannot be empty")
        if "alertname" not in v or not str(v["alertname"]).strip():
            raise ValueError("Alert labels must contain a non-empty 'alertname'")
        return v

    @field_validator("startsAt", mode="before")
    @classmethod
    def validate_rfc3339_starts_at(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                clean = v.replace("Z", "+00:00") if v.endswith("Z") else v
                return datetime.fromisoformat(clean)
            except Exception as e:
                raise ValueError(f"Invalid RFC3339 startsAt timestamp '{v}': {str(e)}")
        return v

    @field_validator("endsAt", mode="before")
    @classmethod
    def validate_rfc3339_ends_at(cls, v: Any) -> Any:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            try:
                clean = v.replace("Z", "+00:00") if v.endswith("Z") else v
                return datetime.fromisoformat(clean)
            except Exception as e:
                raise ValueError(f"Invalid RFC3339 endsAt timestamp '{v}': {str(e)}")
        return v


class AlertmanagerWebhookPayload(BaseModel):
    """
    Alertmanager v0.27.0 (Webhook Version 4) payload model.
    Strictly validates incoming Prometheus Alertmanager notifications.
    """

    version: str = Field(..., description="Alertmanager webhook protocol version")
    groupKey: str = Field(..., min_length=1, description="Alertmanager aggregation group key")
    status: AlertStatus = Field(..., description="Overall group status ('firing' or 'resolved')")
    receiver: str = Field(..., min_length=1, description="Target receiver name")
    groupLabels: Dict[str, str] = Field(default_factory=dict)
    commonLabels: Dict[str, str] = Field(default_factory=dict)
    commonAnnotations: Dict[str, str] = Field(default_factory=dict)
    externalURL: Optional[str] = ""
    alerts: List[AlertItem] = Field(..., min_length=1, description="List of individual alerts")
    truncatedAlerts: int = Field(default=0, ge=0, description="Count of omitted alerts if truncated")

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        s = str(v).strip()
        if s != "4":
            raise ValueError(f"Unsupported Alertmanager webhook version: '{s}'. Expected '4'.")
        return s

    @field_validator("alerts")
    @classmethod
    def validate_alerts_non_empty(cls, v: List[AlertItem]) -> List[AlertItem]:
        if not v or len(v) == 0:
            raise ValueError("Alert collection cannot be empty")
        return v


def map_alert_to_incident_category(alertname: str, labels: Dict[str, str], annotations: Dict[str, str]) -> str:
    """
    Maps Prometheus alert name and labels to one of the canonical SUPPORTED_INCIDENT_CATEGORIES.
    Defaults safely to 'Kubernetes Pod CrashLoopBackOff' if unclassified.
    """
    name = (alertname or "").lower()
    combined = f"{name} {labels.get('reason', '')} {annotations.get('description', '')}".lower()

    if "oomkill" in combined or "oom" in name:
        return IncidentCategory.POD_OOM_KILLED.value
    if "crashloop" in combined or "crash" in name or "notready" in name:
        return IncidentCategory.POD_CRASH_LOOP.value
    if "replicas" in combined or "deployment" in name:
        return IncidentCategory.DEPLOYMENT_UNAVAILABLE.value
    if "memorypressure" in combined:
        return IncidentCategory.NODE_MEMORY_PRESSURE.value
    if "diskpressure" in combined:
        return IncidentCategory.NODE_DISK_PRESSURE.value
    if "cpu" in combined:
        return IncidentCategory.HIGH_CPU_UTILIZATION.value
    if "5xx" in combined or "http" in combined or "errorrate" in combined:
        return IncidentCategory.HTTP_5XX_SPIKE.value
    if "postgres" in combined or "database" in combined or "db" in combined:
        return IncidentCategory.POSTGRES_FAILURE.value

    return IncidentCategory.POD_CRASH_LOOP.value


def alert_to_incident_input(
    alert: AlertItem,
    cluster_identity: str = "boutique-dev-eks",
    is_truncated: bool = False,
    truncated_count: int = 0,
) -> IncidentInput:
    """
    Converts a validated AlertItem into an IncidentInput for LangGraph ingestion.
    Applies defensive untrusted data labelling and records truncation warnings.
    """
    alertname = alert.labels.get("alertname", "UnknownAlert")
    category = map_alert_to_incident_category(alertname, alert.labels, alert.annotations)
    workload = (
        alert.labels.get("workload")
        or alert.labels.get("pod")
        or alert.labels.get("deployment")
        or alert.labels.get("service")
        or alert.labels.get("app")
        or "unknown-workload"
    )
    namespace = alert.labels.get("namespace", "boutique")
    title = alert.annotations.get("summary") or alert.annotations.get("title") or f"{alertname} on {workload}"
    description = alert.annotations.get("description") or alert.annotations.get("message") or ""

    starts_at_str = alert.startsAt.isoformat()
    episode_id = hashlib.sha256(f"{cluster_identity}:{alert.fingerprint}:{starts_at_str}".encode("utf-8")).hexdigest()

    metadata: Dict[str, Any] = {
        "fingerprint": alert.fingerprint,
        "startsAt": starts_at_str,
        "generatorURL": alert.generatorURL or "",
        "labels": alert.labels,
        "annotations": alert.annotations,
        "cluster_identity": cluster_identity,
        "untrusted_source": "alertmanager_webhook",
    }
    if is_truncated:
        metadata["incomplete_notification"] = True
        metadata["truncated_alerts_count"] = truncated_count
        metadata["warning"] = (
            f"Notification incomplete: {truncated_count} alerts were omitted by Alertmanager. "
            f"Diagnostic evidence coverage may be partial."
        )

    return IncidentInput(
        incident_id=episode_id,
        title=title,
        alert_name=alertname,
        category=category,
        severity=alert.labels.get("severity", "warning"),
        affected_workload=workload,
        namespace=namespace,
        description=description,
        timestamp=alert.startsAt,
        metadata=metadata,
    )
