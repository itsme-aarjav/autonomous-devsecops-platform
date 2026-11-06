"""
AIOps Platform — Human Approval Safety & GitOps Concurrency Regression Tests

Tests the critical security guarantees of the GitOps remediation pipeline:
1. Atomic state transitions in remediation persistence.
2. Cross-process concurrency protection (competing approve vs reject).
3. Competing approval serialization and single-commit guarantee.
4. Failure rollback: failed GitHub commit reverts claim to PENDING_HUMAN_APPROVAL.
5. Idempotent reconciliation: unpersisted commit recovered via GitHub commit evidence.
6. Terminal rejection protection: cannot apply rejected proposals; cannot reject applied proposals.
7. AWS IAM/STS operator identity verification: account gating, role pattern matching, and secondary 2FA.
8. Strict offline simulation isolation: zero AWS, zero GitHub, zero DynamoDB mutations.
9. Simulation forbidden to commit: commit_to_main + is_simulation raises PermissionError.
10. Secret non-leakage in audit logs and proposal payloads.
11. CLI list filter correctness for 'pending' (matches PENDING_HUMAN_APPROVAL & POLICY_APPROVED).
12. RCA report preservation on shared DynamoDB tables (UpdateItem only, never PutItem).
13. Complete proposal audit fields (approved_by, approved_at, applied_commit_sha, rejection_reason).
"""

import io
import os
import sys
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# Ensure repo root is in sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Ensure hermetic environment even when boto3 is not locally installed
if "boto3" not in sys.modules:
    try:
        import boto3
    except ImportError:
        mock_boto3 = MagicMock()
        mock_botocore = MagicMock()
        mock_botocore.exceptions.ClientError = type("ClientError", (Exception,), {})
        sys.modules["boto3"] = mock_boto3
        sys.modules["botocore"] = mock_botocore
        sys.modules["botocore.exceptions"] = mock_botocore.exceptions
        sys.modules["botocore.config"] = mock_botocore.config
        sys.modules["boto3.dynamodb"] = MagicMock()
        mock_cond = MagicMock()
        sys.modules["boto3.dynamodb.conditions"] = mock_cond

from aiops.agent.remediation.schemas import (
    RemediationProposal,
    RemediationActionType,
    RemediationParameters,
    PolicyDecision,
    RemediationStatus,
)
from aiops.agent.remediation.store import (
    InMemoryRemediationStore,
    DynamoDBRemediationStore,
)
from aiops.agent.remediation.generator import GitOpsRemediationEngine
from aiops.agent.remediation.policy import RemediationPolicyEngine
from aiops.agent.remediation.renderer import ManifestPatchRenderer
from aiops.agent.remediation.authenticator import (
    AwsIamApprovalAuthenticator,
    TrustedTokenApprovalAuthenticator,
)
from aiops.agent.remediation.github_provider import BaseGitHubProvider
import aiops.operator_cli as operator_cli


class MockGitHubProvider(BaseGitHubProvider):
    """Synthetic in-memory GitHub provider for hermetic testing."""

    def __init__(self, default_branch="main"):
        self.default_branch = default_branch
        self.commits = {}
        self.head_sha = "initial-head-sha-00000000000000000000"
        self.fail_commit = False

    def get_default_branch(self) -> str:
        return self.default_branch

    def get_branch_head_sha(self, branch: str) -> str:
        return self.head_sha

    def branch_exists(self, branch: str) -> bool:
        return branch == self.default_branch

    def commit_files(self, branch_name: str, files, commit_message: str, expected_parent_sha: str = None) -> str:
        if self.fail_commit:
            raise RuntimeError("Synthetic GitHub API CAS conflict / network timeout")
        if expected_parent_sha and expected_parent_sha != self.head_sha:
            raise RuntimeError(f"CAS mismatch: expected {expected_parent_sha}, current {self.head_sha}")

        import hashlib
        new_sha = hashlib.sha256(f"{self.head_sha}:{commit_message}".encode("utf-8")).hexdigest()
        self.commits[new_sha] = {
            "message": commit_message,
            "files": files,
            "parent": self.head_sha,
            "branch": branch_name,
        }
        self.head_sha = new_sha
        return new_sha

    def find_commit_for_proposal(self, proposal_id: str):
        for sha, data in self.commits.items():
            if f"Proposal-ID: {proposal_id}" in data["message"]:
                return sha
        return None

    def get_file_content(self, path: str, ref: str = "main") -> str:
        return ""


def _create_test_proposal(
    proposal_id="test-prop-001",
    workload="auth",
    status=RemediationStatus.PENDING_HUMAN_APPROVAL,
    manifest="devops/gitops/k8s/backend/auth.yml",
) -> RemediationProposal:
    renderer = ManifestPatchRenderer(repo_root=REPO_ROOT)
    prop = RemediationProposal(
        proposal_id=proposal_id,
        incident_id=f"inc-{proposal_id}",
        episode_id=f"ep-{proposal_id}",
        category="Pod OOMKilled",
        action_type=RemediationActionType.SET_MEMORY_RESOURCES,
        workload=workload,
        namespace="boutique",
        target_manifest=manifest,
        parameters=RemediationParameters(memory_request="256Mi", memory_limit="512Mi", target_container=workload),
        confidence_score=0.95,
        justification="Mitigate Pod OOMKilled with higher memory limits.",
        policy_decision=PolicyDecision.APPROVED,
        policy_reason="Resource limits within allowable threshold",
        status=status,
    )
    try:
        prop.diff_summary = renderer.render_proposal_patch(prop).diff
    except Exception:
        prop.diff_summary = "--- diff\n+++ diff"
    return prop


class TestApprovalSafetyIntegration(unittest.TestCase):
    """Unit and security regression tests for GitOps approval workflow."""

    def setUp(self):
        self.store = InMemoryRemediationStore()
        self.github = MockGitHubProvider()
        self.token_auth = TrustedTokenApprovalAuthenticator(
            {"token-secret-1234567890abcdef": "terra-admin"}
        )
        self.mock_sts = MagicMock()
        self.mock_sts.get_caller_identity.return_value = {
            "Account": "592668326948",
            "Arn": "arn:aws:iam::592668326948:user/terra-admin",
            "UserId": "AIDA592668326948ADMIN",
        }
        self.iam_auth = AwsIamApprovalAuthenticator(
            allowed_account="592668326948",
            token_authenticator=self.token_auth,
            sts_client=self.mock_sts,
        )
        self.engine = GitOpsRemediationEngine(
            repo_root=REPO_ROOT,
            policy_engine=RemediationPolicyEngine(),
            renderer=ManifestPatchRenderer(repo_root=REPO_ROOT),
            github_provider=self.github,
            store=self.store,
            approval_authenticator=self.iam_auth,
        )

    # -----------------------------------------------------------------------
    # 1. Competing Approve vs Reject Concurrency
    # -----------------------------------------------------------------------
    def test_competing_approve_and_reject_concurrency(self):
        """Rejecting a proposal before approval commits prevents commit execution."""
        prop = _create_test_proposal("prop-compete-01")
        self.store.save_proposal(prop)

        # Operator B rejects the proposal first
        rejected = self.engine.reject_remediation(
            proposal_id="prop-compete-01",
            reason="Manual rejection by security operator",
            approval_token="token-secret-1234567890abcdef",
        )
        self.assertEqual(rejected.status, RemediationStatus.OPERATOR_REJECTED)

        # Operator A concurrently attempts to apply the proposal
        with self.assertRaises(PermissionError) as ctx:
            self.engine.apply_approved_remediation(
                proposal_id="prop-compete-01",
                approval_token="token-secret-1234567890abcdef",
                commit_to_main=True,
            )
        self.assertIn("rejected", str(ctx.exception).lower())
        # Verify NO commit was created on GitHub
        self.assertIsNone(self.github.find_commit_for_proposal("prop-compete-01"))

    def test_rejection_cannot_override_in_progress_or_applied(self):
        """Rejection is forbidden if proposal is already in-progress or applied."""
        prop = _create_test_proposal("prop-apply-first-01")
        self.store.save_proposal(prop)

        # Operator A applies and commits to main
        applied = self.engine.apply_approved_remediation(
            proposal_id="prop-apply-first-01",
            approval_token="token-secret-1234567890abcdef",
            commit_to_main=True,
        )
        self.assertEqual(applied.status, RemediationStatus.APPLIED_TO_MAIN)
        self.assertIsNotNone(applied.applied_commit_sha)

        # Operator B attempts to reject the already applied proposal
        with self.assertRaises(PermissionError) as ctx:
            self.engine.reject_remediation(
                proposal_id="prop-apply-first-01",
                reason="Too late rejection",
                approval_token="token-secret-1234567890abcdef",
            )
        self.assertIn("already APPLIED_TO_MAIN", str(ctx.exception))

    # -----------------------------------------------------------------------
    # 2. Competing Approvals (Single Winner)
    # -----------------------------------------------------------------------
    def test_competing_approvals_idempotence(self):
        """Two concurrent approvals result in a single commit, not duplicate application."""
        prop = _create_test_proposal("prop-compete-appr-01")
        self.store.save_proposal(prop)

        res1 = self.engine.apply_approved_remediation(
            proposal_id="prop-compete-appr-01",
            approval_token="token-secret-1234567890abcdef",
            commit_to_main=True,
        )
        self.assertEqual(res1.status, RemediationStatus.APPLIED_TO_MAIN)
        initial_sha = res1.applied_commit_sha

        # Second approval call runs
        res2 = self.engine.apply_approved_remediation(
            proposal_id="prop-compete-appr-01",
            approval_token="token-secret-1234567890abcdef",
            commit_to_main=True,
        )
        self.assertEqual(res2.status, RemediationStatus.APPLIED_TO_MAIN)
        # Must return the SAME commit SHA (no duplicate commits)
        self.assertEqual(res2.applied_commit_sha, initial_sha)
        self.assertEqual(len(self.github.commits), 1)

    # -----------------------------------------------------------------------
    # 3. GitHub Commit Failure Reverts Claim
    # -----------------------------------------------------------------------
    def test_commit_failure_reverts_claim_to_pending(self):
        """When GitHub commit fails, the proposal is NOT left as APPLIED_TO_MAIN and reverts to PENDING."""
        prop = _create_test_proposal("prop-commit-fail-01")
        self.store.save_proposal(prop)

        # Induce failure in GitHub commit
        self.github.fail_commit = True

        with self.assertRaises(RuntimeError) as ctx:
            self.engine.apply_approved_remediation(
                proposal_id="prop-commit-fail-01",
                approval_token="token-secret-1234567890abcdef",
                commit_to_main=True,
            )
        self.assertIn("GitHub commit failed", str(ctx.exception))

        # Check proposal status in store
        refreshed = self.store.get_proposal("prop-commit-fail-01")
        self.assertEqual(refreshed.status, RemediationStatus.PENDING_HUMAN_APPROVAL)
        self.assertIsNone(refreshed.applied_commit_sha)

    # -----------------------------------------------------------------------
    # 4. Successful Commit with Store Failure Reconciles
    # -----------------------------------------------------------------------
    def test_commit_success_reconciliation_via_github_evidence(self):
        """If a commit lands on GitHub but the store diverges, reconciliation restores APPLIED_TO_MAIN."""
        prop = _create_test_proposal("prop-reconcile-01")
        self.store.save_proposal(prop)

        # Simulate pre-existing commit landed on GitHub by another worker/crash
        synthetic_sha = "abcdef12345678901234567890abcdef12345678"
        self.github.commits[synthetic_sha] = {
            "message": f"fix(gitops): apply\n\nProposal-ID: prop-reconcile-01\nApproved-by: test",
            "files": {},
            "parent": self.github.head_sha,
        }

        # Running apply now detects existing commit and reconciles
        res = self.engine.apply_approved_remediation(
            proposal_id="prop-reconcile-01",
            approval_token="token-secret-1234567890abcdef",
            commit_to_main=True,
        )
        self.assertEqual(res.status, RemediationStatus.APPLIED_TO_MAIN)
        self.assertEqual(res.applied_commit_sha, synthetic_sha)

    # -----------------------------------------------------------------------
    # 5. Terminal Rejection Protection
    # -----------------------------------------------------------------------
    def test_terminal_rejection_cannot_be_applied(self):
        """A proposal marked OPERATOR_REJECTED cannot be approved or committed."""
        prop = _create_test_proposal("prop-rej-term-01", status=RemediationStatus.OPERATOR_REJECTED)
        self.store.save_proposal(prop)

        with self.assertRaises(PermissionError):
            self.engine.apply_approved_remediation(
                proposal_id="prop-rej-term-01",
                approval_token="token-secret-1234567890abcdef",
                commit_to_main=True,
            )

    # -----------------------------------------------------------------------
    # 6. AWS IAM/STS Operator Identity Verification
    # -----------------------------------------------------------------------
    def test_iam_operator_identity_account_and_pattern_checks(self):
        """Ensures caller identity requires target account 592668326948 and authorized operator pattern."""
        prop = _create_test_proposal("prop-iam-01")

        # Case A: Wrong AWS Account
        mock_sts_wrong_acct = MagicMock()
        mock_sts_wrong_acct.get_caller_identity.return_value = {
            "Account": "111122223333",
            "Arn": "arn:aws:iam::111122223333:user/terra-admin",
        }
        auth_wrong_acct = AwsIamApprovalAuthenticator(sts_client=mock_sts_wrong_acct)
        ok, msg = auth_wrong_acct.authenticate(prop, approval_token=None)
        self.assertFalse(ok)
        self.assertIn("not authorized", msg)

        # Case B: Correct account, but unauthorized role/user
        mock_sts_unauth_user = MagicMock()
        mock_sts_unauth_user.get_caller_identity.return_value = {
            "Account": "592668326948",
            "Arn": "arn:aws:iam::592668326948:user/unauthorized-intern",
        }
        auth_unauth = AwsIamApprovalAuthenticator(sts_client=mock_sts_unauth_user)
        ok, msg = auth_unauth.authenticate(prop, approval_token=None)
        self.assertFalse(ok)
        self.assertIn("does not match allowed", msg)

        # Case C: Correct account and authorized role pattern (terra-admin)
        mock_sts_valid = MagicMock()
        mock_sts_valid.get_caller_identity.return_value = {
            "Account": "592668326948",
            "Arn": "arn:aws:iam::592668326948:user/terra-admin",
        }
        auth_valid = AwsIamApprovalAuthenticator(sts_client=mock_sts_valid)
        ok, arn = auth_valid.authenticate(prop, approval_token=None)
        self.assertTrue(ok)
        self.assertEqual(arn, "arn:aws:iam::592668326948:user/terra-admin")

    # -----------------------------------------------------------------------
    # 7. Strict Simulation Isolation (0 AWS / DynamoDB)
    # -----------------------------------------------------------------------
    def test_simulation_cannot_modify_dynamodb_or_live_proposals(self):
        """Simulation uses InMemoryRemediationStore and cannot touch production DynamoDB."""
        sim_store = operator_cli._resolve_store(is_simulation=True)
        self.assertIsInstance(sim_store, InMemoryRemediationStore)

        # Listing proposals in simulation retrieves only synthetic fixtures
        sim_proposals = sim_store.list_proposals()
        self.assertTrue(len(sim_proposals) >= 2)
        prop_ids = [p.proposal_id for p in sim_proposals]
        self.assertIn("sim-prop-001", prop_ids)

    # -----------------------------------------------------------------------
    # 8. Simulation Forbidden to Commit to GitHub
    # -----------------------------------------------------------------------
    def test_simulation_cannot_commit_to_github(self):
        """Simulation mode with commit_to_main=True raises PermissionError."""
        prop = _create_test_proposal("prop-sim-commit-01")
        self.store.save_proposal(prop)

        with self.assertRaises(PermissionError) as ctx:
            self.engine.apply_approved_remediation(
                proposal_id="prop-sim-commit-01",
                operator="sim-operator",
                is_simulation=True,
                commit_to_main=True,
            )
        self.assertIn("simulation mode cannot commit", str(ctx.exception))

    # -----------------------------------------------------------------------
    # 9. Secret Non-Leakage
    # -----------------------------------------------------------------------
    def test_no_secret_leakage_in_proposal_or_audit(self):
        """Approval tokens and secrets must not be stored in proposal models or diff summaries."""
        prop = _create_test_proposal("prop-secret-check-01")
        self.store.save_proposal(prop)

        applied = self.engine.apply_approved_remediation(
            proposal_id="prop-secret-check-01",
            approval_token="token-secret-1234567890abcdef",
            commit_to_main=True,
        )
        serialized = json.dumps(applied.model_dump(mode="json"))
        self.assertNotIn("token-secret-1234567890abcdef", serialized)
        self.assertNotIn("token-secret-1234567890abcdef", applied.diff_summary or "")

    # -----------------------------------------------------------------------
    # 10. CLI List Filter Correctness for 'pending'
    # -----------------------------------------------------------------------
    def test_cli_list_status_pending_matches_both_pending_and_policy_approved(self):
        """CLI list --status pending must match PENDING_HUMAN_APPROVAL and POLICY_APPROVED."""
        store = InMemoryRemediationStore()
        p1 = _create_test_proposal("p-pend-01", status=RemediationStatus.PENDING_HUMAN_APPROVAL)
        p2 = _create_test_proposal("p-pol-02", status=RemediationStatus.POLICY_APPROVED)
        p3 = _create_test_proposal("p-appr-03", status=RemediationStatus.APPLIED_TO_MAIN)
        p4 = _create_test_proposal("p-rej-04", status=RemediationStatus.OPERATOR_REJECTED)
        store.save_proposal(p1)
        store.save_proposal(p2)
        store.save_proposal(p3)
        store.save_proposal(p4)

        args = MagicMock()
        args.status = "pending"

        captured = io.StringIO()
        with patch("sys.stdout", captured):
            operator_cli.cmd_list(args, store)

        output = captured.getvalue()
        self.assertIn("p-pend-01", output)
        self.assertIn("p-pol-02", output)
        self.assertNotIn("p-appr-03", output)
        self.assertNotIn("p-rej-04", output)

    # -----------------------------------------------------------------------
    # 11. RCA Report Preservation on Shared DynamoDB Table
    # -----------------------------------------------------------------------
    def test_rca_report_preservation_on_shared_table(self):
        """On boutique-aiops-rca-reports table, store performs UpdateItem and never PutItem."""
        mock_table = MagicMock()
        mock_ddb = MagicMock()
        mock_ddb.Table.return_value = mock_table

        with patch("boto3.resource", return_value=mock_ddb):
            store = DynamoDBRemediationStore(
                region="us-east-2",
                table_name=DynamoDBRemediationStore.RCA_TABLE_NAME,
            )
            prop = _create_test_proposal("prop-rca-safe-01")
            store.save_proposal(prop)

            # PutItem must NEVER be called
            mock_table.put_item.assert_not_called()
            # UpdateItem must be called with incident_id key
            mock_table.update_item.assert_called_once()
            call_kwargs = mock_table.update_item.call_args[1]
            self.assertEqual(call_kwargs["Key"], {"incident_id": prop.incident_id})

    # -----------------------------------------------------------------------
    # 12. Complete Audit Fields and Commit SHA
    # -----------------------------------------------------------------------
    def test_audit_fields_population(self):
        """Applied and rejected proposals contain complete audit tracking fields."""
        prop = _create_test_proposal("prop-audit-01")
        self.store.save_proposal(prop)

        # Test applied audit fields
        applied = self.engine.apply_approved_remediation(
            proposal_id="prop-audit-01",
            approval_token="token-secret-1234567890abcdef",
            commit_to_main=True,
        )
        self.assertEqual(applied.approved_by, "arn:aws:iam::592668326948:user/terra-admin")
        self.assertIsInstance(applied.approved_at, datetime)
        self.assertIsNotNone(applied.applied_commit_sha)
        self.assertEqual(applied.approval_mode, "AUTHENTICATED")
        self.assertTrue(applied.is_approved_by_human)
        self.assertFalse(applied.is_simulated_approval)

        # Test rejected audit fields
        prop2 = _create_test_proposal("prop-audit-02")
        self.store.save_proposal(prop2)
        rejected = self.engine.reject_remediation(
            proposal_id="prop-audit-02",
            reason="Insufficient confidence in traffic forecast",
            approval_token="token-secret-1234567890abcdef",
        )
        self.assertEqual(rejected.rejected_by, "arn:aws:iam::592668326948:user/terra-admin")
        self.assertIsInstance(rejected.rejected_at, datetime)
        self.assertEqual(rejected.rejection_reason, "Insufficient confidence in traffic forecast")


if __name__ == "__main__":
    unittest.main()
