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
        write_to_working_tree: bool = False,
        commit_to_main: bool = False,
        create_pr: bool = False,
    ) -> RemediationProposal:
        """
        Applies a previously generated and policy-approved GitOps patch directly to 'main'.
        Enforces human approval authentication:
        - Real execution (is_simulation=False): Caller-supplied operator strings alone are strictly
          rejected. An authentic human approval via a configured trusted authenticator is required.
          If no trusted authenticator is configured, fails closed and proposal remains pending.
        - Offline simulation (is_simulation=True): Explicitly labels the approval as simulated
          ([SIMULATED] <operator>) and sets is_simulated_approval=True, is_approved_by_human=False.
          Simulation mode CANNOT commit to real remote GitHub repositories.
        Fails closed if the proposal is not policy-approved or was rejected.
        """
        if commit_to_main:
            raise PermissionError(
                "Security policy violation: direct commits to 'main' branch are strictly prohibited. "
                "All remediation approvals must create a reviewed GitHub Pull Request."
            )

        with self._apply_lock:
            proposal = self.store.get_proposal(proposal_id)
            if not proposal:
                raise ValueError(f"Remediation proposal '{proposal_id}' not found in store.")

            if proposal.status in (RemediationStatus.POLICY_REJECTED, RemediationStatus.OPERATOR_REJECTED):
                raise PermissionError(
                    f"Cannot apply rejected proposal '{proposal_id}' (status: {proposal.status.value})."
                )

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

            # 3. Execution & Atomic State Transitions
            if create_pr:
                if is_simulation:
                    sim_proposal = proposal.model_copy(deep=True)
                    sim_proposal.status = RemediationStatus.PR_CREATED
                    sim_proposal.is_approved_by_human = False
                    sim_proposal.is_simulated_approval = True
                    sim_proposal.approval_mode = "SIMULATED"
                    sim_proposal.approved_by = verified_identity
                    sim_proposal.approved_at = datetime.now(timezone.utc)
                    sim_proposal.github_branch = f"fix/aiops-proposal-{proposal.proposal_id[:8]}"
                    sim_proposal.github_pr_number = 999
                    sim_proposal.github_pr_url = "https://github.com/itsme-aarjav/autonomous-devsecops-platform/pull/999"
                    sim_proposal.applied_commit_sha = "simulated-pr-commit-sha"

                    transitioned = self.store.atomic_transition_status(
                        proposal_id=proposal.proposal_id,
                        expected_statuses=[
                            RemediationStatus.PENDING_HUMAN_APPROVAL.value,
                            RemediationStatus.POLICY_APPROVED.value,
                        ],
                        new_status=RemediationStatus.PR_CREATED.value,
                        updated_proposal=sim_proposal,
                    )
                    if not transitioned:
                        fresh = self.store.get_proposal(proposal.proposal_id)
                        raise PermissionError(
                            f"Cannot create PR for proposal '{proposal.proposal_id}': status modified to '{fresh.status.value if fresh else 'UNKNOWN'}'."
                        )
                    logger.info(
                        "Remediation proposal %s PR created in SIMULATION mode: branch=%s, pr=%s",
                        proposal.proposal_id,
                        sim_proposal.github_branch,
                        sim_proposal.github_pr_url,
                    )
                    return sim_proposal

                if not self.github_provider:
                    raise RuntimeError(
                        f"Cannot create remediation PR for proposal '{proposal.proposal_id}': no GitHub provider or credentials configured."
                    )

                if proposal.status == RemediationStatus.PR_CREATED and proposal.github_pr_url:
                    logger.info("Remediation proposal %s PR already created at %s", proposal_id, proposal.github_pr_url)
                    return proposal

                # Atomic claim to APPLICATION_IN_PROGRESS
                claimed_proposal = proposal.model_copy(deep=True)
                claimed_proposal.status = RemediationStatus.APPLICATION_IN_PROGRESS
                claimed_proposal.approved_by = verified_identity
                claimed_proposal.is_approved_by_human = is_authenticated
                claimed_proposal.is_simulated_approval = is_simulated
                claimed_proposal.approval_mode = "AUTHENTICATED"
                claimed_proposal.approved_at = datetime.now(timezone.utc)

                allowed_pre_claim = [
                    RemediationStatus.PENDING_HUMAN_APPROVAL.value,
                    RemediationStatus.POLICY_APPROVED.value,
                ]
                claimed = self.store.atomic_transition_status(
                    proposal_id=proposal.proposal_id,
                    expected_statuses=allowed_pre_claim,
                    new_status=RemediationStatus.APPLICATION_IN_PROGRESS.value,
                    updated_proposal=claimed_proposal,
                )
                if not claimed:
                    fresh = self.store.get_proposal(proposal.proposal_id)
                    fresh_status = fresh.status.value if fresh else "UNKNOWN"
                    raise PermissionError(
                        f"Concurrent state conflict: proposal '{proposal.proposal_id}' status is now '{fresh_status}'."
                    )

                pr_title = f"fix(gitops): remediate {proposal.workload} - {proposal.action_type.value}"
                pr_body = (
                    f"## AIOps Autonomous Remediation Proposal\n\n"
                    f"- **Proposal ID:** `{proposal.proposal_id}`\n"
                    f"- **Incident ID:** `{proposal.incident_id}`\n"
                    f"- **Episode ID:** `{proposal.episode_id}`\n"
                    f"- **Workload:** `{proposal.workload}` (`{proposal.namespace}`)\n"
                    f"- **Target Manifest:** `{proposal.target_manifest}`\n"
                    f"- **Approved By:** `{verified_identity}`\n"
                    f"- **Approval Mode:** AUTHENTICATED\n"
                    f"- **Confidence Score:** {proposal.confidence_score * 100:.1f}%\n\n"
                    f"### Justification\n{proposal.justification}\n\n"
                    f"### Policy Review\n- **Decision:** {proposal.policy_decision.value}\n- **Reason:** {proposal.policy_reason}\n\n"
                    f"### Manifest Changes\n```diff\n{rendered.diff.strip()}\n```\n\n"
                    f"### Review and Merge Instructions\n"
                    f"1. Review the git diff above to verify it complies with workload limits.\n"
                    f"2. Merge this Pull Request into `main`.\n"
                    f"3. GitHub Actions / Argo CD will detect the commit on `main` and synchronize the manifest to EKS.\n"
                    f"4. Verify pod health in the `{proposal.namespace}` namespace.\n"
                )
                commit_msg = (
                    f"autonomous-devsecops-platform\n\n"
                    f"Proposal-ID: {proposal.proposal_id}\n"
                    f"Incident: {proposal.incident_id}\n"
                    f"Episode: {proposal.episode_id}\n"
                    f"Approved-by: {verified_identity}\n"
                    f"Mode: AUTHENTICATED\n"
                    f"Action: {rendered.summary}"
                )

                try:
                    pr_info = self.github_provider.create_remediation_pr(
                        proposal_id=proposal.proposal_id,
                        files=rendered.modified_files,
                        commit_message=commit_msg,
                        pr_title=pr_title,
                        pr_body=pr_body,
                    )
                except Exception as pr_err:
                    try:
                        revert_proposal = claimed_proposal.model_copy(deep=True)
                        revert_proposal.status = RemediationStatus.PENDING_HUMAN_APPROVAL
                        self.store.atomic_transition_status(
                            proposal_id=proposal.proposal_id,
                            expected_statuses=[RemediationStatus.APPLICATION_IN_PROGRESS.value],
                            new_status=RemediationStatus.PENDING_HUMAN_APPROVAL.value,
                            updated_proposal=revert_proposal,
                        )
                    except Exception as rev_err:
                        logger.error("Failed to release claim on PR failure for %s: %s", proposal.proposal_id, rev_err)
                    raise RuntimeError(f"GitHub PR creation failed for proposal '{proposal.proposal_id}': {pr_err}") from pr_err

                final_proposal = claimed_proposal.model_copy(deep=True)
                final_proposal.status = RemediationStatus.PR_CREATED
                final_proposal.github_branch = pr_info.get("branch")
                final_proposal.github_pr_number = pr_info.get("pr_number")
                final_proposal.github_pr_url = pr_info.get("pr_url")
                final_proposal.applied_commit_sha = pr_info.get("commit_sha")

                finalized = self.store.atomic_transition_status(
                    proposal_id=proposal.proposal_id,
                    expected_statuses=[RemediationStatus.APPLICATION_IN_PROGRESS.value],
                    new_status=RemediationStatus.PR_CREATED.value,
                    updated_proposal=final_proposal,
                )
                if not finalized:
                    fresh = self.store.get_proposal(proposal.proposal_id)
                    if fresh and fresh.status == RemediationStatus.PR_CREATED:
                        return fresh
                    raise RuntimeError(
                        f"CRITICAL: PR '{final_proposal.github_pr_url}' was created on GitHub, but atomic status transition "
                        f"to PR_CREATED failed. Manual reconciliation required."
                    )
                logger.info(
                    "Remediation proposal %s PR created: url=%s, branch=%s, commit=%s",
                    proposal.proposal_id,
                    final_proposal.github_pr_url,
                    final_proposal.github_branch,
                    final_proposal.applied_commit_sha,
                )
                return final_proposal

            elif commit_to_main:
                raise PermissionError(
                    "Security policy violation: direct commits to 'main' branch are strictly prohibited. "
                    "All remediation approvals must create a reviewed GitHub Pull Request via create_pr=True."
                )

            else:
                # commit_to_main is False (Simulation or staging)
                target_status = RemediationStatus.SIMULATED_APPROVED if is_simulated else RemediationStatus.HUMAN_APPROVED
                target_proposal = proposal.model_copy(deep=True)
                target_proposal.is_approved_by_human = is_authenticated
                target_proposal.is_simulated_approval = is_simulated
                target_proposal.approval_mode = "SIMULATED" if is_simulated else "AUTHENTICATED"
                target_proposal.approved_by = verified_identity
                target_proposal.approved_at = datetime.now(timezone.utc)
                target_proposal.status = target_status
                target_proposal.applied_commit_sha = None

                transitioned = self.store.atomic_transition_status(
                    proposal_id=proposal.proposal_id,
                    expected_statuses=[
                        RemediationStatus.PENDING_HUMAN_APPROVAL.value,
                        RemediationStatus.POLICY_APPROVED.value,
                    ],
                    new_status=target_status.value,
                    updated_proposal=target_proposal,
                )
                if not transitioned:
                    fresh = self.store.get_proposal(proposal.proposal_id)
                    fresh_status = fresh.status.value if fresh else "UNKNOWN"
                    raise PermissionError(
                        f"Cannot approve proposal '{proposal.proposal_id}': status concurrently modified to '{fresh_status}'."
                    )
                logger.info(
                    "Remediation proposal %s for %s was approved by '%s' (mode=%s, status=%s).",
                    proposal.proposal_id,
                    proposal.workload,
                    verified_identity,
                    "SIMULATION" if is_simulated else "AUTHENTICATED",
                    target_status.value,
                )
                return target_proposal

    def reject_remediation(
        self,
        proposal_id: str,
        reason: str,
        operator: Optional[str] = None,
        approval_token: Optional[str] = None,
        is_simulation: bool = False,
    ) -> RemediationProposal:
        """
        Explicitly and securely rejects a remediation proposal.
        Requires authenticated operator identity (or explicit simulation mode).
        Fails closed if the proposal was already applied to main, in-progress, or if authentication fails.
        Uses atomic state transitions in DynamoDB to eliminate race conditions.
        """
        with self._apply_lock:
            proposal = self.store.get_proposal(proposal_id)
            if not proposal:
                raise ValueError(f"Remediation proposal '{proposal_id}' not found in store.")

            if proposal.status in (RemediationStatus.APPLIED_TO_MAIN, RemediationStatus.PR_CREATED):
                raise PermissionError(
                    f"Cannot reject proposal '{proposal_id}': proposal is already finalized with status {proposal.status.value}."
                )

            if proposal.status == RemediationStatus.APPLICATION_IN_PROGRESS:
                raise PermissionError(
                    f"Cannot reject proposal '{proposal_id}': application is currently in progress."
                )

            # Idempotent rejection check
            if proposal.status == RemediationStatus.OPERATOR_REJECTED:
                logger.info("Proposal %s is already rejected. Rejection is idempotent.", proposal_id)
                return proposal

            # Authenticate operator
            if is_simulation:
                if not operator or not isinstance(operator, str) or not operator.strip():
                    raise PermissionError("Simulated human operator identifier required for offline simulation.")
                verified_identity = f"[SIMULATED] {operator.strip()}"
            else:
                if self.approval_authenticator is None:
                    raise PermissionError(
                        "Unauthenticated rejection rejected: no trusted human identity mechanism is configured. "
                        "Caller-supplied operator strings alone cannot reject proposals."
                    )
                authenticated, result_or_err = self.approval_authenticator.authenticate(
                    proposal=proposal,
                    approval_token=approval_token,
                    operator=operator,
                )
                if not authenticated:
                    raise PermissionError(f"Human rejection authentication failed: {result_or_err}.")
                verified_identity = result_or_err

            # Transition state atomically
            now_utc = datetime.now(timezone.utc)
            rejected_proposal = proposal.model_copy(deep=True)
            rejected_proposal.status = RemediationStatus.OPERATOR_REJECTED
            rejected_proposal.rejected_by = verified_identity
            rejected_proposal.rejected_at = now_utc
            rejected_proposal.rejection_reason = reason
            rejected_proposal.policy_reason = (rejected_proposal.policy_reason or "") + f" | Operator rejection by {verified_identity}: {reason}"

            expected = [
                RemediationStatus.PENDING_HUMAN_APPROVAL.value,
                RemediationStatus.POLICY_APPROVED.value,
                RemediationStatus.PROPOSED.value,
            ]
            transitioned = self.store.atomic_transition_status(
                proposal_id=proposal_id,
                expected_statuses=expected,
                new_status=RemediationStatus.OPERATOR_REJECTED.value,
                updated_proposal=rejected_proposal,
            )
            if not transitioned:
                fresh = self.store.get_proposal(proposal_id)
                if fresh and fresh.status == RemediationStatus.OPERATOR_REJECTED:
                    return fresh
                if fresh and fresh.status in (RemediationStatus.APPLICATION_IN_PROGRESS, RemediationStatus.APPLIED_TO_MAIN, RemediationStatus.HUMAN_APPROVED):
                    raise PermissionError(
                        f"Cannot reject proposal '{proposal_id}': concurrently approved or applied (status: {fresh.status.value})."
                    )
                raise PermissionError(
                    f"Concurrent modification: proposal '{proposal_id}' status changed to '{fresh.status.value if fresh else 'UNKNOWN'}'."
                )

            logger.info("Remediation proposal %s was rejected by '%s': %s", proposal_id, verified_identity, reason)
            return rejected_proposal

    def recover_in_progress_proposal(
        self,
        proposal_id: str,
        operator: Optional[str] = None,
        approval_token: Optional[str] = None,
        is_simulation: bool = False,
    ) -> RemediationProposal:
        """
        Safely and authoritatively recovers a proposal stuck in APPLICATION_IN_PROGRESS.
        Verifies:
        1. Human operator is authenticated (or simulation).
        2. Authoritative check on GitHub: if commit landed, reconciles to APPLIED_TO_MAIN preserving provenance.
        3. If GitHub check fails with an error: fails closed (cannot recover ambiguous state).
        4. If GitHub confirms NO commit landed: atomically transitions status back to PENDING_HUMAN_APPROVAL.
        """
        with self._apply_lock:
            proposal = self.store.get_proposal(proposal_id)
            if not proposal:
                raise ValueError(f"Remediation proposal '{proposal_id}' not found in store.")

            if proposal.status == RemediationStatus.APPLIED_TO_MAIN:
                logger.info("Proposal %s is already APPLIED_TO_MAIN.", proposal_id)
                return proposal

            if proposal.status == RemediationStatus.OPERATOR_REJECTED:
                raise PermissionError(f"Cannot recover rejected proposal '{proposal_id}' (status: OPERATOR_REJECTED).")

            if proposal.status != RemediationStatus.APPLICATION_IN_PROGRESS:
                logger.info("Proposal %s is not in progress (status: %s).", proposal_id, proposal.status.value)
                return proposal

            # Authenticate operator
            if is_simulation:
                if not operator or not isinstance(operator, str) or not operator.strip():
                    raise PermissionError("Simulated human operator identifier required for offline simulation.")
                verified_identity = f"[SIMULATED] {operator.strip()}"
            else:
                if self.approval_authenticator is None:
                    raise PermissionError("Unauthenticated recovery rejected: no trusted human identity mechanism configured.")
                authenticated, result_or_err = self.approval_authenticator.authenticate(
                    proposal=proposal,
                    approval_token=approval_token,
                    operator=operator,
                )
                if not authenticated:
                    raise PermissionError(f"Human operator recovery authentication failed: {result_or_err}.")
                verified_identity = result_or_err

            # Authoritative check on GitHub
            if not self.github_provider:
                raise RuntimeError(f"Cannot verify proposal '{proposal_id}' on GitHub: no GitHub provider configured.")

            try:
                commit_sha = self.github_provider.find_commit_for_proposal(proposal_id=proposal_id)
            except Exception as e:
                raise RuntimeError(
                    f"Cannot recover proposal '{proposal_id}': GitHub verification failed ({e}). State remains ambiguous."
                ) from e

            if commit_sha:
                # Commit actually landed! Reconcile to APPLIED_TO_MAIN preserving provenance
                reconciled = proposal.model_copy(deep=True)
                reconciled.is_approved_by_human = True if proposal.is_approved_by_human else not is_simulation
                reconciled.is_simulated_approval = is_simulation
                reconciled.approval_mode = proposal.approval_mode or ("SIMULATED" if is_simulation else "AUTHENTICATED")
                reconciled.approved_by = proposal.approved_by or verified_identity
                reconciled.approved_at = proposal.approved_at or datetime.now(timezone.utc)
                reconciled.status = RemediationStatus.APPLIED_TO_MAIN
                reconciled.applied_commit_sha = commit_sha
                self.store.atomic_transition_status(
                    proposal_id=proposal_id,
                    expected_statuses=[RemediationStatus.APPLICATION_IN_PROGRESS.value],
                    new_status=RemediationStatus.APPLIED_TO_MAIN.value,
                    updated_proposal=reconciled,
                )
                logger.info("Recovered proposal %s: reconciled to APPLIED_TO_MAIN (commit: %s).", proposal_id, commit_sha)
                return reconciled

            # No commit on GitHub: safe to release claim back to PENDING_HUMAN_APPROVAL
            recovered = proposal.model_copy(deep=True)
            recovered.status = RemediationStatus.PENDING_HUMAN_APPROVAL
            recovered.policy_reason = (recovered.policy_reason or "") + f" | Recovered from stale in-progress claim by {verified_identity}"
            transitioned = self.store.atomic_transition_status(
                proposal_id=proposal_id,
                expected_statuses=[RemediationStatus.APPLICATION_IN_PROGRESS.value],
                new_status=RemediationStatus.PENDING_HUMAN_APPROVAL.value,
                updated_proposal=recovered,
            )
            if not transitioned:
                fresh = self.store.get_proposal(proposal_id)
                raise PermissionError(
                    f"Recovery transition failed: proposal '{proposal_id}' status concurrently changed to '{fresh.status.value if fresh else 'UNKNOWN'}'."
                )
            logger.info("Recovered proposal %s: released claim back to PENDING_HUMAN_APPROVAL by '%s'.", proposal_id, verified_identity)
            return recovered

    def _extract_workload(self, rca: RootCauseAnalysis, incident: Optional[Dict[str, Any]]) -> str:
        """Determines target workload from incident context or RCA evidence."""
        if incident and incident.get("affected_workload"):
            raw = str(incident["affected_workload"]).strip().lower()
            if raw in WORKLOAD_MANIFEST_MAP:
                return raw
            candidate = raw.removeprefix("boutique-")
            if candidate in WORKLOAD_MANIFEST_MAP:
                return candidate

            # Match against allowlisted workloads when pod names include ReplicaSet/Pod hashes
            # (e.g. 'boutique-canary-5c9d488bb5-pnt2d' -> 'boutique-canary' or 'canary')
            for key in sorted(WORKLOAD_MANIFEST_MAP.keys(), key=len, reverse=True):
                if raw == key or raw.startswith(f"{key}-"):
                    return key
                if candidate == key or candidate.startswith(f"{key}-"):
                    return key

            return candidate
        text = f"{rca.root_cause} {rca.summary}".lower()
        for svc in sorted(WORKLOAD_MANIFEST_MAP.keys(), key=len, reverse=True):
            if svc in text:
                return svc
        return "unknown"

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
            target_c = workload.removeprefix("boutique-")
            params = RemediationParameters(memory_request="256Mi", memory_limit="512Mi", target_container=target_c)
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
