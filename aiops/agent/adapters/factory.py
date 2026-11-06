"""
Autonomous AIOps Platform — Production Evidence Adapter Factory

Ensures strict isolation between production live evidence adapters
and local development / testing mock adapters.
"""

from typing import Optional
from ..config import AgentConfig
from .kubernetes_adapter import KubernetesEvidenceAdapter
from .prometheus_adapter import PrometheusEvidenceAdapter
from .composite_adapter import CompositeEvidenceAdapter


def create_production_evidence_adapter(
    config: Optional[AgentConfig] = None,
) -> CompositeEvidenceAdapter:
    """
    Constructs a production-only composite evidence adapter.
    SECURITY GUARANTEE:
    - Strictly excludes MockEvidenceAdapter.
    - Explicitly sets fallback_to_mock=False.
    - Gathers telemetry only from real in-cluster Kubernetes and Prometheus APIs.
    """
    cfg = config or AgentConfig()
    k8s = KubernetesEvidenceAdapter(config=cfg)
    prom = PrometheusEvidenceAdapter(config=cfg)

    adapter = CompositeEvidenceAdapter(
        k8s_adapter=k8s,
        prometheus_adapter=prom,
        mock_adapter=None,
        fallback_to_mock=False,
    )

    # Invariant assertion
    if adapter.mock_adapter is not None or adapter.fallback_to_mock:
        raise RuntimeError("CRITICAL: MockEvidenceAdapter cannot be configured in production runtime.")

    return adapter
