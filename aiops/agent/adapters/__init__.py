"""
Autonomous AIOps Evidence Adapters Package.
"""

from .kubernetes_adapter import KubernetesEvidenceAdapter
from .prometheus_adapter import PrometheusEvidenceAdapter, APPROVED_PROMQL_CATALOG, SAFE_IDENTIFIER_PATTERN
from .composite_adapter import CompositeEvidenceAdapter
from .factory import create_production_evidence_adapter

__all__ = [
    "KubernetesEvidenceAdapter",
    "PrometheusEvidenceAdapter",
    "CompositeEvidenceAdapter",
    "create_production_evidence_adapter",
    "APPROVED_PROMQL_CATALOG",
    "SAFE_IDENTIFIER_PATTERN",
]
