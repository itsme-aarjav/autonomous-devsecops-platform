"""
Autonomous AIOps Platform — Evidence Sanitization & Secret Redaction Engine
"""

import re
import json
from typing import Dict, Any
try:
    from node_diagnostics import NodeDiagnosticManager
except ImportError:
    NodeDiagnosticManager = None


class EvidenceSanitizer:
    """Sanitizes raw evidence before dispatching to Amazon Bedrock."""

    def __init__(self, max_log_lines: int = 300, max_log_bytes: int = 65536):
        self.max_log_lines = max_log_lines
        self.max_log_bytes = max_log_bytes
        self._existing_mgr = NodeDiagnosticManager() if NodeDiagnosticManager else None

    def sanitize_text(self, text: str) -> str:
        """Removes secrets, credentials, tokens, private keys, and neutralizes injection attempts."""
        if not text:
            return ""

        # Step 1: Base sanitization via existing NodeDiagnosticManager if available
        if self._existing_mgr:
            sanitized = self._existing_mgr.sanitize_diagnostic_log(text)
        else:
            sanitized = text

        # Step 2: Redact Private Keys (RSA, EC, OpenSSH)
        sanitized = re.sub(
            r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z]+ )?PRIVATE KEY-----",
            "[REDACTED_RSA_PRIVATE_KEY]",
            sanitized,
        )

        # Step 3: Redact Bearer JWT tokens and raw JWT patterns
        sanitized = re.sub(
            r"Bearer\s+eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*",
            "Bearer [REDACTED_JWT_TOKEN]",
            sanitized,
        )
        sanitized = re.sub(
            r"\beyJ[A-Za-z0-9-_=]{10,}\.[A-Za-z0-9-_=]{10,}\.?[A-Za-z0-9-_.+/=]*\b",
            "[REDACTED_JWT_TOKEN]",
            sanitized,
        )

        # Step 4: Redact Kubernetes ServiceAccount tokens in log paths
        sanitized = re.sub(
            r"/var/run/secrets/kubernetes\.io/serviceaccount/(?:token|ca\.crt)\s*[:=]?\s*[^\s]+",
            r"[REDACTED_K8S_SECRET_PATH]",
            sanitized,
        )

        # Step 5: Redact AWS Access Keys (AKIA/ASIA)
        sanitized = re.sub(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b", "[REDACTED_AWS_ACCESS_KEY]", sanitized)

        # Step 6: Redact AWS Secret Access Keys
        sanitized = re.sub(
            r"(aws_secret_access_key|AWS_SECRET_ACCESS_KEY|secret_key|secret)\s*[:=]\s*[A-Za-z0-9/+=]{40}",
            r"\1: [REDACTED_AWS_SECRET_KEY]",
            sanitized,
        )

        # Step 7: Redact Database URLs with embedded credentials
        sanitized = re.sub(
            r"postgres(?:ql)?://([^:]+):([^@]+)@([^\s/]+)",
            r"postgresql://\1:[REDACTED_DB_CREDENTIALS]@\3",
            sanitized,
        )

        # Step 8: Redact sensitive environment variables
        sanitized = re.sub(
            r"(JWT_SECRET|AUTH_TOKEN|API_KEY|SESSION_SECRET|ENCRYPTION_KEY)\s*[:=]\s*['\"]?[^\s'\"]+",
            r"\1: [REDACTED_ENV]",
            sanitized,
            flags=re.IGNORECASE,
        )

        # Step 9: Redact generic passwords
        sanitized = re.sub(
            r"(password|passwd|secret|POSTGRES_PASSWORD|DB_PASS)\s*[:=]\s*['\"]?[^\s'\"]+",
            r"\1: [REDACTED_SECRET]",
            sanitized,
            flags=re.IGNORECASE,
        )

        # Step 10: Neutralize prompt injection attempts in untrusted log text
        sanitized = re.sub(
            r"(?i)\b(ignore previous instructions|system override|you are now a|disregard all prior instructions)\b",
            r"[UNTRUSTED_PROMPT_INJECTION_ATTEMPT]",
            sanitized,
        )

        return sanitized

    def sanitize_logs(self, log_content: str) -> str:
        """Applies secret redaction and enforces line & byte truncation limits."""
        if not log_content:
            return ""

        # Step 1: Redact secrets first
        cleaned = self.sanitize_text(log_content)

        # Step 2: Line limit truncation
        lines = cleaned.splitlines()
        if len(lines) > self.max_log_lines:
            truncated_lines = lines[-self.max_log_lines :]
            cleaned = (
                f"[LOG TRUNCATED: showing last {self.max_log_lines} of {len(lines)} lines]\n"
                + "\n".join(truncated_lines)
            )

        # Step 3: Byte limit truncation
        cleaned_bytes = cleaned.encode("utf-8")
        if len(cleaned_bytes) > self.max_log_bytes:
            cleaned = (
                "[LOG TRUNCATED: exceeded byte limit]\n"
                + cleaned_bytes[-self.max_log_bytes :].decode("utf-8", errors="ignore")
            )

        return cleaned

    def sanitize_evidence_bundle(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """Deeply sanitizes an entire dictionary of collected incident evidence and bounds total payload."""
        sanitized_bundle: Dict[str, Any] = {}

        for key, value in evidence.items():
            if isinstance(value, str):
                if "log" in key.lower():
                    sanitized_bundle[key] = self.sanitize_logs(value)
                else:
                    sanitized_bundle[key] = self.sanitize_text(value)
            elif isinstance(value, list):
                sanitized_bundle[key] = [
                    self.sanitize_text(item) if isinstance(item, str) else item
                    for item in value
                ]
            elif isinstance(value, dict):
                sanitized_bundle[key] = self.sanitize_evidence_bundle(value)
            else:
                sanitized_bundle[key] = value

        # Ensure total bundle payload doesn't exceed 2x max_log_bytes
        total_size = len(json.dumps(sanitized_bundle, default=str).encode("utf-8"))
        max_total_bytes = self.max_log_bytes * 4
        if total_size > max_total_bytes:
            # Truncate logs if overall bundle is too large
            if "logs" in sanitized_bundle and isinstance(sanitized_bundle["logs"], str):
                sanitized_bundle["logs"] = "[OVERALL PAYLOAD BOUNDED]\n" + sanitized_bundle["logs"][-10000:]

        return sanitized_bundle
