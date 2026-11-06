"""
Autonomous AIOps Platform — Autonomous GitOps Remediation Generator & PR Orchestrator
"""

import hashlib
import logging
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pathlib import Path

from ..schemas import RootCauseAnalysis
from .schemas import (
    RemediationProposal,
    RemediationActionType,
    RemediationParameters,
    PolicyDecision,
    RemediationStatus,
)
from .policy import RemediationPolicyEngine, WORKLOAD_MANIFEST_MAP
from .renderer import ManifestPatchRenderer, ManifestRenderError
from .github_provider import BaseGitHubProvider
from .store import BaseRemediationStore, InMemoryRemediationStore
from .authenticator import BaseApprovalAuthenticator

logger = logging.getLogger("aiops.remediation.generator")


class GitOpsRemediationEngine:
    """
    Coordinates policy evaluation, manifest patch rendering, and human-approved direct-main application
    for validated Root Cause Analysis outcomes.
    """

    def __init__(
        self,
        repo_root: str,
        policy_engine: Optional[RemediationPolicyEngine] = None,
        renderer: Optional[ManifestPatchRenderer] = None,
        github_provider: Optional[BaseGitHubProvider] = None,
        store: Optional[BaseRemediationStore] = None,
        approval_authenticator: Optional[BaseApprovalAuthenticator] = None,
        min_confidence: float = 0.70,
    ):
        self.repo_root = repo_root
        self.policy_engine = policy_engine or RemediationPolicyEngine(min_confidence=min_confidence)
        self.renderer = renderer or ManifestPatchRenderer(repo_root=repo_root, github_provider=github_provider)
        self.github_provider = github_provider
        self.store = store or InMemoryRemediationStore()
        self.approval_authenticator = approval_authenticator
        # In-process lock serializing concurrent approval calls on this engine instance.
        # Cross-process concurrency is safely governed by GitHub atomic branch CAS (PATCH refs/heads/main).
        self._apply_lock = threading.Lock()

    def process_rca_and_propose(
        self,
        rca: RootCauseAnalysis,
        incident: Optional[Dict[str, Any]] = None,
        episode_id: Optional[str] = None,
    ) -> RemediationProposal:
        """
        Main entrypoint: converts validated RCA into a typed proposal, gates with policy,
        renders allowlisted manifest patch, and prepares a direct-main proposal if approved.
        """
        inc_id = rca.incident_id
        ep_id = episode_id or inc_id
        workload = self._extract_workload(rca, incident)
        category = rca.category

        # 1. Synthesize candidate proposal
        proposal = self._build_candidate_proposal(
            rca=rca,
            incident_id=inc_id,
            episode_id=ep_id,
            workload=workload,
            category=category,
        )

        # 2. Evaluate with deterministic policy engine
        decision, reason = self.policy_engine.evaluate(
            proposal=proposal,
            rca_is_destructive=rca.is_destructive,
        )
        proposal.policy_decision = decision
        proposal.policy_reason = reason

        if decision != PolicyDecision.APPROVED:
            proposal.status = RemediationStatus.POLICY_REJECTED
            self.store.save_proposal(proposal)
            logger.info(
                "Remediation proposal %s for %s was not approved: decision=%s, reason=%s",
                proposal.proposal_id,
                workload,
                decision.value,
                reason,
            )
            return proposal

        proposal.status = RemediationStatus.POLICY_APPROVED

        # 3. Render manifest patch
        try:
            rendered = self.renderer.render_proposal_patch(proposal)
            proposal.diff_summary = rendered.diff
        except ManifestRenderError as rend_err:
            proposal.status = RemediationStatus.POLICY_REJECTED
            proposal.policy_reason += f" | Render error: {str(rend_err)}"
            self.store.save_proposal(proposal)
            logger.error("Manifest rendering failed for proposal %s: %s", proposal.proposal_id, str(rend_err))
            return proposal

        # 5. Enforce single-main-branch operational policy:
        # Generate a reviewable patch and wait for explicit human approval.
        # Do not create remediation branches or PRs.
        # Do not enable automatic unattended commits.
        proposal.status = RemediationStatus.PENDING_HUMAN_APPROVAL
        proposal.is_approved_by_human = False
        proposal.github_branch = "main"
        proposal.github_pr_number = None
        proposal.github_pr_url = None
        logger.info(
            "Generated reviewable GitOps patch for %s (%s). Awaiting explicit human approval before applying to 'main'.",
            proposal.workload,
            proposal.proposal_id,
        )

        self.store.save_proposal(proposal)
        return proposal

    def apply_approved_remediation(
        self,
        proposal_id: str,
        operator: Optional[str] = None,
        approval_token: Optional[str] = None,
        is_simulation: bool = False,
        write_to_working_tree: bool = True,
        commit_to_main: bool = False,
    ) -> RemediationProposal:
        """
        Applies a previously generated and policy-approved GitOps patch directly to 'main'.
        Enforces human approval authentication:
        - Real execution (is_simulation=False): Caller-supplied operator strings alone are strictly
          rejected. An authentic human approval via a configured trusted authenticator is required.
          If no trusted authenticator is configured, fails closed and proposal remains pending.
        - Offline simulation (is_simulation=True): Explicitly labels the approval as simulated
          ([SIMULATED] <operator>) and sets is_simulated_approval=True, is_approved_by_human=False.
        Fails closed if the proposal is not policy-approved or was rejected.
        """
        with self._apply_lock:
            proposal = self.store.get_proposal(proposal_id)
            if not proposal:
                raise ValueError(f"Remediation proposal '{proposal_id}' not found in store.")

            if proposal.policy_decision != PolicyDecision.APPROVED:
                raise PermissionError(
                    f"Cannot apply unapproved remediation: policy decision is '{proposal.policy_decision.value}' (must be APPROVED)."
                )

            if proposal.status == RemediationStatus.APPLIED_TO_MAIN:
                logger.info("Remediation proposal %s has already been applied to 'main'.", proposal_id)
                return proposal

            # 1. Human Approval Authentication Gate
            if is_simulation:
                if not operator or not isinstance(operator, str) or not operator.strip():
                    raise PermissionError("Simulated human operator identifier required for offline simulation.")
                verified_identity = f"[SIMULATED] {operator.strip()}"
                is_authenticated = False
                is_simulated = True
                logger.warning(
                    "[SIMULATION ONLY] Remediation proposal %s applied with simulated operator '%s'. "
                    "This is an offline simulation and does NOT constitute real authenticated human approval.",
                    proposal_id,
                    operator.strip(),
                )
            else:
                if self.approval_authenticator is None:
                    raise PermissionError(
                        "Unauthenticated approval rejected: no trusted human identity mechanism is configured. "
                        "Caller-supplied operator strings alone cannot authorize changes to 'main'. "
                        "Remediation proposal remains in PENDING_HUMAN_APPROVAL."
                    )

                authenticated, result_or_err = self.approval_authenticator.authenticate(
                    proposal=proposal,
                    approval_token=approval_token,
                    operator=operator,
                )
                if not authenticated:
                    raise PermissionError(
                        f"Human approval authentication failed: {result_or_err}. "
                        "Remediation proposal remains in PENDING_HUMAN_APPROVAL."
                    )

                verified_identity = result_or_err
                is_authenticated = True
                is_simulated = False
                logger.info(
                    "Remediation proposal %s successfully authenticated for operator '%s'.",
                    proposal_id,
                    verified_identity,
                )

            # 2. Render patch and verify patch integrity against operator review
            rendered = self.renderer.render_proposal_patch(proposal)
            if proposal.diff_summary and rendered.diff.strip() != proposal.diff_summary.strip():
                raise PermissionError(
                    f"Remediation patch integrity check failed: generated diff differs from reviewed diff "
                    f"for proposal '{proposal.proposal_id}'. Aborting to prevent unreviewed mutations."
                )

            if write_to_working_tree:
                repo_path = Path(self.repo_root)
                for rel_path, content in rendered.modified_files.items():
                    target_file = repo_path / rel_path
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    target_file.write_text(content, encoding="utf-8")

            new_commit_sha = None
            if commit_to_main:
                if not self.github_provider:
                    raise RuntimeError(
                        f"Cannot commit remediation proposal '{proposal.proposal_id}' to main: no GitHub provider or credentials configured."
                    )
                existing_commit_sha = self.github_provider.find_commit_for_proposal(
                    proposal_id=proposal.proposal_id,
                )
                if existing_commit_sha:
                    logger.info(
                        "Remediation proposal %s was already committed to 'main' in commit %s. Reconciling proposal state.",
                        proposal_id,
                        existing_commit_sha,
                    )
                    return self._finalize_applied(
                        proposal, verified_identity, is_authenticated, is_simulated, existing_commit_sha, is_reconcile=True
                    )

                commit_msg = (
                    f"fix(gitops): apply approved {proposal.action_type.value} for {proposal.workload}\n\n"
                    f"Proposal-ID: {proposal.proposal_id}\n"
                    f"Incident: {proposal.incident_id}\n"
                    f"Episode: {proposal.episode_id}\n"
                    f"Approved-by: {verified_identity}\n"
                    f"Mode: {'SIMULATION' if is_simulated else 'AUTHENTICATED'}\n"
                    f"Action: {rendered.summary}"
                )
                default_branch = self.github_provider.get_default_branch()
                parent_sha = self.github_provider.get_branch_head_sha(default_branch)
                new_commit_sha = self.github_provider.commit_to_main(
                    files=rendered.modified_files,
                    commit_message=commit_msg,
                    expected_parent_sha=parent_sha,
                )

            return self._finalize_applied(
                proposal, verified_identity, is_authenticated, is_simulated, new_commit_sha, is_reconcile=False
            )

    def _finalize_applied(
        self,
        proposal: RemediationProposal,
        verified_identity: str,
        is_authenticated: bool,
        is_simulated: bool,
        commit_sha: Optional[str],
        is_reconcile: bool = False,
    ) -> RemediationProposal:
        proposal.is_approved_by_human = is_authenticated
        proposal.is_simulated_approval = is_simulated
        proposal.approval_mode = "SIMULATED" if is_simulated else "AUTHENTICATED"
        proposal.approved_by = verified_identity
        proposal.approved_at = datetime.now(timezone.utc)
        proposal.status = RemediationStatus.APPLIED_TO_MAIN
        proposal.applied_commit_sha = commit_sha

        try:
            self.store.save_proposal(proposal)
        except Exception as store_err:
            if is_reconcile:
                logger.critical(
                    "CRITICAL: Proposal %s already committed (SHA: %s) but failed to reconcile store: %s",
                    proposal.proposal_id,
                    commit_sha,
                    str(store_err),
                )
            else:
                logger.critical(
                    "CRITICAL: Remediation proposal %s was successfully committed to 'main' (SHA: %s) "
                    "by '%s', but failed to persist proposal state in store: %s",
                    proposal.proposal_id,
                    commit_sha,
                    verified_identity,
                    str(store_err),
                )
            raise

        if not is_reconcile:
            logger.info(
                "Remediation proposal %s for %s was approved by '%s' (mode=%s) and applied directly to 'main'.",
                proposal.proposal_id,
                proposal.workload,
                verified_identity,
                "SIMULATION" if is_simulated else "AUTHENTICATED",
            )
        return proposal

    def _extract_workload(self, rca: RootCauseAnalysis, incident: Optional[Dict[str, Any]]) -> str:
        """Determines target workload from incident context or RCA evidence."""
        if incident and incident.get("affected_workload"):
            raw = str(incident["affected_workload"]).strip().lower()
            candidate = raw.removeprefix("boutique-")
            return candidate if candidate in WORKLOAD_MANIFEST_MAP else raw
        text = f"{rca.root_cause} {rca.summary}".lower()
        return next((svc for svc in WORKLOAD_MANIFEST_MAP if svc in text), "unknown")

    def _build_candidate_proposal(
        self,
        rca: RootCauseAnalysis,
        incident_id: str,
        episode_id: str,
        workload: str,
        category: str,
    ) -> RemediationProposal:
        """Constructs a candidate RemediationProposal based on category and RCA."""
        prop_id = hashlib.sha256(f"{episode_id}:{workload}:{category}".encode("utf-8")).hexdigest()[:16]
        target_manifest = WORKLOAD_MANIFEST_MAP.get(workload, ["unknown"])[0]
        action_type = RemediationActionType.NO_ACTION
        params = RemediationParameters()
        justification = f"Automated remediation proposal based on validated root cause: {rca.root_cause}"

        if category == "Pod OOMKilled":
            action_type = RemediationActionType.SET_MEMORY_RESOURCES
            params = RemediationParameters(memory_request="256Mi", memory_limit="512Mi", target_container=workload)
            justification = f"Scale container memory limits for {workload} to mitigate Pod OOMKilled condition."
        elif category in ("High CPU utilization", "Application HTTP 5xx spike"):
            action_type = RemediationActionType.SCALE_REPLICAS
            params = RemediationParameters(replicas=2)
            justification = f"Scale deployment replicas to 2 for {workload} to alleviate high load / 5xx error spikes."
        elif category == "Deployment replicas unavailable":
            action_type = RemediationActionType.SCALE_REPLICAS
            params = RemediationParameters(replicas=1)
            justification = f"Restore baseline replica count for {workload}."

        return RemediationProposal(
            proposal_id=prop_id,
            incident_id=incident_id,
            episode_id=episode_id,
            category=category,
            action_type=action_type,
            workload=workload,
            namespace="boutique",
            target_manifest=target_manifest,
            parameters=params,
            confidence_score=rca.confidence_score,
            justification=justification,
        )
