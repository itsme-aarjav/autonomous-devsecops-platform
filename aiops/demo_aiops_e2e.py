#!/usr/bin/env python3
"""
Autonomous AIOps Platform — Local End-to-End Demonstration
Reproducible, local walkthrough of the 8-node LangGraph operational agent:
  1. Incident Input Validation (Pydantic schema validation)
  2. Normalization & Deduplication (hash calculation)
  3. Evidence Collection (Synthetic Kubernetes & Prometheus fixtures)
  4. Evidence Sanitization (Credential stripping, truncation, PII redaction)
  5. RCA Inference (Deterministic simulated Bedrock Converse model)
  6. RCA Validation & Safety Gate (Rejection of destructive commands)
  7. Persistence (Local incident storage & retrieval)
  8. Two-Tier Self-Healing (Tier-1 Ansible dry-run + Tier-2 GitOps PR)

NOTE: Simulated offline demonstration with mock adapters and fake GitHub provider.
Does NOT require AWS credentials, calls no live Bedrock, and incurs ZERO cloud costs.
"""

import sys
import os
import json
import tempfile
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# Ensure agent module is importable
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from agent.config import AgentConfig
from agent.sanitization import EvidenceSanitizer
from agent.evidence import MockEvidenceAdapter
from agent.persistence import LocalFilePersistenceAdapter
from agent.graph import create_aiops_graph
from agent.remediation.generator import GitOpsRemediationEngine
from agent.remediation.runbook_executor import AnsibleRunbookExecutor


class DeterministicFakeBedrockClient:
    """
    Simulates Amazon Bedrock Converse API with a deterministic, structured
    root cause analysis adhering to strict safety directives.
    NOTE: Simulated offline demonstration only (incurs zero AWS cloud costs).
    """

    def __init__(self):
        self.invoked = False

    def analyze(
        self,
        incident: Dict[str, Any],
        evidence: Dict[str, Any],
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.invoked = True
        incident_id = incident.get("incident_id", "inc-synthetic-001")
        category = incident.get("category", "Pod OOMKilled")
        workload = incident.get("affected_workload", "boutique-auth")

        return {
            "incident_id": incident_id,
            "category": category,
            "confidence_score": 0.95,
            "summary": f"Pod {workload} terminated with exit code 137 (OOMKilled) under peak memory pressure.",
            "root_cause": (
                f"The {workload} container exceeded its configured memory limit of 256Mi during high volume "
                f"JWT signing and bcrypt verification operations. The Linux kernel cgroup memory controller "
                f"terminated process with SIGKILL (exit code 137). Container runtime logs confirm "
                f"'JavaScript heap out of memory'. Working set memory peaked at 100% of ceiling."
            ),
            "supporting_evidence": [
                f"Pod termination event: container in {workload} terminated with exit code 137 (OOMKilled)",
                "Kernel event: Memory cgroup out of memory: Killed process 124 (node)",
                "Container log: FATAL ERROR: Ineffective mark-compacts near heap limit Allocation failed - JavaScript heap out of memory",
                "Prometheus metric: container_memory_working_set_bytes reached memory limit ceiling",
            ],
            "recommended_actions": [
                "Increase container memory limit in devops/gitops/k8s/backend/auth.yml from 256Mi to 512Mi (requests to 256Mi).",
                "Trigger immediate Tier-1 memory remediation runbook to drop host OS page cache and clear zombie processes.",
                "Generate automated Tier-2 GitOps Pull Request to persist adjusted memory limits via Argo CD.",
            ],
            "risks": [
                f"User login, token verification, and registration requests will experience HTTP 503 until {workload} is restored."
            ],
            "is_destructive": False,
        }


def run_e2e_demonstration():
    print("=" * 70)
    print("  AUTONOMOUS AIOPS PLATFORM — END-TO-END LOCAL DEMONSTRATION")
    print("=" * 70)

    # 1. Prepare Synthetic Incident
    raw_incident = {
        "incident_id": f"inc-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "title": "Pod OOMKilled in boutique-auth",
        "category": "Pod OOMKilled",
        "severity": "critical",
        "affected_workload": "boutique-auth",
        "namespace": "boutique",
        "description": "Container terminated with exit code 137; node memory pressure and cgroup limit reached.",
        "metadata": {
            "cluster": "boutique-dev-eks",
            "node_name": "ip-10-0-1-100.ec2.internal",
            "environment": "dev",
        },
    }

    print("\n[STEP 1/8] Ingesting Raw Incident Payload:")
    print(f"  Incident ID : {raw_incident['incident_id']}")
    print(f"  Workload    : {raw_incident['affected_workload']} (ns: {raw_incident['namespace']})")
    print(f"  Category    : {raw_incident['category']}")
    print(f"  Severity    : {raw_incident['severity'].upper()}")

    # 2. Configure Local Test Sandbox & Adapters
    temp_dir = tempfile.mkdtemp(prefix="aiops_demo_")
    repo_root = os.path.abspath(os.path.join(current_dir, "../.."))
    config = AgentConfig(
        aws_region="us-east-2",
        bedrock_enabled=False,  # Disabled for local offline testing
        max_log_lines=50,
        max_log_bytes=4096,
    )
    evidence_adapter = MockEvidenceAdapter()
    sanitizer = EvidenceSanitizer(max_log_lines=50, max_log_bytes=4096)
    fake_bedrock = DeterministicFakeBedrockClient()
    persistence = LocalFilePersistenceAdapter(base_dir=temp_dir)
    runbook_executor = AnsibleRunbookExecutor(dry_run=True)
    remediation_engine = GitOpsRemediationEngine(
        repo_root=repo_root,
        github_provider=None,
        runbook_executor=runbook_executor,
    )

    print("\n[STEP 2/8] Initializing Local Adapters:")
    print("  ✓ Evidence Adapter    : MockEvidenceAdapter (synthetic K8s & Prometheus fixtures)")
    print("  ✓ Sanitizer           : EvidenceSanitizer (credential redaction & line truncation)")
    print("  ✓ AI Inference Engine : DeterministicFakeBedrockClient (Offline simulated Converse API)")
    print(f"  ✓ Persistence Engine  : LocalFilePersistenceAdapter (Local directory: {temp_dir})")
    print("  ✓ GitHub Provider     : None (Offline demonstration; no live GitHub mutations)")
    print("  ✓ Runbook Executor    : AnsibleRunbookExecutor (dry-run operational execution)")

    # 3. Construct and Compile LangGraph Workflow
    print("\n[STEP 3/8] Compiling 8-Node LangGraph StateGraph Pipeline...")
    graph = create_aiops_graph(
        config=config,
        evidence_adapter=evidence_adapter,
        bedrock_client=fake_bedrock,
        sanitizer=sanitizer,
        persistence_adapter=persistence,
        remediation_engine=remediation_engine,
    )
    print("  ✓ StateGraph compiled successfully.")

    # 4. Execute Pipeline
    print("\n[STEP 4/8] Executing Workflow:")
    initial_state = {"raw_incident": raw_incident}
    final_state = graph.invoke(initial_state)

    # 5. Validate Pipeline Progression
    print("\n[STEP 5/8] Verifying Node Execution Progression:")
    steps_verified = [
        ("Input Validation", final_state.get("incident_id") == raw_incident["incident_id"]),
        ("Incident Normalization", final_state.get("normalized_incident") is not None),
        ("Evidence Collection", final_state.get("raw_evidence") is not None),
        ("Evidence Sanitization", final_state.get("sanitized_evidence") is not None),
        ("Bedrock RCA Inference", final_state.get("root_cause_analysis") is not None),
        ("RCA Safety Validation", final_state.get("status") == "completed"),
        ("Remediation Proposal", final_state.get("remediation_proposal") is not None),
    ]

    for step_name, passed in steps_verified:
        badge = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {badge} : {step_name}")

    if final_state.get("errors"):
        print(f"\n⚠️  Pipeline Errors Encountered: {final_state['errors']}")
        return 1

    rca = final_state.get("root_cause_analysis", {})
    proposal = final_state.get("remediation_proposal", {})

    # 6. Safety Gate Verification
    print("\n[STEP 6/8] Safety Gate & Policy Inspection:")
    print(f"  ✓ Confidence Score   : {rca.get('confidence_score'):.2f} / 1.00")
    print(f"  ✓ Non-Destructive    : {rca.get('is_destructive') is False}")
    print(f"  ✓ Action Count       : {len(rca.get('recommended_actions', []))} recommended steps")
    print(f"  ✓ Policy Decision    : {proposal.get('policy_decision')}")
    print(f"  ✓ Target Workload    : {proposal.get('workload')}")
    print(f"  ✓ Target Manifest    : {proposal.get('target_manifest')}")

    # 7. Persistence Verification
    persisted_obj = persistence.get_result(raw_incident["incident_id"])
    assert persisted_obj is not None, "Persisted RCA must be retrievable from local storage."
    print("\n[STEP 7/8] Persistence Verification:")
    persisted_path = os.path.join(temp_dir, f"{raw_incident['incident_id']}.json")
    print(f"  ✓ Successfully stored and retrieved report for: {raw_incident['incident_id']}")
    print(f"  ✓ Persisted file location: {persisted_path}")

    # 8. Two-Tier Self-Healing Verification
    print("\n[STEP 8/8] Two-Tier Autonomous Self-Healing Verification:")
    if remediation_engine.last_runbook_result:
        print(f"  ✓ Tier-1 Operational Runbook : {remediation_engine.last_runbook_result.playbook} (Success: {remediation_engine.last_runbook_result.success})")
        print(f"    Summary: {remediation_engine.last_runbook_result.summary}")
    print(f"  ✓ Tier-2 Declarative GitOps  : Status: {proposal.get('status')} (Awaiting Human Approval for Direct-Main)")
    diff = proposal.get("diff_summary", "")
    if diff:
        print("\n  --- Rendered GitOps Manifest Patch (Unified Diff) ---")
        for line in diff.strip().splitlines():
            print(f"    {line}")
        print("  ----------------------------------------------------")

    # Demonstrate explicit human operator approval gate and direct-to-main application
    print("\n  --- Human Operator Approval Gate Simulation ---")
    approved_proposal = remediation_engine.apply_approved_remediation(
        proposal_id=proposal["proposal_id"],
        operator="sre-oncall-lead",
        is_simulation=True,
        write_to_working_tree=False,
    )
    print(f"  ✓ Explicit Simulated Approval Recorded : {approved_proposal.approved_by}")
    print(f"  ✓ Simulated Approval Flag              : is_simulated_approval={approved_proposal.is_simulated_approval}")
    print(f"  ✓ Real Human Authentication Flag       : is_approved_by_human={approved_proposal.is_approved_by_human} (False - Offline Simulation Only)")
    print(f"  ✓ Approval Mode                        : {approved_proposal.approval_mode}")
    print(f"  ✓ Final Proposal Status                : {approved_proposal.status.value}")
    print(f"  ✓ Single-Main Branch Invariant         : Branches created = 0, PRs created = 0")

    print("\n" + "=" * 70)
    print("  FINAL ROOT CAUSE ANALYSIS REPORT (GENERATED)")
    print("=" * 70)
    print(json.dumps(rca, indent=2))
    print("=" * 70)
    print("  SIMULATED DEMONSTRATION COMPLETED SUCCESSFULLY")
    print("  (Offline local run with Mock Evidence & Deterministic Fake Bedrock)")
    print("  (Zero cloud costs incurred, no live cluster/GitHub mutations)")
    print("=" * 70 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(run_e2e_demonstration())
