"""
Autonomous AIOps Platform — NodeDiagnostic Controller & Diagnostic Lifecycle Manager

Architecture & Security:
1. Automated collection PREFERS pre-signed S3 HTTP PUT upload URLs.
   (destination: node is reserved exclusively for interactive manual debugging via kubectl ekslogs).
2. Pre-signed URLs are generated with short expiration (15 minutes / 900s) and NEVER logged or exposed.
3. ContentType is strictly OMITTED from signing parameters to avoid SIGV4 signature mismatch.
4. Robust lifecycle cleanup & artifact retention rules:
   - Kubernetes NodeDiagnostic Custom Resources are ALWAYS cleaned up (in finally block).
   - S3 diagnostic bundles are deleted after successful analysis (purge_s3=True).
   - If log capture, download or analysis fails, the S3 bundle is RETAINED under the 14-day
     bucket lifecycle rule for post-mortem forensics.
   - Audit logs record ONLY object_key and failure status; NEVER pre-signed URLs or sensitive log contents.
"""

import re
import logging
import datetime
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("aiops.node_diagnostics")


class NodeDiagnosticManager:
    """Manages the full lifecycle of automated EKS Auto Mode NodeDiagnostic operations."""

    DEFAULT_EXPIRATION_SECONDS = 900  # 15 minutes

    def __init__(self, s3_client=None, custom_k8s_client=None, apps_k8s_client=None):
        self.s3_client = s3_client
        self.custom_k8s = custom_k8s_client
        self.apps_k8s = apps_k8s_client

    def determine_destination(self, allow_manual_node_destination: bool = False) -> str:
        """
        Determines the diagnostic logCapture destination.
        For automated AIOps workflows, 's3' is ALWAYS preferred because it enables
        direct programmatic retrieval. 'node' is only selected if manual kubectl ekslogs
        retrieval is explicitly enabled and tested.
        """
        if allow_manual_node_destination:
            return "node"
        return "s3"

    def generate_presigned_put_url(
        self, bucket_name: str, node_name: str, expires_in: int = DEFAULT_EXPIRATION_SECONDS
    ) -> Tuple[str, str]:
        """
        Generates a short-lived pre-signed HTTP PUT upload URL for S3.
        SECURITY & PROTOCOL RULES:
        1. ContentType is intentionally OMITTED from Params to prevent S3 403 SignatureDoesNotMatch.
        2. The generated URL contains signed signature parameters and MUST NEVER be logged.
        """
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        object_key = f"nodediagnostics/{node_name}-{timestamp}.tar.gz"

        if not self.s3_client:
            raise ValueError("S3 client not initialized")

        url = self.s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": bucket_name,
                "Key": object_key,
            },
            ExpiresIn=expires_in,
            HttpMethod="PUT",
        )
        return url, object_key

    def build_nodediagnostic_manifest(
        self, node_name: str, destination: str
    ) -> Dict[str, Any]:
        """
        Constructs the Kubernetes NodeDiagnostic manifest.
        ApiVersion: eks.amazonaws.com/v1alpha1
        metadata.name MUST match the node name in EKS Auto Mode.
        """
        return {
            "apiVersion": "eks.amazonaws.com/v1alpha1",
            "kind": "NodeDiagnostic",
            "metadata": {
                "name": node_name,
                "namespace": "kube-system",
                "labels": {
                    "app.kubernetes.io/name": "aiops-assistant",
                    "app.kubernetes.io/component": "diagnostics",
                },
            },
            "spec": {
                "logCapture": {
                    "destination": destination
                }
            },
        }

    def sanitize_diagnostic_log(self, raw_log_text: str) -> str:
        """
        Redacts credentials, tokens, and PII from raw diagnostic bundles.
        """
        # Redact Bearer JWT tokens
        sanitized = re.sub(
            r"Bearer\s+[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*",
            "Bearer [REDACTED_JWT]",
            raw_log_text,
        )
        # Redact AWS Access Key IDs
        sanitized = re.sub(r"(AKIA|ASIA)[0-9A-Z]{16}", "[REDACTED_AWS_KEY]", sanitized)
        # Redact generic passwords in logs/configs
        sanitized = re.sub(
            r"(password|passwd|secret|POSTGRES_PASSWORD)\s*[:=]\s*[^\s]+",
            r"\1: [REDACTED_SECRET]",
            sanitized,
            flags=re.IGNORECASE,
        )
        # Redact private IPv4 addresses (10.1.x.x)
        sanitized = re.sub(r"\b10\.1\.\d{1,3}\.\d{1,3}\b", "[INTERNAL_NODE_IP]", sanitized)
        return sanitized

    def cleanup_resources(
        self,
        node_name: str,
        bucket_name: Optional[str] = None,
        object_key: Optional[str] = None,
        purge_s3: bool = True,
    ) -> Dict[str, Any]:
        """
        Lifecycle cleanup:
        - Kubernetes NodeDiagnostic Custom Resource is ALWAYS deleted (on success and failure).
        - S3 diagnostic bundle is purged ONLY when purge_s3=True (after successful analysis).
        - If purge_s3=False (failure), the S3 object is retained under the 14-day lifecycle rule.
        """
        results = {"cr_deleted": False, "s3_purged": False, "s3_retained": False}

        # 1. Kubernetes NodeDiagnostic resource is ALWAYS cleaned up
        if self.custom_k8s:
            try:
                self.custom_k8s.delete_namespaced_custom_object(
                    group="eks.amazonaws.com",
                    version="v1alpha1",
                    namespace="kube-system",
                    plural="nodediagnostics",
                    name=node_name,
                )
                results["cr_deleted"] = True
            except Exception as e:
                logger.error("Failed to delete NodeDiagnostic CR for node %s: %s", node_name, str(e))
                results["cr_deleted"] = False

        # 2. S3 Retention Decision
        if not purge_s3:
            results["s3_retained"] = True
            return results

        if self.s3_client and bucket_name and object_key:
            try:
                self.s3_client.delete_object(Bucket=bucket_name, Key=object_key)
                results["s3_purged"] = True
            except Exception as e:
                logger.error("Failed to delete S3 bundle %s: %s", object_key, str(e))
                results["s3_purged"] = False

        return results

    def run_automated_diagnostic_lifecycle(
        self,
        node_name: str,
        bucket_name: str,
        simulate_retrieval_fn=None,
        analyze_fn=None,
    ) -> Dict[str, Any]:
        """
        Executes a complete automated diagnostic collection cycle:
        1. Generates pre-signed S3 upload URL (ContentType omitted, 15m expiration).
        2. Creates NodeDiagnostic CR in kube-system.
        3. Awaits/retrieves bundle from S3.
        4. Redacts sensitive credentials & PII.
        5. Runs analysis engine (if analyze_fn provided).
        6. On SUCCESS: Purges S3 object and deletes Kubernetes CR.
        7. On FAILURE: Retains S3 object under 14-day lifecycle rule for forensics;
           deletes Kubernetes CR; records audit log with ONLY object_key and failure status.
        """
        upload_url, object_key = self.generate_presigned_put_url(bucket_name, node_name)
        manifest = self.build_nodediagnostic_manifest(node_name, destination=upload_url)

        output = {
            "node_name": node_name,
            "object_key": object_key,
            "manifest": manifest,
            "sanitized_data": None,
            "analysis_result": None,
            "error": None,
            "audit_log": None,
            "cleanup": None,
        }

        success = False
        try:
            # Apply CRD in cluster
            if self.custom_k8s:
                self.custom_k8s.create_namespaced_custom_object(
                    group="eks.amazonaws.com",
                    version="v1alpha1",
                    namespace="kube-system",
                    plural="nodediagnostics",
                    body=manifest,
                )

            # Retrieve diagnostic data
            if simulate_retrieval_fn:
                raw_data = simulate_retrieval_fn(bucket_name, object_key)
                output["sanitized_data"] = self.sanitize_diagnostic_log(raw_data)

            # Analyze diagnostic data
            if analyze_fn and output["sanitized_data"]:
                output["analysis_result"] = analyze_fn(output["sanitized_data"])

            success = True
        except Exception as e:
            output["error"] = str(e)
            # Record audit log: ONLY object_key, status, error class/summary
            # NEVER record pre-signed URL or raw/unredacted log contents
            audit_entry = {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "node_name": node_name,
                "object_key": object_key,
                "status": "FAILED",
                "error_type": type(e).__name__,
                "retention_action": "RETAINED_UNDER_14_DAY_LIFECYCLE",
            }
            output["audit_log"] = audit_entry
            logger.warning(
                "Diagnostic collection/analysis failed. Retaining S3 object for forensics: "
                "object_key=%s, status=FAILED, error_type=%s",
                object_key,
                type(e).__name__,
            )
            # Attach audit log to exception for caller visibility
            e.audit_log = audit_entry
            raise
        finally:
            # CR is ALWAYS cleaned up. S3 is purged ONLY on success (purge_s3=success).
            output["cleanup"] = self.cleanup_resources(
                node_name=node_name,
                bucket_name=bucket_name,
                object_key=object_key,
                purge_s3=success,
            )

        return output
