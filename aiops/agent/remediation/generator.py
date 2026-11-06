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
        if is_simulation and commit_to_main:
            raise PermissionError(
                "Security violation: offline simulation mode cannot commit to real GitHub repository. "
                "Production commits require authentic human operator verification."
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
            if commit_to_main:
                if not self.github_provider:
                    raise RuntimeError(
                        f"Cannot commit remediation proposal '{proposal.proposal_id}' to main: no GitHub provider or credentials configured."
                    )

                # Check if already committed on GitHub (idempotent reconciliation)
                try:
                    existing_commit_sha = self.github_provider.find_commit_for_proposal(
                        proposal_id=proposal.proposal_id,
                    )
                except Exception as precheck_err:
                    if proposal.status == RemediationStatus.APPLICATION_IN_PROGRESS:
                        raise RuntimeError(
                            f"Cannot inspect in-progress proposal '{proposal_id}': GitHub verification failed ({precheck_err}). "
                            "Status remains APPLICATION_IN_PROGRESS to prevent races."
                        ) from precheck_err
                    logger.debug("Pre-claim commit check failed: %s", precheck_err)
                    existing_commit_sha = None
                if existing_commit_sha:
                    logger.info(
                        "Remediation proposal %s was already committed to 'main' in commit %s. Reconciling proposal state.",
                        proposal_id,
                        existing_commit_sha,
                    )
                    reconciled = proposal.model_copy(deep=True)
                    reconciled.is_approved_by_human = True if proposal.is_approved_by_human else is_authenticated
                    reconciled.is_simulated_approval = proposal.is_simulated_approval if proposal.is_simulated_approval is not None else is_simulated
                    reconciled.approval_mode = proposal.approval_mode or ("SIMULATED" if is_simulated else "AUTHENTICATED")
                    reconciled.approved_by = proposal.approved_by or verified_identity
                    reconciled.approved_at = proposal.approved_at or datetime.now(timezone.utc)
                    reconciled.status = RemediationStatus.APPLIED_TO_MAIN
                    reconciled.applied_commit_sha = existing_commit_sha

                    reconcile_statuses = [
                        RemediationStatus.PENDING_HUMAN_APPROVAL.value,
                        RemediationStatus.POLICY_APPROVED.value,
                        RemediationStatus.APPLICATION_IN_PROGRESS.value,
                    ]
                    reconciled_ok = self.store.atomic_transition_status(
                        proposal_id=proposal.proposal_id,
                        expected_statuses=reconcile_statuses,
                        new_status=RemediationStatus.APPLIED_TO_MAIN.value,
                        updated_proposal=reconciled,
                    )
                    if not reconciled_ok:
                        fresh = self.store.get_proposal(proposal.proposal_id)
                        if fresh and fresh.status == RemediationStatus.APPLIED_TO_MAIN:
                            return fresh
                        logger.warning(
                            "Reconciliation transition could not be finalized for %s (current status: %s).",
                            proposal_id,
                            fresh.status.value if fresh else "UNKNOWN",
                        )
                    return reconciled

                if proposal.status == RemediationStatus.APPLICATION_IN_PROGRESS:
                    raise PermissionError(
                        f"Cannot apply proposal '{proposal_id}': proposal is currently in progress (APPLICATION_IN_PROGRESS, claimed by '{proposal.approved_by}'). "
                        "No GitHub commit was found. Use explicit operator recovery or wait for lease to expire."
                    )

                # ATOMIC CLAIM: Reserve proposal before live commit to prevent race with rejections/competing approvals
                claimed_proposal = proposal.model_copy(deep=True)
                claimed_proposal.status = RemediationStatus.APPLICATION_IN_PROGRESS
                claimed_proposal.approved_by = verified_identity
                claimed_proposal.is_approved_by_human = is_authenticated
                claimed_proposal.is_simulated_approval = is_simulated
                claimed_proposal.approval_mode = "AUTHENTICATED"
                claimed_proposal.approved_at = datetime.now(timezone.utc)

                allowed_pre_claim_statuses = [
                    RemediationStatus.PENDING_HUMAN_APPROVAL.value,
                    RemediationStatus.POLICY_APPROVED.value,
                ]
                claimed = self.store.atomic_transition_status(
                    proposal_id=proposal.proposal_id,
                    expected_statuses=allowed_pre_claim_statuses,
                    new_status=RemediationStatus.APPLICATION_IN_PROGRESS.value,
                    updated_proposal=claimed_proposal,
                )
                if not claimed:
                    fresh = self.store.get_proposal(proposal.proposal_id)
                    fresh_status = fresh.status.value if fresh else "UNKNOWN"
                    if fresh and fresh.status == RemediationStatus.OPERATOR_REJECTED:
                        raise PermissionError(
                            f"Cannot apply proposal '{proposal.proposal_id}': proposal was rejected by operator ({fresh.rejected_by})."
                        )
                    if fresh and fresh.status == RemediationStatus.APPLIED_TO_MAIN:
                        return fresh
                    if fresh and fresh.status == RemediationStatus.APPLICATION_IN_PROGRESS:
                        raise PermissionError(
                            f"Concurrent claim conflict: proposal '{proposal.proposal_id}' is already claimed by '{fresh.approved_by}' (APPLICATION_IN_PROGRESS)."
                        )
                    raise PermissionError(
                        f"Concurrent state conflict: proposal '{proposal.proposal_id}' status is now '{fresh_status}'."
                    )

                # Now perform live GitHub commit with CAS
                commit_msg = (
                    f"fix(gitops): apply approved {proposal.action_type.value} for {proposal.workload}\n\n"
                    f"Proposal-ID: {proposal.proposal_id}\n"
                    f"Incident: {proposal.incident_id}\n"
                    f"Episode: {proposal.episode_id}\n"
                    f"Approved-by: {verified_identity}\n"
                    f"Mode: AUTHENTICATED\n"
                    f"Action: {rendered.summary}"
                )
                new_commit_sha = None
                try:
                    default_branch = self.github_provider.get_default_branch()
                    parent_sha = self.github_provider.get_branch_head_sha(default_branch)
                    new_commit_sha = self.github_provider.commit_to_main(
                        files=rendered.modified_files,
                        commit_message=commit_msg,
                        expected_parent_sha=parent_sha,
                    )
                except Exception as commit_err:
                    # Check if the commit landed despite an exception
                    recheck_error = None
                    rechecked_sha = None
                    try:
                        rechecked_sha = self.github_provider.find_commit_for_proposal(proposal_id=proposal.proposal_id)
                    except Exception as chk_err:
                        recheck_error = chk_err

                    if rechecked_sha:
                        new_commit_sha = rechecked_sha
                    elif recheck_error is not None:
                        # Ambiguous outcome: commit failed and status check also failed.
                        # Fail closed: retain APPLICATION_IN_PROGRESS claim to prevent races/duplicate commits.
                        logger.error(
                            "Ambiguous GitHub API outcome for proposal %s: commit failed (%s) and authoritative verification failed (%s). "
                            "Retaining APPLICATION_IN_PROGRESS claim.",
                            proposal.proposal_id,
                            commit_err,
                            recheck_error,
                        )
                        raise RuntimeError(
                            f"Ambiguous GitHub API outcome for proposal '{proposal.proposal_id}': commit failed ({commit_err}) "
                            f"and authoritative verification failed ({recheck_error}). Claim retained in APPLICATION_IN_PROGRESS "
                            f"to prevent duplicate execution. Manual operator investigation required."
                        ) from commit_err
                    else:
                        # Authoritative check confirmed commit did NOT land
                        # Revert in-progress reservation back to PENDING_HUMAN_APPROVAL so operator can retry
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
                            logger.error("Failed to release in-progress reservation for %s: %s", proposal.proposal_id, rev_err)
                        raise RuntimeError(f"GitHub commit failed for proposal '{proposal.proposal_id}': {commit_err}") from commit_err

                # ATOMIC FINALIZE: Transition from APPLICATION_IN_PROGRESS -> APPLIED_TO_MAIN
                final_proposal = claimed_proposal.model_copy(deep=True)
                final_proposal.status = RemediationStatus.APPLIED_TO_MAIN
                final_proposal.applied_commit_sha = new_commit_sha

                finalized = self.store.atomic_transition_status(
                    proposal_id=proposal.proposal_id,
                    expected_statuses=[RemediationStatus.APPLICATION_IN_PROGRESS.value],
                    new_status=RemediationStatus.APPLIED_TO_MAIN.value,
                    updated_proposal=final_proposal,
                )
                if not finalized:
                    fresh = self.store.get_proposal(proposal.proposal_id)
                    if fresh and fresh.status == RemediationStatus.APPLIED_TO_MAIN:
                        return fresh
                    raise RuntimeError(
                        f"CRITICAL: Commit '{new_commit_sha}' was pushed to GitHub 'main', but atomic status transition "
                        f"to APPLIED_TO_MAIN failed (current store status: {fresh.status.value if fresh else 'UNKNOWN'}). "
                        f"Unconditional overwrite denied. Manual operator reconciliation required."
                    )

                logger.info(
                    "Remediation proposal %s for %s was approved by '%s' and applied to 'main' (commit: %s).",
                    proposal.proposal_id,
                    proposal.workload,
                    verified_identity,
                    new_commit_sha,
                )
                return final_proposal

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

            if proposal.status == RemediationStatus.APPLIED_TO_MAIN:
                raise PermissionError(
                    f"Cannot reject proposal '{proposal_id}': already APPLIED_TO_MAIN (commit: {proposal.applied_commit_sha})."
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
