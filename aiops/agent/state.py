"""
Autonomous AIOps Platform — LangGraph Agent State Definition
"""

from typing import TypedDict, Dict, Any, List, Optional


class AgentState(TypedDict, total=False):
    """Typed state dictionary passed across LangGraph nodes."""

    # Unique incident identifier
    incident_id: str

    # Incoming raw request payload
    raw_incident: Dict[str, Any]

    # Validated & normalized incident
    normalized_incident: Optional[Dict[str, Any]]

    # Collected raw evidence
    raw_evidence: Optional[Dict[str, Any]]

    # Sanitized evidence (secrets redacted, logs bounded)
    sanitized_evidence: Optional[Dict[str, Any]]

    # Root Cause Analysis model output
    root_cause_analysis: Optional[Dict[str, Any]]

    # Remediation proposal output (Stage 6.5)
    remediation_proposal: Optional[Dict[str, Any]]

    # Deduplication flag
    is_duplicate: bool

    # Current workflow execution step
    current_step: str

    # Overall lifecycle status: validating, normalized, evidence_collected, evidence_sanitized, analysis_generated, rca_validated, completed, failed, deduplicated
    status: str

    # Accumulated errors during workflow execution
    errors: List[str]
