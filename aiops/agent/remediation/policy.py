"""
Autonomous AIOps Platform — Deterministic Remediation Policy Engine
"""

import re
from typing import Tuple, Dict, Set, Optional, List
from .schemas import (
    RemediationProposal,
    RemediationActionType,
    PolicyDecision,
    _parse_memory_bytes,
)

ALLOWLISTED_NAMESPACES: Set[str] = {"boutique"}

ALLOWLISTED_WORKLOADS: Set[str] = {
    "auth",
    "frontend",
    "gateway",
}

# Explicit mapping of allowed workloads to their canonical GitOps manifests
WORKLOAD_MANIFEST_MAP: Dict[str, List[str]] = {
    "auth": ["gitops/k8s/backend/auth.yml"],
    "gateway": ["gitops/k8s/backend/gateway.yml"],
    "frontend": ["gitops/k8s/frontend/rollout.yaml"],
}

# Category to permitted actions mapping
CATEGORY_ACTION_MAP: Dict[str, Set[RemediationActionType]] = {
    "Pod OOMKilled": {RemediationActionType.SET_MEMORY_RESOURCES},
    "High CPU utilization": {
        RemediationActionType.SCALE_REPLICAS,
        RemediationActionType.SET_CPU_RESOURCES,
    },
    "Application HTTP 5xx spike": {
        RemediationActionType.SCALE_REPLICAS,
        RemediationActionType.SET_CPU_RESOURCES,
    },
    "Deployment replicas unavailable": {
        RemediationActionType.SCALE_REPLICAS,
    },
    "Kubernetes Pod CrashLoopBackOff": {
        RemediationActionType.REVERT_IMAGE_DIGEST,
    },
}

# Strict bounds
MIN_REPLICAS = 1
MAX_REPLICAS = 5

MIN_MEMORY_BYTES = 128 * 1024 * 1024  # 128Mi
MAX_MEMORY_BYTES = 1024 * 1024 * 1024  # 1Gi (1024Mi)

MIN_CPU_MILLICORES = 100
MAX_CPU_MILLICORES = 2000

SECRET_PATTERNS = [
    r"ey[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}",  # JWT / bearer tokens
    r"(?i)(bearer\s+[a-zA-Z0-9_\-\.]{16,})",
    r"(?i)(password|secret|apikey|api_key|token|auth_token)\s*[:=]\s*['\"]?[^\s'\"]{6,}",
    r"-----BEGIN\s+([A-Z0-9_-]+\s+)?PRIVATE\s+KEY-----",
    r"(?i)(postgresql|mysql|mongodb|redis)://[^\s'\"]+:[^\s'\"]+@",  # DB URIs with credentials
]


class RemediationPolicyEngine:
    """
    Deterministic policy evaluator for GitOps remediation proposals.
    Enforces strict allowlists, resource bounds, confidence gates, and safety checks.
    """

    def __init__(self, min_confidence: float = 0.70):
        self.min_confidence = min_confidence

    def evaluate(
        self,
        proposal: RemediationProposal,
        rca_is_destructive: bool = False,
        min_confidence_override: Optional[float] = None,
    ) -> Tuple[PolicyDecision, str]:
        """
        Evaluates a remediation proposal against all deterministic policy rules.
        Returns: (PolicyDecision, reason)
        """
        threshold = min_confidence_override if min_confidence_override is not None else self.min_confidence

        # 1. Destructive check
        if rca_is_destructive:
            return (
                PolicyDecision.REJECTED,
                "Policy rejection: RCA marked action as destructive. Autonomous GitOps proposals must be non-destructive.",
            )

        # 2. Confidence threshold
        if proposal.confidence_score < threshold:
            return (
                PolicyDecision.REJECTED,
                f"Policy rejection: RCA confidence score ({proposal.confidence_score:.2f}) is below minimum threshold ({threshold:.2f}).",
            )

        # 3. Workload allowlist
        if proposal.workload not in ALLOWLISTED_WORKLOADS:
            return (
                PolicyDecision.REJECTED,
                f"Policy rejection: Workload '{proposal.workload}' is not in allowlisted services: {sorted(ALLOWLISTED_WORKLOADS)}.",
            )

        # 4. Namespace allowlist
        if proposal.namespace not in ALLOWLISTED_NAMESPACES:
            return (
                PolicyDecision.REJECTED,
                f"Policy rejection: Namespace '{proposal.namespace}' is not in allowlisted namespaces: {sorted(ALLOWLISTED_NAMESPACES)}.",
            )

        # 5. Manifest allowlist & path traversal check
        if ".." in proposal.target_manifest or proposal.target_manifest.startswith("/"):
            return (
                PolicyDecision.REJECTED,
                f"Policy rejection: Malformed or directory traversal target manifest path '{proposal.target_manifest}'.",
            )

        allowed_manifests = WORKLOAD_MANIFEST_MAP.get(proposal.workload, [])
        if proposal.target_manifest not in allowed_manifests:
            return (
                PolicyDecision.REJECTED,
                f"Policy rejection: Manifest '{proposal.target_manifest}' is not allowlisted for workload '{proposal.workload}'. Allowed: {allowed_manifests}.",
            )

        # 6. Action alignment with category
        permitted_actions = CATEGORY_ACTION_MAP.get(proposal.category)
        if not permitted_actions:
            return (
                PolicyDecision.MANUAL_REVIEW_REQUIRED,
                f"Policy hold: Category '{proposal.category}' has no automated remediation policy. Manual engineering review required.",
            )

        if proposal.action_type not in permitted_actions:
            return (
                PolicyDecision.REJECTED,
                f"Policy rejection: Action '{proposal.action_type.value}' is not permitted for category '{proposal.category}'. Permitted: {[a.value for a in permitted_actions]}.",
            )

        # 7. Action-specific parameter bounds
        params = proposal.parameters

        if proposal.action_type == RemediationActionType.SCALE_REPLICAS:
            if params.replicas is None:
                return (
                    PolicyDecision.REJECTED,
                    "Policy rejection: SCALE_REPLICAS action requires 'replicas' parameter.",
                )
            if params.replicas < MIN_REPLICAS or params.replicas > MAX_REPLICAS:
                return (
                    PolicyDecision.REJECTED,
                    f"Policy rejection: Replicas {params.replicas} out of allowed bounds [{MIN_REPLICAS}, {MAX_REPLICAS}].",
                )

        elif proposal.action_type == RemediationActionType.SET_MEMORY_RESOURCES:
            if not params.memory_limit and not params.memory_request:
                return (
                    PolicyDecision.REJECTED,
                    "Policy rejection: SET_MEMORY_RESOURCES requires at least memory_limit or memory_request.",
                )
            if params.memory_limit:
                lim_b = _parse_memory_bytes(params.memory_limit)
                if lim_b < MIN_MEMORY_BYTES or lim_b > MAX_MEMORY_BYTES:
                    return (
                        PolicyDecision.REJECTED,
                        f"Policy rejection: Memory limit {params.memory_limit} out of bounds [{MIN_MEMORY_BYTES // (1024*1024)}Mi, {MAX_MEMORY_BYTES // (1024*1024)}Mi].",
                    )
            if params.memory_request:
                req_b = _parse_memory_bytes(params.memory_request)
                if req_b < MIN_MEMORY_BYTES or req_b > MAX_MEMORY_BYTES:
                    return (
                        PolicyDecision.REJECTED,
                        f"Policy rejection: Memory request {params.memory_request} out of bounds [{MIN_MEMORY_BYTES // (1024*1024)}Mi, {MAX_MEMORY_BYTES // (1024*1024)}Mi].",
                    )

        elif proposal.action_type == RemediationActionType.SET_CPU_RESOURCES:
            if not params.cpu_limit and not params.cpu_request:
                return (
                    PolicyDecision.REJECTED,
                    "Policy rejection: SET_CPU_RESOURCES requires at least cpu_limit or cpu_request.",
                )
            if params.cpu_limit:
                lim_m = int(params.cpu_limit.rstrip("m"))
                if lim_m < MIN_CPU_MILLICORES or lim_m > MAX_CPU_MILLICORES:
                    return (
                        PolicyDecision.REJECTED,
                        f"Policy rejection: CPU limit {params.cpu_limit} out of bounds [{MIN_CPU_MILLICORES}m, {MAX_CPU_MILLICORES}m].",
                    )
            if params.cpu_request:
                req_m = int(params.cpu_request.rstrip("m"))
                if req_m < MIN_CPU_MILLICORES or req_m > MAX_CPU_MILLICORES:
                    return (
                        PolicyDecision.REJECTED,
                        f"Policy rejection: CPU request {params.cpu_request} out of bounds [{MIN_CPU_MILLICORES}m, {MAX_CPU_MILLICORES}m].",
                    )

        elif proposal.action_type == RemediationActionType.REVERT_IMAGE_DIGEST:
            if not params.image_digest:
                return (
                    PolicyDecision.REJECTED,
                    "Policy rejection: REVERT_IMAGE_DIGEST requires 'image_digest' parameter.",
                )

        # 8. Secret & credential leak prevention in justification and params
        text_to_check = f"{proposal.justification} {params.model_dump_json()}"
        for pattern in SECRET_PATTERNS:
            if re.search(pattern, text_to_check):
                return (
                    PolicyDecision.REJECTED,
                    "Policy rejection: Potential credential or secret pattern detected in remediation proposal.",
                )

        return (
            PolicyDecision.APPROVED,
            f"Policy approval: Proposal for workload '{proposal.workload}' satisfies all safety, bounding, and allowlist constraints.",
        )

