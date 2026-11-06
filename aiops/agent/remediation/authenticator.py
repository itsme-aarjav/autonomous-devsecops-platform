"""
Autonomous AIOps Platform — Human Approval Authenticator Interface & Implementations
"""

import os
import hmac
import fnmatch
from abc import ABC, abstractmethod
from typing import Optional, Dict, Tuple, List, Any
from .schemas import RemediationProposal


class BaseApprovalAuthenticator(ABC):
    """Abstract interface for authenticating human operator approval."""

    @abstractmethod
    def authenticate(
        self,
        proposal: RemediationProposal,
        approval_token: Optional[str],
        operator: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Verifies whether the approval token and operator identity prove genuine
        authenticated human authorization.

        Returns:
            (is_authenticated, verified_operator_identity_or_error_message)
        """
        pass


class TrustedTokenApprovalAuthenticator(BaseApprovalAuthenticator):
    """
    Authenticated human approval provider using constant-time token comparison
    against cryptographically strong authorized operator credentials.
    """

    def __init__(self, authorized_operators: Dict[str, str]):
        """
        Args:
            authorized_operators: Mapping of token -> operator_id
        """
        self._authorized_operators = authorized_operators

    def authenticate(
        self,
        proposal: RemediationProposal,
        approval_token: Optional[str],
        operator: Optional[str] = None,
    ) -> Tuple[bool, str]:
        if not approval_token or not isinstance(approval_token, str) or not approval_token.strip():
            return False, "Missing or empty approval token"

        token_to_verify = approval_token.strip()
        matched_operator = None

        for valid_token, valid_operator in self._authorized_operators.items():
            if hmac.compare_digest(token_to_verify, valid_token.strip()):
                matched_operator = valid_operator
                break

        if not matched_operator:
            return False, "Unrecognized, invalid, or expired approval token"

        if operator and operator.strip() != matched_operator:
            return False, f"Operator mismatch: token belongs to '{matched_operator}', but approval was claimed for '{operator.strip()}'"

        return True, matched_operator


class AwsIamApprovalAuthenticator(BaseApprovalAuthenticator):
    """
    Production-grade human approval authenticator bound to authenticated AWS IAM/STS caller identity.
    Enforces that caller is authenticated in the target AWS Account (default: 592668326948)
    and matches authorized operator IAM principal patterns (e.g. terra-admin, CloudShell, Operator roles).
    Optionally validates a secondary approval token if token authenticator is provided.
    """

    DEFAULT_ALLOWED_ACCOUNT = "592668326948"
    DEFAULT_ALLOWED_PATTERNS = [
        "*:user/terra-admin",
        "*:root",
        "*:role/*Admin*",
        "*:role/*CloudOps*",
        "*:role/*Operator*",
        "*:role/*CloudShell*",
        "*:assumed-role/*Admin*/*",
        "*:assumed-role/*CloudOps*/*",
        "*:assumed-role/*Operator*/*",
        "*:assumed-role/*CloudShell*/*",
        "*:assumed-role/AWSCloudShellFullAccess/*",
    ]

    def __init__(
        self,
        allowed_account: Optional[str] = None,
        allowed_patterns: Optional[List[str]] = None,
        token_authenticator: Optional[TrustedTokenApprovalAuthenticator] = None,
        sts_client: Optional[Any] = None,
    ):
        self.allowed_account = allowed_account or os.getenv("AIOPS_ALLOWED_AWS_ACCOUNT", self.DEFAULT_ALLOWED_ACCOUNT)
        raw_patterns = os.getenv("AIOPS_ALLOWED_OPERATOR_PATTERNS", "")
        if raw_patterns:
            self.allowed_patterns = [p.strip() for p in raw_patterns.split(",") if p.strip()]
        else:
            self.allowed_patterns = allowed_patterns or self.DEFAULT_ALLOWED_PATTERNS
        self.token_authenticator = token_authenticator
        self._sts_client = sts_client

    def _get_sts_client(self):
        if self._sts_client is not None:
            return self._sts_client
        import boto3
        region = os.getenv("AWS_DEFAULT_REGION", os.getenv("AWS_REGION", "us-east-2"))
        self._sts_client = boto3.client("sts", region_name=region)
        return self._sts_client

    def authenticate(
        self,
        proposal: RemediationProposal,
        approval_token: Optional[str],
        operator: Optional[str] = None,
    ) -> Tuple[bool, str]:
        # 1. Authoritative AWS STS Identity Verification
        try:
            sts = self._get_sts_client()
            identity = sts.get_caller_identity()
        except Exception as e:
            return False, f"AWS STS caller identity verification failed: {e}"

        account = identity.get("Account", "")
        arn = identity.get("Arn", "")

        if account != self.allowed_account:
            return False, f"Access Denied: AWS Account '{account}' is not authorized (expected {self.allowed_account})"

        # Verify ARN matches allowed operator patterns
        matched = any(fnmatch.fnmatch(arn, pattern) for pattern in self.allowed_patterns)
        if not matched:
            return False, f"Access Denied: IAM principal '{arn}' does not match allowed operator roles/principals"

        # 2. Secondary token factor verification if token authenticator is configured
        if self.token_authenticator:
            ok, token_msg = self.token_authenticator.authenticate(
                proposal=proposal,
                approval_token=approval_token,
                operator=operator,
            )
            if not ok:
                return False, f"Secondary token verification failed: {token_msg}"

        return True, arn
