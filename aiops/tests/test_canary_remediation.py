"""
Unit tests verifying Canary workload remediation, policy gating, and GitOps diff rendering.
"""

import unittest
from pathlib import Path

from aiops.agent.schemas import RootCauseAnalysis
from aiops.agent.remediation.policy import RemediationPolicyEngine, WORKLOAD_MANIFEST_MAP, ALLOWLISTED_WORKLOADS
from aiops.agent.remediation.schemas import (
    RemediationProposal,
    RemediationActionType,
    RemediationParameters,
    PolicyDecision,
)
from aiops.agent.remediation.renderer import ManifestPatchRenderer
from aiops.agent.remediation.generator import GitOpsRemediationEngine


class TestCanaryRemediation(unittest.TestCase):
    def setUp(self):
        self.repo_root = str(Path(__file__).parent.parent.parent.resolve())
        self.policy_engine = RemediationPolicyEngine(min_confidence=0.70)
        self.renderer = ManifestPatchRenderer(repo_root=self.repo_root)
        self.engine = GitOpsRemediationEngine(repo_root=self.repo_root)

    def test_canary_workload_resolution(self):
        """Tests that both 'canary' and 'boutique-canary' resolve to valid workloads."""
        self.assertIn("canary", ALLOWLISTED_WORKLOADS)
        self.assertIn("boutique-canary", ALLOWLISTED_WORKLOADS)
        self.assertEqual(
            WORKLOAD_MANIFEST_MAP["canary"][0],
            "devops/gitops/overlays/dev/canary.yml",
        )
        self.assertEqual(
            WORKLOAD_MANIFEST_MAP["boutique-canary"][0],
            "devops/gitops/overlays/dev/canary.yml",
        )

        rca = RootCauseAnalysis(
            incident_id="inc-test-01",
            root_cause="Canary container memory exhaustion in boutique-canary",
            category="Pod OOMKilled",
            confidence_score=0.95,
            is_destructive=False,
            summary="Workload canary terminated due to OOMKilled",
        )
        # Incident with affected_workload="boutique-canary"
        workload = self.engine._extract_workload(rca, {"affected_workload": "boutique-canary"})
        self.assertIn(workload, ("canary", "boutique-canary"))

        # Incident with affected_workload="canary"
        workload_canary = self.engine._extract_workload(rca, {"affected_workload": "canary"})
        self.assertIn(workload_canary, ("canary", "boutique-canary"))

        # Incident with pod name containing ReplicaSet/Pod hash suffix
        workload_pod_hash = self.engine._extract_workload(rca, {"affected_workload": "boutique-canary-5c9d488bb5-pnt2d"})
        self.assertIn(workload_pod_hash, ("canary", "boutique-canary"))

        workload_canary_hash = self.engine._extract_workload(rca, {"affected_workload": "canary-5c9d488bb5-pnt2d"})
        self.assertIn(workload_canary_hash, ("canary", "boutique-canary"))

        workload_auth_hash = self.engine._extract_workload(rca, {"affected_workload": "auth-786cb868b8-jn8dx"})
        self.assertEqual(workload_auth_hash, "auth")

    def test_canary_policy_approval(self):
        """Tests that a valid canary memory remediation proposal passes deterministic policy."""
        proposal = RemediationProposal(
            proposal_id="prop-canary-01",
            incident_id="inc-canary-01",
            episode_id="ep-canary-01",
            category="Pod OOMKilled",
            action_type=RemediationActionType.SET_MEMORY_RESOURCES,
            workload="canary",
            namespace="boutique",
            target_manifest="devops/gitops/overlays/dev/canary.yml",
            parameters=RemediationParameters(memory_request="256Mi", memory_limit="512Mi", target_container="canary"),
            confidence_score=0.90,
            justification="Scale memory limit for canary workload to 512Mi.",
        )
        decision, reason = self.policy_engine.evaluate(proposal)
        self.assertEqual(decision, PolicyDecision.APPROVED)
        self.assertIn("satisfies all safety", reason)

    def test_canary_diff_rendering(self):
        """Tests that renderer creates a surgical unified diff for boutique-canary Deployment."""
        proposal = RemediationProposal(
            proposal_id="prop-canary-02",
            incident_id="inc-canary-02",
            episode_id="ep-canary-02",
            category="Pod OOMKilled",
            action_type=RemediationActionType.SET_MEMORY_RESOURCES,
            workload="canary",
            namespace="boutique",
            target_manifest="devops/gitops/overlays/dev/canary.yml",
            parameters=RemediationParameters(memory_request="256Mi", memory_limit="512Mi", target_container="canary"),
            confidence_score=0.92,
            justification="Increase container memory limit.",
            policy_decision=PolicyDecision.APPROVED,
        )
        rendered = self.renderer.render_proposal_patch(proposal)
        self.assertIn("devops/gitops/overlays/dev/canary.yml", rendered.modified_files)
        self.assertTrue(len(rendered.diff) > 0)
        self.assertIn("512Mi", rendered.diff)
        self.assertIn("256Mi", rendered.diff)

    def test_canary_manifest_command_bounding(self):
        """Tests that canary manifest defines bounded memory checks and avoids endless loops."""
        canary_manifest = Path(self.repo_root) / "devops/gitops/overlays/dev/canary.yml"
        self.assertTrue(canary_manifest.is_file())
        content = canary_manifest.read_text()

        # Verify ConfigMap volume mount definition
        self.assertIn("boutique-canary-trigger", content)
        self.assertIn("/etc/canary-trigger", content)

        # Verify command contains bounded check logic (checking cgroup limit <= 128Mi)
        self.assertIn("trigger_check()", content)
        self.assertIn("134217728", content)
        self.assertIn("Simulating bounded memory load", content)
        self.assertIn("Bounded workload resolved by remediation; running stably", content)

    def test_canary_invalid_proposal_rejected(self):
        """Tests that out-of-bounds proposals or unknown workloads are strictly rejected."""
        # Excessive memory limit (2Gi > MAX_MEMORY_BYTES 1Gi)
        invalid_proposal = RemediationProposal(
            proposal_id="prop-canary-invalid-01",
            incident_id="inc-canary-invalid-01",
            episode_id="ep-canary-invalid-01",
            category="Pod OOMKilled",
            action_type=RemediationActionType.SET_MEMORY_RESOURCES,
            workload="canary",
            namespace="boutique",
            target_manifest="devops/gitops/overlays/dev/canary.yml",
            parameters=RemediationParameters(memory_limit="2048Mi", target_container="canary"),
            confidence_score=0.95,
            justification="Attempting excessive memory allocation.",
        )
        decision, reason = self.policy_engine.evaluate(invalid_proposal)
        self.assertEqual(decision, PolicyDecision.REJECTED)
        self.assertIn("out of bounds", reason)


if __name__ == "__main__":
    unittest.main()

