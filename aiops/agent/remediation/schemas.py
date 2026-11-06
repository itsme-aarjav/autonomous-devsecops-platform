"""
Autonomous AIOps Platform — Remediation Data Schemas & Validation Models
"""

from enum import Enum
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class RemediationActionType(str, Enum):
    """Supported declarative GitOps remediation action types."""

    SET_MEMORY_RESOURCES = "SET_MEMORY_RESOURCES"
    SET_CPU_RESOURCES = "SET_CPU_RESOURCES"
    SCALE_REPLICAS = "SCALE_REPLICAS"
    REVERT_IMAGE_DIGEST = "REVERT_IMAGE_DIGEST"
    NO_ACTION = "NO_ACTION"


class PolicyDecision(str, Enum):
    """Deterministic policy gate outcome."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


class RemediationStatus(str, Enum):
    """Lifecycle state of a remediation proposal."""

    PROPOSED = "PROPOSED"
    POLICY_APPROVED = "POLICY_APPROVED"
    POLICY_REJECTED = "POLICY_REJECTED"
    PENDING_HUMAN_APPROVAL = "PENDING_HUMAN_APPROVAL"
    APPLIED_TO_MAIN = "APPLIED_TO_MAIN"
    PR_CREATED = "PR_CREATED"
    PR_EXISTS = "PR_EXISTS"
    PR_FAILED = "PR_FAILED"


class RemediationParameters(BaseModel):
    """Typed parameters for declarative GitOps manifest modification."""

    replicas: Optional[int] = Field(None, ge=1, le=5, description="Target replica count (bounded 1-5)")
    memory_request: Optional[str] = Field(None, pattern=r"^[0-9]+(Mi|Gi)$", description="Memory request (e.g. 256Mi)")
    memory_limit: Optional[str] = Field(None, pattern=r"^[0-9]+(Mi|Gi)$", description="Memory limit (e.g. 512Mi)")
    cpu_request: Optional[str] = Field(None, pattern=r"^[0-9]+m$", description="CPU request in millicores (e.g. 200m)")
    cpu_limit: Optional[str] = Field(None, pattern=r"^[0-9]+m$", description="CPU limit in millicores (e.g. 500m)")
    image_digest: Optional[str] = Field(None, pattern=r"^sha256:[a-f0-9]{64}$", description="Pinned image SHA256 digest")
    target_container: Optional[str] = Field(None, description="Container name within pod spec")

    @model_validator(mode="after")
    def validate_resource_pairs(self) -> "RemediationParameters":
        """Ensures request <= limit when both memory or CPU parameters are specified."""
        if self.memory_request and self.memory_limit:
            req_bytes = _parse_memory_bytes(self.memory_request)
            lim_bytes = _parse_memory_bytes(self.memory_limit)
            if req_bytes > lim_bytes:
                raise ValueError(f"memory_request ({self.memory_request}) cannot exceed memory_limit ({self.memory_limit})")

        if self.cpu_request and self.cpu_limit:
            req_m = int(self.cpu_request.rstrip("m"))
            lim_m = int(self.cpu_limit.rstrip("m"))
            if req_m > lim_m:
                raise ValueError(f"cpu_request ({self.cpu_request}) cannot exceed cpu_limit ({self.cpu_limit})")

        return self


def _parse_memory_bytes(mem_str: str) -> int:
    """Parses Kubernetes memory string (Mi or Gi) into integer bytes."""
    val = mem_str.strip()
    if val.endswith("Gi"):
        return int(val[:-2]) * 1024 * 1024 * 1024
    elif val.endswith("Mi"):
        return int(val[:-2]) * 1024 * 1024
    elif val.endswith("Ki"):
        return int(val[:-2]) * 1024
    return int(val)


class RemediationProposal(BaseModel):
    """Validated, traceable GitOps remediation proposal."""

    proposal_id: str = Field(..., min_length=1, description="Unique proposal identifier")
    incident_id: str = Field(..., min_length=1, description="Originating incident identifier")
    episode_id: str = Field(..., min_length=1, description="Originating episode identifier")
    category: str = Field(..., min_length=1, description="Incident category")
    action_type: RemediationActionType = Field(..., description="Targeted remediation action")
    workload: str = Field(..., min_length=1, description="Canonical workload/service name")
    namespace: str = Field("boutique", min_length=1, description="Target Kubernetes namespace")
    target_manifest: str = Field(..., min_length=1, description="Relative repository path to target manifest")
    parameters: RemediationParameters = Field(default_factory=RemediationParameters)
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="RCA confidence score")
    justification: str = Field(..., min_length=1, description="Human-readable justification for the remediation")
    policy_decision: PolicyDecision = Field(PolicyDecision.MANUAL_REVIEW_REQUIRED, description="Policy gate decision")
    policy_reason: str = Field("", description="Explanation of policy decision")
    status: RemediationStatus = Field(RemediationStatus.PROPOSED, description="Current proposal lifecycle status")
    is_approved_by_human: bool = Field(False, description="Whether explicit authenticated human approval has been granted")
    is_simulated_approval: bool = Field(False, description="Whether this approval was executed in offline simulation mode")
    approval_mode: Optional[str] = Field(None, description="Approval mode: 'AUTHENTICATED' or 'SIMULATED'")
    approved_by: Optional[str] = Field(None, description="Identifier of human operator who approved")
    applied_commit_sha: Optional[str] = Field(None, description="Commit SHA on main after approval and application")
    github_pr_number: Optional[int] = Field(None, description="Draft PR number on GitHub if created")
    github_pr_url: Optional[str] = Field(None, description="Draft PR URL on GitHub if created")
    github_branch: Optional[str] = Field(None, description="Remediation feature branch name")
    diff_summary: Optional[str] = Field(None, description="Unified diff summary of proposed manifest changes")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")
    approved_at: Optional[datetime] = Field(None, description="Timestamp when proposal was approved")
    rejected_at: Optional[datetime] = Field(None, description="Timestamp when proposal was rejected")

