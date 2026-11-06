"""
Autonomous AIOps Agent StateGraph implementation using LangGraph.
Defines the 7-node diagnostic pipeline with conditional error routing.
"""

from typing import Dict, Any, Optional
try:
    from langgraph.graph import StateGraph, START, END
except ImportError:
    StateGraph = None
    START = None
    END = None

from .config import AgentConfig
from .schemas import IncidentInput, NormalizedIncident, RootCauseAnalysis
from .state import AgentState
from .sanitization import EvidenceSanitizer
from .evidence import BaseEvidenceAdapter, MockEvidenceAdapter
from .bedrock_client import BedrockConverseClient
from .persistence import BasePersistenceAdapter, InMemoryPersistenceAdapter


def create_aiops_graph(
    config: Optional[AgentConfig] = None,
    evidence_adapter: Optional[BaseEvidenceAdapter] = None,
    bedrock_client: Optional[BedrockConverseClient] = None,
    sanitizer: Optional[EvidenceSanitizer] = None,
    persistence_adapter: Optional[BasePersistenceAdapter] = None,
    episode_store: Any = None,
    remediation_engine: Optional[Any] = None,
):
    """
    Constructs and compiles the Autonomous AIOps LangGraph workflow.
    Supports optional GitOps remediation PR generation (Stage 6.5).
    """
    cfg = config or AgentConfig()
    evidence = evidence_adapter or MockEvidenceAdapter()
    bedrock = bedrock_client or BedrockConverseClient(cfg)
    sanitizer_inst = sanitizer or EvidenceSanitizer(max_log_lines=cfg.max_log_lines, max_log_bytes=cfg.max_log_bytes)
    persistence = persistence_adapter or InMemoryPersistenceAdapter()

    if StateGraph is None:
        raise ImportError("langgraph is required to construct the AIOps graph. Install with: pip install langgraph")

    workflow = StateGraph(AgentState)

    # -------------------------------------------------------------
    # Node 1: Incident Input Validation
    # -------------------------------------------------------------
    def validate_input_node(state: AgentState) -> Dict[str, Any]:
        raw = state.get("raw_incident") or {}
        try:
            validated = IncidentInput.model_validate(raw)
            return {
                "raw_incident": validated.model_dump(),
                "incident_id": validated.incident_id,
                "current_step": "validate_input",
                "status": "validating",
                "errors": [],
            }
        except Exception as e:
            return {
                "current_step": "validate_input",
                "status": "failed",
                "errors": [f"Input validation error: {str(e)}"],
            }

    # -------------------------------------------------------------
    # Node 2: Incident Normalization & Deduplication
    # -------------------------------------------------------------
    def normalize_incident_node(state: AgentState) -> Dict[str, Any]:
        raw = state.get("raw_incident") or {}
        try:
            norm = NormalizedIncident.from_input(IncidentInput.model_validate(raw))
            if persistence.is_duplicate(norm.dedup_key):
                return {
                    "normalized_incident": norm.model_dump(),
                    "current_step": "normalize_incident",
                    "status": "deduplicated",
                    "is_duplicate": True,
                }
            return {
                "normalized_incident": norm.model_dump(),
                "current_step": "normalize_incident",
                "status": "normalized",
                "is_duplicate": False,
            }
        except Exception as e:
            return {
                "current_step": "normalize_incident",
                "status": "failed",
                "errors": state.get("errors", []) + [f"Normalization error: {str(e)}"],
            }

    # -------------------------------------------------------------
    # Node 3: Evidence Collection
    # -------------------------------------------------------------
    def collect_evidence_node(state: AgentState) -> Dict[str, Any]:
        norm_dict = state.get("normalized_incident", {})
        namespace = norm_dict.get("namespace", "default")
        workload = norm_dict.get("affected_workload", "unknown")
        category = norm_dict.get("category", "")
        node_name = norm_dict.get("metadata", {}).get("node_name", "ip-10-0-1-100.ec2.internal")

        try:
            bundle = evidence.collect_all(
                namespace=namespace,
                workload=workload,
                node_name=node_name,
                category=category,
            )
            return {
                "raw_evidence": bundle,
                "current_step": "collect_evidence",
                "status": "evidence_collected",
            }
        except Exception as e:
            return {
                "current_step": "collect_evidence",
                "status": "failed",
                "errors": state.get("errors", []) + [f"Evidence collection error: {str(e)}"],
            }

    # -------------------------------------------------------------
    # Node 4: Evidence Sanitization
    # -------------------------------------------------------------
    def sanitize_evidence_node(state: AgentState) -> Dict[str, Any]:
        raw_bundle = state.get("raw_evidence", {})
        try:
            sanitized = sanitizer_inst.sanitize_evidence_bundle(raw_bundle)
            return {
                "sanitized_evidence": sanitized,
                "current_step": "sanitize_evidence",
                "status": "evidence_sanitized",
            }
        except Exception as e:
            return {
                "current_step": "sanitize_evidence",
                "status": "failed",
                "errors": state.get("errors", []) + [f"Sanitization error: {str(e)}"],
            }

    # -------------------------------------------------------------
    # Node 5: Bedrock Root Cause Analysis
    # -------------------------------------------------------------
    def analyze_with_bedrock_node(state: AgentState) -> Dict[str, Any]:
        incident_id = state.get("incident_id", "")
        # Pre-inference check: skip model inference if episode was resolved while in-flight
        if episode_store and incident_id and episode_store.is_episode_resolved(incident_id):
            return {
                "current_step": "analyze_with_bedrock",
                "status": "resolved_cancelled",
                "errors": [],
            }
        norm_dict = state.get("normalized_incident", {})
        sanitized_ev = state.get("sanitized_evidence", {})
        try:
            rca_dict = bedrock.analyze(incident=norm_dict, evidence=sanitized_ev)
            # Inject incident_id if missing or mismatch
            rca_dict["incident_id"] = incident_id or rca_dict.get("incident_id", "inc-unknown")
            if "category" not in rca_dict or not rca_dict["category"]:
                rca_dict["category"] = norm_dict.get("category", "Kubernetes Pod CrashLoopBackOff")
            return {
                "root_cause_analysis": rca_dict,
                "current_step": "analyze_with_bedrock",
                "status": "analysis_generated",
            }
        except Exception as e:
            return {
                "current_step": "analyze_with_bedrock",
                "status": "failed",
                "errors": state.get("errors", []) + [f"Bedrock analysis error: {str(e)}"],
            }

    # -------------------------------------------------------------
    # Node 6: RCA Validation & Safety Gate
    # -------------------------------------------------------------
    def validate_rca_node(state: AgentState) -> Dict[str, Any]:
        rca_dict = state.get("root_cause_analysis") or {}
        try:
            validated_rca = RootCauseAnalysis.model_validate(rca_dict)
            return {
                "root_cause_analysis": validated_rca.model_dump(),
                "current_step": "validate_rca",
                "status": "rca_validated",
            }
        except Exception as e:
            return {
                "current_step": "validate_rca",
                "status": "failed",
                "errors": state.get("errors", []) + [f"RCA validation failed: {str(e)}"],
            }

    # -------------------------------------------------------------
    # Node 7: Result Persistence
    # -------------------------------------------------------------
    def persist_result_node(state: AgentState) -> Dict[str, Any]:
        incident_id = state.get("incident_id", "")
        # Pre-persistence check: skip RCA persistence if episode was resolved while in-flight
        if episode_store and incident_id and episode_store.is_episode_resolved(incident_id):
            return {
                "current_step": "persist_result",
                "status": "resolved_cancelled",
                "errors": [],
            }
        rca_dict = state.get("root_cause_analysis") or {}
        norm_dict = state.get("normalized_incident") or {}
        try:
            rca_obj = RootCauseAnalysis.model_validate(rca_dict)
            saved_id = persistence.save_result(rca_obj)
            dedup_key = norm_dict.get("dedup_key")
            if dedup_key:
                persistence.record_dedup_key(dedup_key, saved_id)
            return {
                "current_step": "persist_result",
                "status": "completed",
            }
        except Exception as e:
            return {
                "current_step": "persist_result",
                "status": "failed",
                "errors": state.get("errors", []) + [f"Persistence failed: {str(e)}"],
            }

    # -------------------------------------------------------------
    # Node 8: GitOps Remediation Proposal (Stage 6.5)
    # -------------------------------------------------------------
    def propose_remediation_node(state: AgentState) -> Dict[str, Any]:
        incident_id = state.get("incident_id", "")
        # Pre-remediation check: skip remediation if episode was resolved while in-flight
        if episode_store and incident_id and episode_store.is_episode_resolved(incident_id):
            return {
                "current_step": "propose_remediation",
                "status": "resolved_cancelled",
                "errors": [],
            }
        rca_dict = state.get("root_cause_analysis")
        if not rca_dict or not remediation_engine:
            return {
                "current_step": "propose_remediation",
                "status": "completed",
            }
        try:
            rca_obj = RootCauseAnalysis.model_validate(rca_dict)
            norm_inc = state.get("normalized_incident") or {}
            proposal = remediation_engine.process_rca_and_propose(
                rca=rca_obj,
                incident=norm_inc,
                episode_id=incident_id,
            )
            return {
                "remediation_proposal": proposal.model_dump(mode="json"),
                "current_step": "propose_remediation",
                "status": "completed",
            }
        except Exception as e:
            # Non-blocking: remediation evaluation failure must not fail validated RCA investigation
            return {
                "current_step": "propose_remediation",
                "status": "completed",
                "remediation_proposal": None,
            }

    # -------------------------------------------------------------
    # Fallback / Error Handling Node
    # -------------------------------------------------------------
    def handle_error_node(state: AgentState) -> Dict[str, Any]:
        return {
            "current_step": "handle_error",
            "status": "failed",
            "errors": state.get("errors", ["Diagnostic pipeline failed"]),
        }

    # Register nodes
    workflow.add_node("validate_input", validate_input_node)
    workflow.add_node("normalize_incident", normalize_incident_node)
    workflow.add_node("collect_evidence", collect_evidence_node)
    workflow.add_node("sanitize_evidence", sanitize_evidence_node)
    workflow.add_node("analyze_with_bedrock", analyze_with_bedrock_node)
    workflow.add_node("validate_rca", validate_rca_node)
    workflow.add_node("persist_result", persist_result_node)
    workflow.add_node("propose_remediation", propose_remediation_node)
    workflow.add_node("handle_error", handle_error_node)

    # Conditional routing checks
    def route_after_input(state: AgentState) -> str:
        if state.get("errors"):
            return "handle_error"
        return "normalize_incident"

    def route_after_normalize(state: AgentState) -> str:
        if state.get("errors"):
            return "handle_error"
        if state.get("is_duplicate"):
            return END
        return "collect_evidence"

    def route_after_evidence(state: AgentState) -> str:
        if state.get("errors"):
            return "handle_error"
        return "sanitize_evidence"

    def route_after_sanitize(state: AgentState) -> str:
        if state.get("errors"):
            return "handle_error"
        return "analyze_with_bedrock"

    def route_after_bedrock(state: AgentState) -> str:
        if state.get("errors"):
            return "handle_error"
        if state.get("status") == "resolved_cancelled":
            return END
        return "validate_rca"

    def route_after_rca(state: AgentState) -> str:
        if state.get("errors"):
            return "handle_error"
        return "persist_result"

    def route_after_persist(state: AgentState) -> str:
        if state.get("errors"):
            return "handle_error"
        if state.get("status") == "resolved_cancelled":
            return END
        if not remediation_engine:
            return END
        return "propose_remediation"

    # Edge connections
    workflow.add_edge(START, "validate_input")
    workflow.add_conditional_edges("validate_input", route_after_input)
    workflow.add_conditional_edges("normalize_incident", route_after_normalize)
    workflow.add_conditional_edges("collect_evidence", route_after_evidence)
    workflow.add_conditional_edges("sanitize_evidence", route_after_sanitize)
    workflow.add_conditional_edges("analyze_with_bedrock", route_after_bedrock)
    workflow.add_conditional_edges("validate_rca", route_after_rca)
    workflow.add_conditional_edges("persist_result", route_after_persist)
    workflow.add_edge("propose_remediation", END)
    workflow.add_edge("handle_error", END)

    return workflow.compile()

