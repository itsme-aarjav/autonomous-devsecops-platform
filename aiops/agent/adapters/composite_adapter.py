"""
Autonomous AIOps Platform — Composite Evidence Collection Adapter

Coordinates Kubernetes, Prometheus, and Mock evidence collectors into a single
unified, resilient evidence bundle. Handles partial failures and validates that
usable telemetry exists before allowing downstream LLM root cause analysis.
"""

import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from ..evidence import BaseEvidenceAdapter, MockEvidenceAdapter
from .kubernetes_adapter import KubernetesEvidenceAdapter
from .prometheus_adapter import PrometheusEvidenceAdapter

logger = logging.getLogger("aiops.adapters.composite")


class CompositeEvidenceAdapter(BaseEvidenceAdapter):
    """
    Composite evidence aggregator combining Kubernetes, Prometheus, and Mock sources.
    Enforces graceful degradation when individual telemetry subsystems are offline.
    """

    def __init__(
        self,
        k8s_adapter: Optional[KubernetesEvidenceAdapter] = None,
        prometheus_adapter: Optional[PrometheusEvidenceAdapter] = None,
        mock_adapter: Optional[MockEvidenceAdapter] = None,
        fallback_to_mock: bool = False,
    ):
        self.k8s_adapter = k8s_adapter
        self.prometheus_adapter = prometheus_adapter
        self.mock_adapter = mock_adapter
        self.fallback_to_mock = fallback_to_mock

    def get_workload_evidence(
        self, namespace: str, workload: str, category: str
    ) -> Dict[str, Any]:
        """
        Gathers evidence across all configured sources, tracking collection durations,
        per-source collection statuses, and ensuring minimum usable evidence is present.
        """
        start_time = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()

        bundle: Dict[str, Any] = {
            "source": "composite",
            "namespace": namespace,
            "workload": workload,
            "category": category,
            "collected_at": now_iso,
            "source_timestamps": {},
            "source_status": {},
            "warnings": [],
            "kubernetes": {},
            "prometheus": {},
            "mock": {},
            "has_usable_evidence": False,
        }

        # 1. Gather Kubernetes Evidence
        if self.k8s_adapter:
            try:
                k8s_res = self.k8s_adapter.get_workload_evidence(namespace, workload, category)
                bundle["kubernetes"] = k8s_res
                bundle["source_timestamps"]["kubernetes"] = k8s_res.get("collected_at", now_iso)
                bundle["source_status"]["kubernetes"] = k8s_res.get("status", "success")
                if k8s_res.get("warnings"):
                    bundle["warnings"].extend(k8s_res["warnings"])
            except Exception as e:
                msg = f"Unexpected error in Kubernetes adapter: {str(e)}"
                logger.error(msg)
                bundle["source_status"]["kubernetes"] = "failed"
                bundle["warnings"].append(msg)
        else:
            bundle["source_status"]["kubernetes"] = "skipped"

        # 2. Gather Prometheus Evidence
        if self.prometheus_adapter:
            try:
                prom_res = self.prometheus_adapter.get_workload_evidence(namespace, workload, category)
                bundle["prometheus"] = prom_res
                bundle["source_timestamps"]["prometheus"] = prom_res.get("collected_at", now_iso)
                bundle["source_status"]["prometheus"] = prom_res.get("status", "success")
                if prom_res.get("warnings"):
                    bundle["warnings"].extend(prom_res["warnings"])
            except Exception as e:
                msg = f"Unexpected error in Prometheus adapter: {str(e)}"
                logger.error(msg)
                bundle["source_status"]["prometheus"] = "failed"
                bundle["warnings"].append(msg)
        else:
            bundle["source_status"]["prometheus"] = "skipped"

        # 3. Optional Mock Adapter / Fallback
        if self.mock_adapter and (self.fallback_to_mock or (bundle["source_status"]["kubernetes"] in ("skipped", "failed", "unavailable") and bundle["source_status"]["prometheus"] in ("skipped", "failed", "unavailable"))):
            try:
                mock_res = self.mock_adapter.get_workload_evidence(namespace, workload, category)
                bundle["mock"] = mock_res
                bundle["source_timestamps"]["mock"] = now_iso
                bundle["source_status"]["mock"] = "success"
            except Exception as e:
                bundle["source_status"]["mock"] = "failed"
                bundle["warnings"].append(f"Mock adapter error: {str(e)}")

        # 4. Synthesize top-level fields for backward compatibility with prompts & tests
        # Merge logs
        k8s_logs = bundle.get("kubernetes", {}).get("logs", "")
        mock_logs = bundle.get("mock", {}).get("logs", "")
        bundle["logs"] = k8s_logs or mock_logs

        # Merge pod status
        k8s_pods = bundle.get("kubernetes", {}).get("pods", [])
        if k8s_pods:
            bundle["pod_status"] = k8s_pods[0]
        elif bundle.get("mock", {}).get("pod_status"):
            bundle["pod_status"] = bundle["mock"]["pod_status"]

        # Merge events
        k8s_events = bundle.get("kubernetes", {}).get("events", [])
        mock_events = bundle.get("mock", {}).get("events", [])
        bundle["events"] = k8s_events or mock_events

        # Merge deployment status
        k8s_dep = bundle.get("kubernetes", {}).get("deployment", {})
        mock_dep = bundle.get("mock", {}).get("deployment_status", {})
        bundle["deployment_status"] = k8s_dep or mock_dep

        # Merge node conditions
        k8s_node = bundle.get("kubernetes", {}).get("node_conditions", {})
        mock_node = bundle.get("mock", {}).get("node_status", {})
        bundle["node_status"] = k8s_node or mock_node

        # Merge Prometheus metrics
        prom_metrics = bundle.get("prometheus", {}).get("metrics", {})
        mock_metrics = bundle.get("mock", {}).get("prometheus_metrics", {})
        bundle["prometheus_metrics"] = prom_metrics or mock_metrics

        # Determine if we have minimum usable evidence
        has_k8s_data = bool(k8s_pods or k8s_dep or k8s_logs or k8s_events or k8s_node)
        has_prom_data = bool(prom_metrics)
        has_mock_data = bool(bundle.get("mock"))

        bundle["has_usable_evidence"] = has_k8s_data or has_prom_data or has_mock_data
        bundle["collection_duration_ms"] = round((time.time() - start_time) * 1000, 2)

        return bundle
