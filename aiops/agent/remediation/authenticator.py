"""
Autonomous AIOps Platform — Human Approval Authenticator Interface & Implementations
"""

import hmac
from abc import ABC, abstractmethod
from typing import Optional, Dict, Tuple
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
