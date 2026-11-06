"""
Autonomous AIOps Platform — Remediation Module
"""

from .schemas import (
    RemediationActionType,
    PolicyDecision,
    RemediationStatus,
    RemediationParameters,
    RemediationProposal,
)
from .policy import (
    RemediationPolicyEngine,
    ALLOWLISTED_WORKLOADS,
    ALLOWLISTED_NAMESPACES,
    WORKLOAD_MANIFEST_MAP,
)
from .renderer import (
    ManifestPatchRenderer,
    RenderedPatch,
    ManifestRenderError,
)
from .github_provider import (
    BaseGitHubProvider,
    GitHubApiProvider,
    GitHubProviderError,
    GitHubAuthError,
    GitHubRateLimitError,
    GitHubConflictError,
)
from .store import (
    BaseRemediationStore,
    InMemoryRemediationStore,
    LocalFileRemediationStore,
)
from .runbook_executor import (
    AnsibleRunbookExecutor,
    AnsibleExecutionResult,
)
from .authenticator import (
    BaseApprovalAuthenticator,
    TrustedTokenApprovalAuthenticator,
    AwsIamApprovalAuthenticator,
)
from .generator import GitOpsRemediationEngine

__all__ = [
    "RemediationActionType",
    "PolicyDecision",
    "RemediationStatus",
    "RemediationParameters",
    "RemediationProposal",
    "RemediationPolicyEngine",
    "ALLOWLISTED_WORKLOADS",
    "ALLOWLISTED_NAMESPACES",
    "WORKLOAD_MANIFEST_MAP",
    "ManifestPatchRenderer",
    "RenderedPatch",
    "ManifestRenderError",
    "BaseGitHubProvider",
    "GitHubApiProvider",
    "GitHubProviderError",
    "GitHubAuthError",
    "GitHubRateLimitError",
    "GitHubConflictError",
    "BaseRemediationStore",
    "InMemoryRemediationStore",
    "LocalFileRemediationStore",
    "AnsibleRunbookExecutor",
    "AnsibleExecutionResult",
    "BaseApprovalAuthenticator",
    "TrustedTokenApprovalAuthenticator",
    "AwsIamApprovalAuthenticator",
    "GitOpsRemediationEngine",
]

