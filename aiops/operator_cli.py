#!/usr/bin/env python3
"""
Autonomous AIOps Platform — Cloud Operator Approval CLI

Provides a secure, CloudShell-ready interface for reviewing and approving or rejecting
human-gated GitOps remediation proposals.

Usage:
  python3 operator_cli.py list [--status pending|all]
  python3 operator_cli.py show <proposal_id>
  python3 operator_cli.py approve <proposal_id>
  python3 operator_cli.py reject <proposal_id> [--reason "text"]
  python3 operator_cli.py status <proposal_id>

Security:
  - Approval token is NEVER accepted as a CLI argument.
  - Token is read from AIOPS_APPROVAL_TOKEN env var or prompted securely via getpass.
  - GitHub token is read from AIOPS_GITHUB_TOKEN env var (never CLI).
  - All operations use the existing GitOpsRemediationEngine policy and auth paths.
  - Idempotent: approving an already-applied proposal prints the existing commit SHA and exits 0.
"""

import argparse
import getpass
import json
import logging
import os
import sys
from typing import Optional

# Ensure repository root is on sys.path for direct CloudShell / CLI invocation
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

logger = logging.getLogger("aiops.operator_cli")
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")


def _resolve_store(is_simulation: bool = False):
    """
    Selects the remediation store backend.
    In simulation mode, UNCONDITIONALLY returns an in-memory store pre-populated
    with realistic synthetic mock proposals. NEVER touches DynamoDB or AWS resources.
    """
    if is_simulation:
        return _create_simulation_store()

    backend = os.getenv("AIOPS_STORE_BACKEND", "dynamodb").strip().lower()
    if backend == "dynamodb":
        from aiops.agent.remediation.store import DynamoDBRemediationStore
        region = os.getenv("AWS_DEFAULT_REGION", os.getenv("AWS_REGION", "us-east-2"))
        table = os.getenv("AIOPS_DYNAMODB_REMEDIATIONS_TABLE", "boutique-aiops-remediations")
        return DynamoDBRemediationStore(region=region, table_name=table)
    elif backend == "local":
        from aiops.agent.remediation.store import LocalFileRemediationStore
        base = os.getenv("AIOPS_LOCAL_STORE_DIR", "/tmp/aiops-investigations")
        return LocalFileRemediationStore(base_dir=base)
    elif backend == "memory":
        from aiops.agent.remediation.store import InMemoryRemediationStore
        return InMemoryRemediationStore()
    else:
        raise ValueError(f"Unsupported AIOPS_STORE_BACKEND: '{backend}'. Must be 'dynamodb', 'local', or 'memory'.")


def _create_simulation_store():
    """Builds an isolated in-memory store populated with realistic synthetic proposals."""
    from aiops.agent.remediation.store import InMemoryRemediationStore
    from aiops.agent.remediation.schemas import (
        RemediationProposal,
        RemediationActionType,
        RemediationParameters,
        PolicyDecision,
        RemediationStatus,
    )
    store = InMemoryRemediationStore()

    p1 = RemediationProposal(
        proposal_id="sim-prop-001",
        incident_id="sim-inc-001",
        episode_id="sim-ep-001",
        category="Pod OOMKilled",
        action_type=RemediationActionType.SET_MEMORY_RESOURCES,
        workload="auth",
        namespace="boutique",
        target_manifest="devops/gitops/k8s/backend/auth.yml",
        parameters=RemediationParameters(memory_request="256Mi", memory_limit="512Mi", target_container="auth"),
        confidence_score=0.95,
        justification="Scale container memory limits for auth to mitigate Pod OOMKilled condition.",
        policy_decision=PolicyDecision.APPROVED,
        policy_reason="Resource changes within deterministic policy limits",
        status=RemediationStatus.PENDING_HUMAN_APPROVAL,
    )
    p2 = RemediationProposal(
        proposal_id="sim-prop-002",
        incident_id="sim-inc-002",
        episode_id="sim-ep-002",
        category="High CPU utilization",
        action_type=RemediationActionType.SCALE_REPLICAS,
        workload="frontend",
        namespace="boutique",
        target_manifest="devops/gitops/k8s/frontend/frontend.yml",
        parameters=RemediationParameters(replicas=2),
        confidence_score=0.88,
        justification="Scale frontend deployment replicas to 2 to alleviate high CPU load.",
        policy_decision=PolicyDecision.APPROVED,
        policy_reason="Replica scaling within deterministic policy limits (1-5)",
        status=RemediationStatus.POLICY_APPROVED,
    )

    try:
        from aiops.agent.remediation.renderer import ManifestPatchRenderer
        renderer = ManifestPatchRenderer(repo_root=REPO_ROOT)
        p1.diff_summary = renderer.render_proposal_patch(p1).diff
        p2.diff_summary = renderer.render_proposal_patch(p2).diff
    except Exception as e:
        logger.debug("Could not render simulation diff: %s", e)

    p3 = RemediationProposal(
        proposal_id="sim-prop-003",
        incident_id="sim-inc-003",
        episode_id="sim-ep-003",
        category="Deployment replicas unavailable",
        action_type=RemediationActionType.SCALE_REPLICAS,
        workload="orders",
        namespace="boutique",
        target_manifest="devops/gitops/k8s/backend/orders.yml",
        parameters=RemediationParameters(replicas=1),
        confidence_score=0.91,
        justification="Restore baseline replica count for orders.",
        policy_decision=PolicyDecision.APPROVED,
        policy_reason="Policy approved",
        status=RemediationStatus.OPERATOR_REJECTED,
        rejected_by="[SIMULATED] test-operator",
        rejection_reason="Manual test rejection in simulation",
    )
    p4 = RemediationProposal(
        proposal_id="sim-prop-004",
        incident_id="sim-inc-004",
        episode_id="sim-ep-004",
        category="Pod OOMKilled",
        action_type=RemediationActionType.SET_MEMORY_RESOURCES,
        workload="payment",
        namespace="boutique",
        target_manifest="devops/gitops/k8s/backend/payment.yml",
        parameters=RemediationParameters(memory_request="256Mi", memory_limit="512Mi", target_container="payment"),
        confidence_score=0.94,
        justification="Mitigated OOMKilled on payment service.",
        policy_decision=PolicyDecision.APPROVED,
        policy_reason="Policy approved",
        status=RemediationStatus.APPLIED_TO_MAIN,
        applied_commit_sha="a1b2c3d4e5f678901234567890abcdef12345678",
        approved_by="arn:aws:iam::592668326948:user/terra-admin",
    )
    store.save_proposal(p1)
    store.save_proposal(p2)
    store.save_proposal(p3)
    store.save_proposal(p4)
    return store


def _resolve_authenticator(is_simulation: bool = False):
    """
    Builds the production authenticator:
    1. Binds authorization to authenticated AWS IAM/STS caller identity via AwsIamApprovalAuthenticator.
       Enforces target AWS Account (592668326948) and authorized operator roles/principals.
    2. If token credentials exist (via AIOPS_APPROVAL_TOKENS or AWS Secrets Manager),
       adds TrustedTokenApprovalAuthenticator as a secondary 2FA factor.
    """
    if is_simulation:
        return None

    from aiops.agent.remediation.authenticator import (
        AwsIamApprovalAuthenticator,
        TrustedTokenApprovalAuthenticator,
    )

    token_authenticator = None
    raw = os.getenv("AIOPS_APPROVAL_TOKENS", "").strip()
    authorized_operators: dict = {}
    if raw:
        for entry in raw.split(","):
            parts = entry.strip().split(":", 1)
            if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                authorized_operators[parts[0].strip()] = parts[1].strip()

    if not authorized_operators:
        try:
            import boto3
            region = os.getenv("AWS_DEFAULT_REGION", os.getenv("AWS_REGION", "us-east-2"))
            sm = boto3.client("secretsmanager", region_name=region)
            secret_value = sm.get_secret_value(SecretId="boutique/aiops/approval-tokens")
            secret_str = secret_value.get("SecretString", "")
            if secret_str:
                data = json.loads(secret_str)
                token_map = data.get("tokens", data)
                if isinstance(token_map, dict):
                    authorized_operators = {k.strip(): v.strip() for k, v in token_map.items() if k.strip() and v.strip()}
        except Exception as e:
            logger.debug("Could not fetch approval tokens from Secrets Manager: %s", e)

    if authorized_operators:
        token_authenticator = TrustedTokenApprovalAuthenticator(authorized_operators)

    return AwsIamApprovalAuthenticator(token_authenticator=token_authenticator)


def _resolve_approval_token(authenticator=None) -> Optional[str]:
    """
    Resolves the operator approval token when token authentication is configured.
    Env var first, then secure getpass prompt.
    """
    if authenticator and getattr(authenticator, "token_authenticator", None) is None:
        return None

    token = os.getenv("AIOPS_APPROVAL_TOKEN", "").strip()
    if token:
        return token
    try:
        token = getpass.getpass("Enter approval token (input hidden): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n[ABORTED] No approval token provided.", file=sys.stderr)
        sys.exit(1)
    if not token:
        print("[ERROR] Approval token cannot be empty.", file=sys.stderr)
        sys.exit(1)
    return token


def _resolve_github_provider(is_simulation: bool = False):
    """Builds GitHubApiProvider from AIOPS_GITHUB_TOKEN or AWS Secrets Manager."""
    if is_simulation:
        return None

    from aiops.agent.remediation.github_provider import GitHubApiProvider
    token = os.getenv("AIOPS_GITHUB_TOKEN", "").strip()
    repo = os.getenv("AIOPS_GITHUB_REPOSITORY", "itsme-aarjav/autonomous-devsecops-platform").strip()
    if not token:
        try:
            import boto3
            region = os.getenv("AWS_DEFAULT_REGION", os.getenv("AWS_REGION", "us-east-2"))
            sm = boto3.client("secretsmanager", region_name=region)
            secret_value = sm.get_secret_value(SecretId="boutique/aiops/github-token")
            secret_str = secret_value.get("SecretString", "")
            if secret_str:
                data = json.loads(secret_str)
                token = data.get("token", "").strip()
        except Exception as e:
            logger.debug("Could not fetch GitHub token from Secrets Manager: %s", e)

    if not token:
        print(
            "[ERROR] AIOPS_GITHUB_TOKEN is not set and could not be retrieved from\n"
            "        AWS Secrets Manager ('boutique/aiops/github-token').\n"
            "        Ensure AWS credentials or AIOPS_GITHUB_TOKEN are present.",
            file=sys.stderr,
        )
        sys.exit(1)
    return GitHubApiProvider(repository=repo, token=token)


def _build_engine(store, github_provider=None, authenticator=None):
    """Instantiates GitOpsRemediationEngine with full security wiring."""
    from aiops.agent.remediation.generator import GitOpsRemediationEngine
    from aiops.agent.remediation.policy import RemediationPolicyEngine
    from aiops.agent.remediation.renderer import ManifestPatchRenderer

    repo_root = os.getenv("AIOPS_GIT_REPO_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return GitOpsRemediationEngine(
        repo_root=repo_root,
        policy_engine=RemediationPolicyEngine(),
        renderer=ManifestPatchRenderer(repo_root=repo_root, github_provider=github_provider),
        github_provider=github_provider,
        store=store,
        approval_authenticator=authenticator,
    )


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------

def cmd_list(args, store):
    """Lists remediation proposals."""
    from aiops.agent.remediation.schemas import RemediationStatus
    proposals = store.list_proposals(limit=50)
    if not proposals:
        print("No remediation proposals found.")
        return

    raw_filter = (args.status or "all").strip().lower()
    shown = 0
    for p in proposals:
        if raw_filter == "pending":
            if p.status not in (RemediationStatus.PENDING_HUMAN_APPROVAL, RemediationStatus.POLICY_APPROVED):
                continue
        elif raw_filter == "applied":
            if p.status != RemediationStatus.APPLIED_TO_MAIN:
                continue
        elif raw_filter == "rejected":
            if p.status not in (RemediationStatus.POLICY_REJECTED, RemediationStatus.OPERATOR_REJECTED):
                continue
        elif raw_filter != "all" and p.status.value.lower() != raw_filter:
            continue

        print(
            f"  {p.proposal_id[:16]:<18}  {p.status.value:<26}  {p.workload:<16}  {p.category:<32}  "
            f"confidence={p.confidence_score:.0%}  {p.created_at.strftime('%Y-%m-%d %H:%M:%SZ')}"
        )
        shown += 1
    if shown == 0:
        print(f"No proposals matching status filter '{args.status}'.")


def cmd_show(args, store):
    """Shows full details of a proposal."""
    proposal = store.get_proposal(args.proposal_id)
    if not proposal:
        print(f"[ERROR] Proposal '{args.proposal_id}' not found.", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'='*70}")
    print(f"  Proposal ID   : {proposal.proposal_id}")
    print(f"  Incident ID   : {proposal.incident_id}")
    print(f"  Status        : {proposal.status.value}")
    print(f"  Workload      : {proposal.workload}")
    print(f"  Namespace     : {proposal.namespace}")
    print(f"  Category      : {proposal.category}")
    print(f"  Action Type   : {proposal.action_type.value}")
    print(f"  Confidence    : {proposal.confidence_score:.0%}")
    print(f"  Policy        : {proposal.policy_decision.value if proposal.policy_decision else 'N/A'}")
    print(f"  Policy Reason : {proposal.policy_reason or 'N/A'}")
    print(f"  Created At    : {proposal.created_at.strftime('%Y-%m-%d %H:%M:%SZ')}")
    print(f"  Justification : {proposal.justification}")
    if proposal.diff_summary:
        print(f"\n  Diff Preview:\n{'-'*70}")
        print(proposal.diff_summary)
    if proposal.applied_commit_sha:
        print(f"\n  Applied Commit: {proposal.applied_commit_sha}")
    print(f"{'='*70}\n")


def cmd_approve(args, store):
    """Reviews diff and applies a proposal to main after explicit confirmation."""
    proposal = store.get_proposal(args.proposal_id)
    if not proposal:
        print(f"[ERROR] Proposal '{args.proposal_id}' not found.", file=sys.stderr)
        sys.exit(1)

    from aiops.agent.remediation.schemas import RemediationStatus
    # Idempotent: already applied
    if proposal.status == RemediationStatus.APPLIED_TO_MAIN:
        print(f"[INFO] Proposal '{args.proposal_id}' is already applied to main.")
        if proposal.applied_commit_sha:
            print(f"       Commit SHA: {proposal.applied_commit_sha}")
        sys.exit(0)

    # Disallow approving rejected proposals
    if proposal.status in (RemediationStatus.POLICY_REJECTED, RemediationStatus.OPERATOR_REJECTED):
        print(
            f"[ERROR] Cannot approve rejected proposal '{args.proposal_id}' (status: {proposal.status.value}).",
            file=sys.stderr,
        )
        sys.exit(1)

    is_simulation = getattr(args, "simulate", False)
    explicit_commit = getattr(args, "commit", False)

    # Guard: --yes is strictly forbidden in production mode
    if not is_simulation and getattr(args, "yes", False):
        print(
            "[ERROR] Security policy violation: '--yes' flag is forbidden in production mode. "
            "Production approval strictly requires interactive human review and manual typing of 'APPROVE'. "
            "'--yes' is permitted only with '--simulate'.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Strict invariant: simulation CANNOT commit to real GitHub
    if is_simulation and explicit_commit:
        print(
            "[ERROR] Security violation: cannot combine --simulate with --commit. "
            "Simulation mode is strictly offline/mock-only and cannot mutate remote repositories.",
            file=sys.stderr,
        )
        sys.exit(1)

    if is_simulation:
        should_commit = False
        should_pr = True
        operator_id = getattr(args, "operator", None) or os.getenv("AIOPS_OPERATOR_ID", "simulation-operator")
        approval_token = None
        authenticator = None
        github_provider = None
        print(f"[NOTICE] Running in SIMULATION mode with operator '{operator_id}'.")
    else:
        # In real mode, approval proceeds via reviewed GitHub Pull Request (NEVER unreviewed direct main mutation)
        if explicit_commit:
            should_commit = True
            should_pr = False
        else:
            should_commit = False
            should_pr = True
        operator_id = None
        authenticator = _resolve_authenticator(is_simulation=False)
        approval_token = _resolve_approval_token(authenticator)
        github_provider = _resolve_github_provider(is_simulation=False)

    # Show diff for operator review
    cmd_show(args, store)

    # Explicit confirmation gate (skip only if --yes is passed in simulation mode)
    if not getattr(args, "yes", False):
        confirm = input("Review the diff above carefully. Type APPROVE to confirm: ").strip()
        if confirm != "APPROVE":
            print("[ABORTED] Approval cancelled. No changes applied.")
            sys.exit(0)

    engine = _build_engine(store, github_provider=github_provider, authenticator=authenticator)

    print(f"\n==> Applying proposal '{args.proposal_id}' (mode={'SIMULATION' if is_simulation else 'AUTHENTICATED'})...")
    result = engine.apply_approved_remediation(
        proposal_id=args.proposal_id,
        operator=operator_id if is_simulation else None,
        approval_token=approval_token,
        is_simulation=is_simulation,
        commit_to_main=should_commit,
        create_pr=should_pr,
        write_to_working_tree=False,
    )
    if result.status == RemediationStatus.PR_CREATED:
        print(f"[SUCCESS] Remediation Pull Request created successfully for human review!")
        print(f"          Approved by : {result.approved_by}")
        print(f"          Mode        : {result.approval_mode}")
        if result.approved_at:
            print(f"          Timestamp   : {result.approved_at.strftime('%Y-%m-%d %H:%M:%SZ')}")
        print(f"          Branch      : {result.github_branch}")
        print(f"          PR Number   : #{result.github_pr_number}")
        print(f"          PR URL      : {result.github_pr_url}")
        if result.applied_commit_sha:
            print(f"          Commit SHA  : {result.applied_commit_sha}")
        print(f"\n[NEXT STEPS FOR OPERATOR]")
        print(f"  1. Review the Pull Request at: {result.github_pr_url}")
        print(f"  2. Inspect the diff and merge into 'main' to trigger Argo CD / GitOps rollout.")
        print(f"  3. Verify the deployment in EKS namespace '{result.namespace}'.")
    elif result.status == RemediationStatus.APPLIED_TO_MAIN:
        print(f"[SUCCESS] Proposal applied directly to main.")
        print(f"          Approved by : {result.approved_by}")
        print(f"          Mode        : {result.approval_mode}")
        if result.approved_at:
            print(f"          Timestamp   : {result.approved_at.strftime('%Y-%m-%d %H:%M:%SZ')}")
        if result.applied_commit_sha:
            print(f"          Commit SHA  : {result.applied_commit_sha}")
    elif result.status == RemediationStatus.SIMULATED_APPROVED:
        print(f"[SUCCESS] Proposal approved in offline SIMULATION mode.")
        print(f"          Simulated by: {result.approved_by}")
        if result.approved_at:
            print(f"          Timestamp   : {result.approved_at.strftime('%Y-%m-%d %H:%M:%SZ')}")
    elif result.status == RemediationStatus.HUMAN_APPROVED:
        print(f"[SUCCESS] Proposal human approved (commit pending).")
        print(f"          Approved by : {result.approved_by}")
    else:
        print(f"[ERROR] Apply did not reach successful state. Final status: {result.status.value}", file=sys.stderr)
        sys.exit(1)


def cmd_reject(args, store):
    """Records authenticated rejection of a proposal."""
    proposal = store.get_proposal(args.proposal_id)
    if not proposal:
        print(f"[ERROR] Proposal '{args.proposal_id}' not found.", file=sys.stderr)
        sys.exit(1)

    from aiops.agent.remediation.schemas import RemediationStatus

    if proposal.status == RemediationStatus.APPLIED_TO_MAIN:
        print(
            f"[ERROR] Proposal '{args.proposal_id}' is already APPLIED_TO_MAIN (commit: {proposal.applied_commit_sha}) and cannot be rejected.",
            file=sys.stderr,
        )
        sys.exit(1)

    if proposal.status == RemediationStatus.OPERATOR_REJECTED:
        print(f"[INFO] Proposal '{args.proposal_id}' is already rejected. Rejection is idempotent.")
        sys.exit(0)

    # Show proposal details before confirmation
    cmd_show(args, store)

    is_simulation = getattr(args, "simulate", False)

    # Guard: --yes is strictly forbidden in production mode
    if not is_simulation and getattr(args, "yes", False):
        print(
            "[ERROR] Security policy violation: '--yes' flag is forbidden in production mode. "
            "Production rejection strictly requires interactive human review and manual typing of 'REJECT'. "
            "'--yes' is permitted only with '--simulate'.",
            file=sys.stderr,
        )
        sys.exit(1)

    if is_simulation:
        operator_id = getattr(args, "operator", None) or os.getenv("AIOPS_OPERATOR_ID", "simulation-operator")
        approval_token = None
        authenticator = None
        print(f"[NOTICE] Running rejection in SIMULATION mode with operator '{operator_id}'.")
    else:
        operator_id = None
        authenticator = _resolve_authenticator(is_simulation=False)
        approval_token = _resolve_approval_token(authenticator)

    reason = getattr(args, "reason", None)
    if not reason:
        try:
            reason = input("Enter rejection reason: ").strip()
        except (EOFError, KeyboardInterrupt):
            reason = "Rejected by operator via CLI."
    if not reason:
        reason = "Rejected by operator via CLI."

    # Explicit confirmation gate (skip only if --yes is passed in simulation mode)
    if not getattr(args, "yes", False):
        confirm = input("Type REJECT to confirm rejection of this proposal: ").strip()
        if confirm != "REJECT":
            print("[ABORTED] Rejection cancelled. Proposal status unchanged.")
            sys.exit(0)

    engine = _build_engine(store, authenticator=authenticator)
    result = engine.reject_remediation(
        proposal_id=args.proposal_id,
        reason=reason,
        operator=operator_id if is_simulation else None,
        approval_token=approval_token,
        is_simulation=is_simulation,
    )
    print(f"[OK] Proposal '{args.proposal_id}' successfully rejected by {result.rejected_by}.")
    print(f"     Reason: {result.rejection_reason}")
    if result.rejected_at:
        print(f"     Timestamp: {result.rejected_at.strftime('%Y-%m-%d %H:%M:%SZ')}")


def cmd_recover(args, store):
    """Safely recovers a proposal stuck in APPLICATION_IN_PROGRESS."""
    proposal = store.get_proposal(args.proposal_id)
    if not proposal:
        print(f"[ERROR] Proposal '{args.proposal_id}' not found.", file=sys.stderr)
        sys.exit(1)

    from aiops.agent.remediation.schemas import RemediationStatus

    if proposal.status != RemediationStatus.APPLICATION_IN_PROGRESS:
        print(
            f"[INFO] Proposal '{args.proposal_id}' is not in progress (current status: {proposal.status.value}). "
            "Recovery is only applicable to APPLICATION_IN_PROGRESS proposals."
        )
        sys.exit(0)

    is_simulation = getattr(args, "simulate", False)
    if not is_simulation and getattr(args, "yes", False):
        print(
            "[ERROR] Security policy violation: '--yes' flag is forbidden in production mode. "
            "Production recovery strictly requires interactive human review and confirmation. "
            "'--yes' is permitted only with '--simulate'.",
            file=sys.stderr,
        )
        sys.exit(1)

    if is_simulation:
        operator_id = getattr(args, "operator", None) or os.getenv("AIOPS_OPERATOR_ID", "simulation-operator")
        approval_token = None
        authenticator = None
        github_provider = None
        print(f"[NOTICE] Running recovery in SIMULATION mode with operator '{operator_id}'.")
    else:
        operator_id = None
        authenticator = _resolve_authenticator(is_simulation=False)
        approval_token = _resolve_approval_token(authenticator)
        github_provider = _resolve_github_provider(is_simulation=False)

    cmd_show(args, store)

    if not getattr(args, "yes", False):
        confirm = input(f"Confirm recovery of in-progress proposal '{args.proposal_id}'? Type RECOVER to proceed: ").strip()
        if confirm != "RECOVER":
            print("[ABORTED] Recovery cancelled. Status remains unchanged.")
            sys.exit(0)

    engine = _build_engine(store, github_provider=github_provider, authenticator=authenticator)
    result = engine.recover_in_progress_proposal(
        proposal_id=args.proposal_id,
        operator=operator_id if is_simulation else None,
        approval_token=approval_token,
        is_simulation=is_simulation,
    )
    print(f"[SUCCESS] Proposal '{args.proposal_id}' recovered successfully.")
    print(f"          Final status : {result.status.value}")
    if result.status == RemediationStatus.APPLIED_TO_MAIN:
        print(f"          Committed SHA: {result.applied_commit_sha}")
        print(f"          Approved by  : {result.approved_by}")


def cmd_status(args, store):
    """Prints the current status of a proposal."""
    proposal = store.get_proposal(args.proposal_id)
    if not proposal:
        print(f"[ERROR] Proposal '{args.proposal_id}' not found.", file=sys.stderr)
        sys.exit(1)
    print(f"Proposal '{args.proposal_id}': status={proposal.status.value}")
    if proposal.applied_commit_sha:
        print(f"  Applied commit: {proposal.applied_commit_sha}")


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="AIOps Cloud Operator Approval CLI — manage GitOps remediation proposals.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment variables (required, never CLI args):
  AIOPS_APPROVAL_TOKENS    Format: 'token1:operator_id1,token2:operator_id2'
  AIOPS_APPROVAL_TOKEN     Single token for approve/reject (prompted if unset)
  AIOPS_GITHUB_TOKEN       GitHub PAT (retrieve from AWS Secrets Manager)
  AIOPS_GITHUB_REPOSITORY  Repository slug (default: itsme-aarjav/autonomous-devsecops-platform)
  AIOPS_STORE_BACKEND      'dynamodb' (default) or 'local'
  AIOPS_DYNAMODB_RCA_TABLE DynamoDB table name (default: boutique-aiops-rca-reports)
  AWS_DEFAULT_REGION       AWS region (default: us-east-2)
        """,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List remediation proposals")
    p_list.add_argument("--status", default="all", help="Filter by status: pending, all (default: all)")
    p_list.add_argument("--simulate", action="store_true", default=False, help="Run in simulation mode (offline fixtures only)")

    p_show = sub.add_parser("show", help="Show full details of a proposal")
    p_show.add_argument("proposal_id", help="Proposal ID (or prefix)")
    p_show.add_argument("--simulate", action="store_true", default=False, help="Run in simulation mode (offline fixtures only)")

    p_approve = sub.add_parser("approve", help="Approve and create a remediation Pull Request for human review")
    p_approve.add_argument("proposal_id", help="Proposal ID")
    p_approve.add_argument("--commit", action="store_true", default=False, help="Commit directly to GitHub main via API (CAS protected)")
    p_approve.add_argument("--simulate", action="store_true", default=False, help="Run in simulation mode (offline/testing only)")
    p_approve.add_argument("--operator", default=None, help="Operator identifier for simulation mode")
    p_approve.add_argument("--yes", "-y", action="store_true", default=False, help="Skip interactive confirmation prompt")

    p_reject = sub.add_parser("reject", help="Reject a proposal")
    p_reject.add_argument("proposal_id", help="Proposal ID")
    p_reject.add_argument("--reason", default=None, help="Rejection reason (optional)")
    p_reject.add_argument("--simulate", action="store_true", default=False, help="Run in simulation mode (offline/testing only)")
    p_reject.add_argument("--operator", default=None, help="Operator identifier for simulation mode")
    p_reject.add_argument("--yes", "-y", action="store_true", default=False, help="Skip interactive confirmation prompt")

    p_status = sub.add_parser("status", help="Print the status of a proposal")
    p_status.add_argument("proposal_id", help="Proposal ID")
    p_status.add_argument("--simulate", action="store_true", default=False, help="Run in simulation mode (offline fixtures only)")

    p_recover = sub.add_parser("recover", help="Recover a proposal stuck in APPLICATION_IN_PROGRESS")
    p_recover.add_argument("proposal_id", help="Proposal ID")
    p_recover.add_argument("--simulate", action="store_true", default=False, help="Run in simulation mode (offline/testing only)")
    p_recover.add_argument("--operator", default=None, help="Operator identifier for simulation mode")
    p_recover.add_argument("--yes", "-y", action="store_true", default=False, help="Skip interactive confirmation prompt")

    args = parser.parse_args()

    is_simulation = getattr(args, "simulate", False) or os.getenv("AIOPS_SIMULATION_MODE", "").strip().lower() in ("1", "true")
    store = _resolve_store(is_simulation=is_simulation)

    if args.command == "list":
        cmd_list(args, store)
    elif args.command == "show":
        cmd_show(args, store)
    elif args.command == "approve":
        cmd_approve(args, store)
    elif args.command == "reject":
        cmd_reject(args, store)
    elif args.command == "status":
        cmd_status(args, store)
    elif args.command == "recover":
        cmd_recover(args, store)


if __name__ == "__main__":
    main()

