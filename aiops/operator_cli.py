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

logger = logging.getLogger("aiops.operator_cli")
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")


def _resolve_store():
    """Selects the remediation store backend based on AIOPS_STORE_BACKEND env var."""
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
    else:
        raise ValueError(f"Unsupported AIOPS_STORE_BACKEND: '{backend}'. Must be 'dynamodb' or 'local'.")


def _resolve_authenticator():
    """
    Builds a TrustedTokenApprovalAuthenticator:
    1. Checks AIOPS_APPROVAL_TOKENS env var (format: 'token1:operator1,token2:operator2').
    2. If unset, retrieves boutique/aiops/approval-tokens from AWS Secrets Manager using boto3.
    """
    from aiops.agent.remediation.authenticator import TrustedTokenApprovalAuthenticator
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

    if not authorized_operators:
        print(
            "[ERROR] AIOPS_APPROVAL_TOKENS is not set and could not be retrieved from\n"
            "        AWS Secrets Manager ('boutique/aiops/approval-tokens').\n"
            "        Set it in your environment or ensure AWS Secrets Manager credentials exist:\n"
            "          export AIOPS_APPROVAL_TOKENS='<token>:<your-operator-id>'",
            file=sys.stderr,
        )
        sys.exit(1)
    return TrustedTokenApprovalAuthenticator(authorized_operators)


def _resolve_approval_token() -> str:
    """
    Resolves the operator approval token: env var first, then secure getpass prompt.
    Never accepts it as a CLI argument.
    """
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


def _resolve_github_provider():
    """Builds GitHubApiProvider from AIOPS_GITHUB_TOKEN or AWS Secrets Manager."""
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

    filter_status = args.status.upper() if args.status and args.status.lower() != "all" else None
    shown = 0
    for p in proposals:
        if filter_status and p.status.value != filter_status:
            continue
        print(
            f"  {p.proposal_id[:12]}  {p.status.value:<25}  {p.workload:<20}  {p.category:<35}  "
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
        operator_id = getattr(args, "operator", None) or os.getenv("AIOPS_OPERATOR_ID", "simulation-operator")
        approval_token = None
        authenticator = None
        github_provider = None
        print(f"[NOTICE] Running in SIMULATION mode with operator '{operator_id}'.")
    else:
        # In real mode, approval always commits to main via CAS
        should_commit = True
        operator_id = None
        approval_token = _resolve_approval_token()
        authenticator = _resolve_authenticator()
        github_provider = _resolve_github_provider()

    # Show diff for operator review
    cmd_show(args, store)

    # Explicit confirmation gate (skip only if --yes is passed in headless scripts)
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
        write_to_working_tree=False,
    )
    if result.status == RemediationStatus.APPLIED_TO_MAIN:
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
    if is_simulation:
        operator_id = getattr(args, "operator", None) or os.getenv("AIOPS_OPERATOR_ID", "simulation-operator")
        approval_token = None
        authenticator = None
        print(f"[NOTICE] Running rejection in SIMULATION mode with operator '{operator_id}'.")
    else:
        operator_id = None
        approval_token = _resolve_approval_token()
        authenticator = _resolve_authenticator()

    reason = getattr(args, "reason", None)
    if not reason:
        try:
            reason = input("Enter rejection reason: ").strip()
        except (EOFError, KeyboardInterrupt):
            reason = "Rejected by operator via CLI."
    if not reason:
        reason = "Rejected by operator via CLI."

    # Explicit confirmation gate
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

    p_show = sub.add_parser("show", help="Show full details of a proposal")
    p_show.add_argument("proposal_id", help="Proposal ID (or prefix)")

    p_approve = sub.add_parser("approve", help="Approve and apply a proposal to main")
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

    args = parser.parse_args()

    store = _resolve_store()

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


if __name__ == "__main__":
    main()

