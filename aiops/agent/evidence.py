"""
Autonomous AIOps Platform — Read-Only Evidence Collection Interface & Adapters
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseEvidenceAdapter(ABC):
    """Abstract base class for read-only evidence collection."""

    @abstractmethod
    def get_workload_evidence(
        self, namespace: str, workload: str, category: str
    ) -> Dict[str, Any]:
        """Collects all relevant evidence for an affected workload."""
        pass

    def collect_all(
        self,
        namespace: str,
        workload: str,
        node_name: str = "ip-10-0-1-100.ec2.internal",
        category: str = "",
    ) -> Dict[str, Any]:
        """Collects comprehensive evidence bundle across pod, node, events, and metrics."""
        return self.get_workload_evidence(namespace=namespace, workload=workload, category=category)


class MockEvidenceAdapter(BaseEvidenceAdapter):
    """
    Mock adapter generating realistic synthetic evidence fixtures for unit testing
    and offline development without requiring AWS credentials or cluster access.
    """

    def __init__(self, synthetic_fixtures: Optional[Dict[str, Dict[str, Any]]] = None):
        self.fixtures = synthetic_fixtures or {}

    def set_fixture(self, workload: str, evidence: Dict[str, Any]) -> None:
        """Injects or overrides a synthetic fixture for a specific workload."""
        self.fixtures[workload] = evidence

    def get_workload_evidence(
        self, namespace: str, workload: str, category: str
    ) -> Dict[str, Any]:
        """Returns synthetic evidence matching the incident category and workload."""
        if workload in self.fixtures:
            return self.fixtures[workload]

        # Generate realistic default fixture based on category
        if "CrashLoopBackOff" in category:
            return {
                "workload": workload,
                "namespace": namespace,
                "pod_status": {
                    "phase": "Running",
                    "ready": False,
                    "restart_count": 8,
                    "container_name": workload,
                    "state": {
                        "waiting": {
                            "reason": "CrashLoopBackOff",
                            "message": "back-off 5m0s restarting failed container",
                        }
                    },
                    "last_state": {
                        "terminated": {
                            "exit_code": 1,
                            "reason": "Error",
                            "finished_at": "2026-11-01T15:00:00Z",
                        }
                    },
                },
                "events": [
                    "Warning BackOff Back-off restarting failed container",
                    "Warning Unhealthy Liveness probe failed: HTTP probe failed with statuscode: 500",
                ],
                "logs": (
                    "2026-11-01T14:59:58Z [INFO] Initializing service...\n"
                    "2026-11-01T14:59:59Z [ERROR] Failed to load configuration: missing required environment variable\n"
                    "Error: Process exited with code 1\n"
                    "at Module.loadConfig (/app/dist/config.js:42:11)\n"
                ),
                "deployment_status": {
                    "desired_replicas": 1,
                    "available_replicas": 0,
                    "unavailable_replicas": 1,
                },
                "resource_limits": {"cpu": "250m", "memory": "256Mi"},
                "prometheus_metrics": {
                    "restart_rate_per_min": 0.4,
                    "cpu_usage_cores": 0.05,
                    "memory_usage_bytes": 45000000,
                },
            }

        elif "OOMKilled" in category:
            return {
                "workload": workload,
                "namespace": namespace,
                "pod_status": {
                    "phase": "Running",
                    "ready": False,
                    "restart_count": 4,
                    "last_state": {
                        "terminated": {
                            "exit_code": 137,
                            "reason": "OOMKilled",
                            "finished_at": "2026-11-01T15:00:00Z",
                        }
                    },
                },
                "events": [
                    "Warning OOMKilling Memory cgroup out of memory: Killed process 124 (node)",
                ],
                "logs": (
                    "FATAL ERROR: Ineffective mark-compacts near heap limit Allocation failed - JavaScript heap out of memory\n"
                ),
                "resource_limits": {"cpu": "250m", "memory": "128Mi"},
                "resource_requests": {"cpu": "100m", "memory": "64Mi"},
                "prometheus_metrics": {
                    "memory_usage_bytes": 134217728,
                    "memory_limit_bytes": 134217728,
                },
            }

        elif "MemoryPressure" in category or "DiskPressure" in category:
            return {
                "workload": workload,
                "namespace": namespace,
                "node_status": {
                    "name": workload,
                    "conditions": [
                        {"type": "MemoryPressure", "status": "True" if "MemoryPressure" in category else "False"},
                        {"type": "DiskPressure", "status": "True" if "DiskPressure" in category else "False"},
                        {"type": "Ready", "status": "True"},
                    ],
                },
                "events": [
                    f"Warning SystemOOM Node {workload} entered MemoryPressure state" if "MemoryPressure" in category else f"Warning NodeDiskPressure Node {workload} disk usage above 90%",
                ],
                "logs": "kubelet: Node status updated with pressure condition.",
                "prometheus_metrics": {
                    "node_memory_utilization_ratio": 0.94,
                    "node_disk_utilization_ratio": 0.91,
                },
            }

        elif "PostgreSQL" in category:
            return {
                "workload": workload,
                "namespace": namespace,
                "pod_status": {
                    "phase": "Running",
                    "ready": True,
                    "restart_count": 0,
                },
                "events": [],
                "logs": (
                    "2026-11-01T15:00:01Z [ERROR] ConnectionRefusedError: connect ECONNREFUSED 10.1.10.125:5432\n"
                    "at TCPConnectWrap.afterConnect [as oncomplete] (net.js:1146:16)\n"
                    "DATABASE_URL: postgresql://boutique_user:password123@boutique-postgres:5432/boutique\n"
                ),
                "database_health": {
                    "service_name": "boutique-postgres",
                    "tcp_port": 5432,
                    "network_policy": "Enforced (restricted ingress)",
                },
                "prometheus_metrics": {
                    "db_connection_pool_active": 0,
                    "db_connection_errors_total": 42,
                },
            }

        elif "High CPU" in category:
            return {
                "workload": workload,
                "namespace": namespace,
                "pod_status": {"phase": "Running", "ready": True, "restart_count": 0},
                "events": [],
                "logs": "2026-11-01T15:00:00Z [INFO] Processing batch catalog import...\n",
                "resource_limits": {"cpu": "250m", "memory": "256Mi"},
                "prometheus_metrics": {
                    "cpu_usage_ratio": 0.98,
                    "http_request_rate": 150.0,
                },
            }

        elif "Deployment" in category:
            return {
                "workload": workload,
                "namespace": namespace,
                "deployment_status": {
                    "desired_replicas": 3,
                    "available_replicas": 0,
                    "unavailable_replicas": 3,
                },
                "events": [
                    "Warning FailedCreate Error creating: pods 'frontend-' is forbidden: exceeded quota",
                ],
                "logs": "",
            }

        # Generic fallback evidence
        return {
            "workload": workload,
            "namespace": namespace,
            "category": category,
            "pod_status": {"phase": "Running", "ready": True, "restart_count": 0},
            "events": [],
            "logs": "No fatal errors recorded in standard output.",
        }
