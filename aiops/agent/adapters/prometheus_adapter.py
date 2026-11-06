"""
Autonomous AIOps Platform — Read-Only Prometheus HTTP API Evidence Adapter

SECURITY DIRECTIVES:
- READ-ONLY HTTP GET REQUESTS ONLY.
- Never executes arbitrary PromQL from untrusted user payloads.
- All PromQL templates are strictly predefined in an approved query catalog.
- Enforces response size bounds and timeout boundaries.
- Returns resilient partial evidence when individual queries fail or return empty vectors.
"""

import json
import logging
import re
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
try:
    import requests
except ImportError:
    requests = None

from ..config import AgentConfig
from ..evidence import BaseEvidenceAdapter

logger = logging.getLogger("aiops.adapters.prometheus")

# Strict regex pattern for safe namespace and workload identifiers in PromQL
SAFE_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]+$")

# Pre-approved PromQL Query Catalog (Strict Whitelist)
# NOTE ON HTTP_5XX_RATE: Scoped to workload pod prefix. Marked as UNVERIFIED against live cluster
# until in-cluster application service metrics are directly validated.
APPROVED_PROMQL_CATALOG = {
    "cpu_usage": 'sum(rate(container_cpu_usage_seconds_total{{namespace="{namespace}", pod=~"{workload}.*", container!=""}}[5m])) by (pod)',
    "memory_usage_bytes": 'sum(container_memory_working_set_bytes{{namespace="{namespace}", pod=~"{workload}.*", container!=""}}) by (pod)',
    "restart_rate": 'sum(increase(kube_pod_container_status_restarts_total{{namespace="{namespace}", pod=~"{workload}.*"}}[1h])) by (pod)',
    "deployment_replicas_available": 'kube_deployment_status_replicas_available{{namespace="{namespace}", deployment="{workload}"}}',
    "http_5xx_rate": 'sum(rate(http_requests_total{{namespace="{namespace}", pod=~"{workload}.*", status=~"5.."}}[5m]))',
    "node_memory_pressure": 'kube_node_status_condition{{condition="MemoryPressure", status="true"}}',
    "node_disk_pressure": 'kube_node_status_condition{{condition="DiskPressure", status="true"}}',
}


class PrometheusEvidenceAdapter(BaseEvidenceAdapter):
    """
    Read-only adapter querying metrics from Prometheus HTTP API (`/api/v1/query`).
    Validates JSON schemas, bounds payload sizes, and normalizes time series data.
    """

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        base_url: Optional[str] = None,
        http_session: Optional[Any] = None,
    ):
        self.config = config or AgentConfig()
        self.base_url = (base_url or self.config.prometheus_base_url).rstrip("/")
        self.timeout = self.config.prometheus_timeout_seconds
        self.max_response_bytes = self.config.prometheus_max_response_bytes
        if http_session is not None:
            self.session = http_session
        else:
            if requests is None:
                raise ImportError("requests is required for PrometheusEvidenceAdapter. Install with: pip install requests")
            self.session = requests.Session()

    def get_workload_evidence(
        self, namespace: str, workload: str, category: str
    ) -> Dict[str, Any]:
        """
        Executes approved metrics queries relevant to the workload and incident category.
        Returns normalized time series with timestamps, labels, and scalar values.
        """
        evidence: Dict[str, Any] = {
            "source": "prometheus",
            "base_url": self.base_url,
            "namespace": namespace,
            "workload": workload,
            "category": category,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "metrics": {},
            "warnings": [],
            "status": "success",
        }

        # Input sanitization against PromQL injection
        if not SAFE_IDENTIFIER_PATTERN.match(namespace) or not SAFE_IDENTIFIER_PATTERN.match(workload):
            msg = f"Invalid namespace or workload identifier for PromQL: namespace={namespace}, workload={workload}"
            logger.warning(msg)
            evidence["warnings"].append(msg)
            evidence["status"] = "failed"
            return evidence

        # Select approved queries to run
        queries_to_run = ["cpu_usage", "memory_usage_bytes", "restart_rate", "deployment_replicas_available"]
        if "HTTP" in category or "5xx" in category:
            queries_to_run.append("http_5xx_rate")
        if "MemoryPressure" in category:
            queries_to_run.append("node_memory_pressure")
        if "DiskPressure" in category:
            queries_to_run.append("node_disk_pressure")

        success_count = 0
        failure_count = 0

        for metric_name in queries_to_run:
            query_template = APPROVED_PROMQL_CATALOG.get(metric_name)
            if not query_template:
                continue

            query_str = query_template.format(namespace=namespace, workload=workload)
            try:
                metric_result = self.execute_query(query_str)
                evidence["metrics"][metric_name] = metric_result
                success_count += 1
            except Exception as e:
                failure_count += 1
                msg = f"Prometheus query '{metric_name}' failed: {str(e)}"
                logger.warning(msg)
                evidence["warnings"].append(msg)

        if failure_count > 0 and success_count == 0:
            evidence["status"] = "unavailable"
        elif failure_count > 0:
            evidence["status"] = "partial_failure"

        return evidence

    def execute_query(self, query: str) -> Dict[str, Any]:
        """
        Issues read-only GET request to `/api/v1/query`.
        Enforces timeout, bounds response size, and parses Prometheus response structure.
        """
        endpoint = f"{self.base_url}/api/v1/query"
        params = {"query": query}

        try:
            resp = self.session.get(endpoint, params=params, timeout=self.timeout, stream=True)
        except requests.exceptions.Timeout as e:
            raise TimeoutError(f"Prometheus query timed out after {self.timeout}s: {query}") from e
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Prometheus connection error: {str(e)}") from e

        if resp.status_code != 200:
            raise RuntimeError(f"Prometheus HTTP {resp.status_code}: {resp.text[:200]}")

        # Check response content length to prevent unbounded memory consumption
        content_length = resp.headers.get("Content-Length")
        if content_length and int(content_length) > self.max_response_bytes:
            raise ValueError(f"Prometheus response exceeds limit ({content_length} > {self.max_response_bytes} bytes)")

        # Read content with bounded byte count
        raw_content = resp.raw.read(self.max_response_bytes + 1)
        if len(raw_content) > self.max_response_bytes:
            raise ValueError(f"Prometheus response exceeded maximum size {self.max_response_bytes} bytes")

        try:
            payload = json.loads(raw_content.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"Prometheus returned malformed JSON: {str(e)}") from e

        if payload.get("status") != "success":
            err_type = payload.get("errorType", "UnknownError")
            err_msg = payload.get("error", "No details")
            raise RuntimeError(f"Prometheus query status error [{err_type}]: {err_msg}")

        data = payload.get("data", {})
        result_type = data.get("resultType", "vector")
        raw_results = data.get("result", [])

        # Normalize vector results
        normalized_series: List[Dict[str, Any]] = []
        for item in raw_results:
            metric_labels = item.get("metric", {})
            value_pair = item.get("value", [])  # [timestamp, "value_string"]
            if len(value_pair) == 2:
                ts, val_str = value_pair
                try:
                    val_float = float(val_str)
                except (ValueError, TypeError):
                    val_float = None

                normalized_series.append({
                    "labels": metric_labels,
                    "timestamp": ts,
                    "value": val_float,
                })

        return {
            "query": query,
            "result_type": result_type,
            "series_count": len(normalized_series),
            "series": normalized_series,
        }
