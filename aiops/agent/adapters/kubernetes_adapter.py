"""
Autonomous AIOps Platform — Read-Only Kubernetes Evidence Collection Adapter

SECURITY DIRECTIVES:
- READ-ONLY OPERATIONS ONLY (GET, LIST).
- Strictly disallows mutating endpoints (create, patch, replace, delete, exec, attach, scale).
- Never accesses or reads Kubernetes Secrets.
- Enforces bounded API timeouts, bounded log line/byte limits, and resilient partial evidence capture.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

try:
    from kubernetes import client as k8s_client
    from kubernetes import config as k8s_config
    from kubernetes.client.rest import ApiException
    K8S_AVAILABLE = True
except ImportError:
    k8s_client = None
    k8s_config = None
    ApiException = Exception
    K8S_AVAILABLE = False

from ..config import AgentConfig
from ..evidence import BaseEvidenceAdapter

logger = logging.getLogger("aiops.adapters.kubernetes")


class KubernetesEvidenceAdapter(BaseEvidenceAdapter):
    """
    Read-only Kubernetes evidence collector using the official Python client.
    Gathers pod health, container exit codes, termination states, event streams,
    deployment specs, and node conditions with bounded timeouts.
    """

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        core_v1_api: Optional[Any] = None,
        apps_v1_api: Optional[Any] = None,
    ):
        self.config = config or AgentConfig()
        self.timeout = self.config.k8s_timeout_seconds
        self.max_log_lines = self.config.k8s_max_log_lines
        self.max_log_bytes = self.config.k8s_max_log_bytes
        self.max_events = self.config.k8s_max_events

        self.core_v1 = core_v1_api
        self.apps_v1 = apps_v1_api
        self._init_error: Optional[str] = None

        if self.core_v1 is None or self.apps_v1 is None:
            self._initialize_clients()

    def _initialize_clients(self) -> None:
        """Attempts in-cluster authentication first, falls back to local kubeconfig."""
        if not K8S_AVAILABLE:
            self._init_error = "kubernetes library is not installed"
            logger.warning("Kubernetes client unavailable: %s", self._init_error)
            return

        try:
            try:
                k8s_config.load_incluster_config()
                logger.info("Loaded in-cluster Kubernetes configuration")
            except Exception:
                k8s_config.load_kube_config()
                logger.info("Loaded local kube-config")

            if self.core_v1 is None:
                self.core_v1 = k8s_client.CoreV1Api()
            if self.apps_v1 is None:
                self.apps_v1 = k8s_client.AppsV1Api()
        except Exception as e:
            self._init_error = f"Failed to initialize Kubernetes API clients: {str(e)}"
            logger.warning(self._init_error)

    def is_available(self) -> bool:
        """Returns True if clients are initialized."""
        return self.core_v1 is not None and self.apps_v1 is not None

    def get_workload_evidence(
        self, namespace: str, workload: str, category: str
    ) -> Dict[str, Any]:
        """
        Gathers comprehensive read-only evidence for a workload.
        Returns partial evidence and captures non-fatal warnings if individual sources fail.
        """
        evidence: Dict[str, Any] = {
            "source": "kubernetes",
            "namespace": namespace,
            "workload": workload,
            "category": category,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "pods": [],
            "deployment": {},
            "events": [],
            "node_conditions": {},
            "logs": "",
            "previous_logs": "",
            "warnings": [],
            "status": "success",
        }

        if not self.is_available():
            evidence["status"] = "unavailable"
            evidence["warnings"].append(self._init_error or "Kubernetes API client not initialized")
            return evidence

        primary_node_name: Optional[str] = None
        primary_pod_name: Optional[str] = None
        has_restarts: bool = False

        # 1. Collect Pods Evidence
        try:
            pods_data = self._get_pods_evidence(namespace, workload)
            evidence["pods"] = pods_data
            if pods_data:
                primary_pod = pods_data[0]
                primary_pod_name = primary_pod.get("name")
                primary_node_name = primary_pod.get("node_name")
                has_restarts = primary_pod.get("restart_count", 0) > 0
        except Exception as e:
            msg = f"Failed to collect pod evidence for {workload}: {str(e)}"
            logger.warning(msg)
            evidence["warnings"].append(msg)

        # 2. Collect Deployment Evidence
        try:
            deploy_data = self._get_deployment_evidence(namespace, workload)
            evidence["deployment"] = deploy_data
        except Exception as e:
            msg = f"Failed to collect deployment evidence for {workload}: {str(e)}"
            logger.warning(msg)
            evidence["warnings"].append(msg)

        # 3. Collect Kubernetes Events
        try:
            events_data = self._get_events(namespace, workload)
            evidence["events"] = events_data
        except Exception as e:
            msg = f"Failed to collect Kubernetes events for {workload}: {str(e)}"
            logger.warning(msg)
            evidence["warnings"].append(msg)

        # 4. Collect Node Evidence (if a node name was detected)
        target_node = primary_node_name or (workload if "ip-" in workload or ".internal" in workload else None)
        if target_node:
            try:
                node_data = self._get_node_evidence(target_node)
                evidence["node_conditions"] = node_data
            except Exception as e:
                msg = f"Failed to collect node evidence for {target_node}: {str(e)}"
                logger.warning(msg)
                evidence["warnings"].append(msg)

        # 5. Collect Current and Previous Logs
        if primary_pod_name:
            try:
                evidence["logs"] = self._get_container_logs(
                    namespace=namespace, pod_name=primary_pod_name, previous=False
                )
            except Exception as e:
                msg = f"Failed to fetch logs for {primary_pod_name}: {str(e)}"
                logger.warning(msg)
                evidence["warnings"].append(msg)

            if has_restarts:
                try:
                    evidence["previous_logs"] = self._get_container_logs(
                        namespace=namespace, pod_name=primary_pod_name, previous=True
                    )
                except Exception as e:
                    # Previous logs are not always available if container never terminated or log rotated
                    logger.debug("Previous container logs not available for %s: %s", primary_pod_name, str(e))

        if evidence["warnings"] and not evidence["pods"] and not evidence["deployment"]:
            evidence["status"] = "partial_failure"

        return evidence

    def _get_pods_evidence(self, namespace: str, workload: str) -> List[Dict[str, Any]]:
        """Reads status, containers, restart counts, and termination states for pods."""
        result: List[Dict[str, Any]] = []
        canonical = workload.replace("boutique-", "") if workload.startswith("boutique-") else workload
        # Query with label selectors matching workload and canonical alias
        pod_list = None
        selectors = [
            f"app={workload}",
            f"app.kubernetes.io/name={workload}",
            f"app={canonical}",
            f"app.kubernetes.io/name={canonical}",
        ]

        for selector in selectors:
            try:
                pod_list = self.core_v1.list_namespaced_pod(
                    namespace=namespace,
                    label_selector=selector,
                    _request_timeout=self.timeout,
                )
                if pod_list and pod_list.items:
                    break
            except Exception:
                continue

        # Fallback to listing all namespace pods and matching prefix if label selector returned empty
        if not pod_list or not pod_list.items:
            all_pods = self.core_v1.list_namespaced_pod(
                namespace=namespace,
                _request_timeout=self.timeout,
            )
            items = [p for p in (all_pods.items or []) if p.metadata and p.metadata.name and (workload in p.metadata.name or canonical in p.metadata.name)]
        else:
            items = pod_list.items

        for pod in items:
            p_name = pod.metadata.name if pod.metadata else "unknown"
            node_name = pod.spec.node_name if pod.spec else None
            phase = pod.status.phase if pod.status else "Unknown"

            # Parse container statuses
            container_statuses = []
            total_restarts = 0
            is_ready = False

            if pod.status and pod.status.container_statuses:
                for cs in pod.status.container_statuses:
                    total_restarts += cs.restart_count or 0
                    if cs.ready:
                        is_ready = True

                    c_info: Dict[str, Any] = {
                        "name": cs.name,
                        "ready": cs.ready,
                        "restart_count": cs.restart_count,
                        "state": {},
                        "last_termination": {},
                    }

                    if cs.state:
                        if cs.state.waiting:
                            c_info["state"] = {
                                "status": "waiting",
                                "reason": cs.state.waiting.reason,
                                "message": cs.state.waiting.message,
                            }
                        elif cs.state.running:
                            c_info["state"] = {
                                "status": "running",
                                "started_at": str(cs.state.running.started_at),
                            }
                        elif cs.state.terminated:
                            c_info["state"] = {
                                "status": "terminated",
                                "exit_code": cs.state.terminated.exit_code,
                                "reason": cs.state.terminated.reason,
                                "message": cs.state.terminated.message,
                            }

                    if cs.last_state and cs.last_state.terminated:
                        term = cs.last_state.terminated
                        c_info["last_termination"] = {
                            "exit_code": term.exit_code,
                            "reason": term.reason,
                            "message": term.message,
                            "finished_at": str(term.finished_at),
                        }

                    container_statuses.append(c_info)

            # Resource limits from spec
            limits: Dict[str, Any] = {}
            requests: Dict[str, Any] = {}
            if pod.spec and pod.spec.containers:
                for c in pod.spec.containers:
                    if c.resources:
                        if c.resources.limits:
                            limits = dict(c.resources.limits)
                        if c.resources.requests:
                            requests = dict(c.resources.requests)

            result.append({
                "name": p_name,
                "namespace": namespace,
                "phase": phase,
                "ready": is_ready,
                "node_name": node_name,
                "restart_count": total_restarts,
                "containers": container_statuses,
                "resource_limits": limits,
                "resource_requests": requests,
            })

        return result

    def _get_events(self, namespace: str, workload: str) -> List[Dict[str, Any]]:
        """Retrieves and filters recent warning or failure events for the workload."""
        events_list = self.core_v1.list_namespaced_event(
            namespace=namespace,
            _request_timeout=self.timeout,
        )
        parsed: List[Dict[str, Any]] = []
        canonical = workload.replace("boutique-", "") if workload.startswith("boutique-") else workload

        for ev in (events_list.items or []):
            involved_name = ev.involved_object.name if ev.involved_object else ""
            if not involved_name or (workload not in involved_name and canonical not in involved_name):
                continue

            event_entry = {
                "type": ev.type,
                "reason": ev.reason,
                "message": ev.message,
                "count": ev.count,
                "last_timestamp": str(ev.last_timestamp or ev.event_time or ""),
                "involved_kind": ev.involved_object.kind if ev.involved_object else "",
                "involved_name": involved_name,
            }
            parsed.append(event_entry)
            if len(parsed) >= self.max_events:
                break

        return parsed

    def _get_deployment_evidence(self, namespace: str, workload: str) -> Dict[str, Any]:
        """Reads deployment replica state and rollout status conditions."""
        canonical = workload.replace("boutique-", "") if workload.startswith("boutique-") else workload
        dep = None
        for name in [workload, canonical]:
            try:
                dep = self.apps_v1.read_namespaced_deployment(
                    name=name,
                    namespace=namespace,
                    _request_timeout=self.timeout,
                )
                if dep:
                    break
            except Exception:
                continue

        if not dep:
            # Might not be a deployment (e.g. statefulset or raw pod)
            return {}

        status = dep.status
        spec = dep.spec
        conditions = []
        if status and status.conditions:
            for cond in status.conditions:
                conditions.append({
                    "type": cond.type,
                    "status": cond.status,
                    "reason": cond.reason,
                    "message": cond.message,
                })

        return {
            "name": workload,
            "desired_replicas": spec.replicas if spec else None,
            "available_replicas": status.available_replicas if status else None,
            "ready_replicas": status.ready_replicas if status else None,
            "updated_replicas": status.updated_replicas if status else None,
            "unavailable_replicas": status.unavailable_replicas if status else None,
            "conditions": conditions,
        }

    def _get_node_evidence(self, node_name: str) -> Dict[str, Any]:
        """Collects node pressure conditions (MemoryPressure, DiskPressure, PIDPressure)."""
        node = self.core_v1.read_node(
            name=node_name,
            _request_timeout=self.timeout,
        )
        conditions: Dict[str, Any] = {}
        if node.status and node.status.conditions:
            for c in node.status.conditions:
                conditions[c.type] = {
                    "status": c.status,
                    "reason": c.reason,
                    "message": c.message,
                }

        allocatable = dict(node.status.allocatable) if node.status and node.status.allocatable else {}
        capacity = dict(node.status.capacity) if node.status and node.status.capacity else {}

        return {
            "node_name": node_name,
            "conditions": conditions,
            "allocatable": allocatable,
            "capacity": capacity,
        }

    def _get_container_logs(
        self,
        namespace: str,
        pod_name: str,
        container_name: Optional[str] = None,
        previous: bool = False,
    ) -> str:
        """Retrieves bounded stdout/stderr logs for a pod container."""
        kwargs: Dict[str, Any] = {
            "name": pod_name,
            "namespace": namespace,
            "tail_lines": self.max_log_lines,
            "limit_bytes": self.max_log_bytes,
            "previous": previous,
            "_request_timeout": self.timeout,
        }
        if container_name:
            kwargs["container"] = container_name

        try:
            raw_logs = self.core_v1.read_namespaced_pod_log(**kwargs)
            return raw_logs or ""
        except Exception as e:
            if previous:
                return ""  # Silence previous log not found
            raise e
