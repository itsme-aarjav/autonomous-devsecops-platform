"""
Autonomous AIOps Platform — Remediation Proposal Persistence & Audit Store
"""

import os
import json
import time
import uuid
import threading
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, Optional, List
from .schemas import RemediationProposal, RemediationStatus

logger = logging.getLogger("aiops.remediation.store")


class BaseRemediationStore(ABC):
    """Abstract persistence interface for remediation proposals and PR audit records."""

    @abstractmethod
    def save_proposal(self, proposal: RemediationProposal) -> str:
        """Saves or updates a remediation proposal."""
        pass

    @abstractmethod
    def get_proposal(self, proposal_id: str) -> Optional[RemediationProposal]:
        """Retrieves proposal by proposal_id."""
        pass

    @abstractmethod
    def get_proposal_by_incident(self, incident_id: str) -> Optional[RemediationProposal]:
        """Retrieves proposal by incident_id."""
        pass

    @abstractmethod
    def list_proposals(self, limit: int = 50) -> List[RemediationProposal]:
        """Lists recent proposals."""
        pass

    def atomic_transition_status(
        self,
        proposal_id: str,
        expected_statuses: List[str],
        new_status: str,
        updated_proposal: RemediationProposal,
    ) -> bool:
        """Atomically transitions proposal status. Falls back to save_proposal if unspecialized."""
        current = self.get_proposal(proposal_id)
        if not current or current.status.value not in expected_statuses:
            return False
        self.save_proposal(updated_proposal)
        return True


class InMemoryRemediationStore(BaseRemediationStore):
    """Thread-safe in-memory store for unit tests and local simulation."""

    def __init__(self):
        self._lock = threading.Lock()
        self._storage: Dict[str, RemediationProposal] = {}
        self._incident_index: Dict[str, str] = {}

    def save_proposal(self, proposal: RemediationProposal) -> str:
        with self._lock:
            current = self._storage.get(proposal.proposal_id)
            if current and current.status in (RemediationStatus.OPERATOR_REJECTED, RemediationStatus.APPLIED_TO_MAIN):
                if proposal.status != current.status:
                    raise PermissionError(
                        f"Cannot overwrite terminal proposal '{proposal.proposal_id}' (status: {current.status.value}) with status '{proposal.status.value}'."
                    )
            self._storage[proposal.proposal_id] = proposal.model_copy(deep=True)
            self._incident_index[proposal.incident_id] = proposal.proposal_id
            return proposal.proposal_id

    def get_proposal(self, proposal_id: str) -> Optional[RemediationProposal]:
        with self._lock:
            prop = self._storage.get(proposal_id)
            return prop.model_copy(deep=True) if prop else None

    def get_proposal_by_incident(self, incident_id: str) -> Optional[RemediationProposal]:
        with self._lock:
            prop_id = self._incident_index.get(incident_id)
            if prop_id:
                prop = self._storage.get(prop_id)
                return prop.model_copy(deep=True) if prop else None
            return None

    def list_proposals(self, limit: int = 50) -> List[RemediationProposal]:
        with self._lock:
            items = [p.model_copy(deep=True) for p in self._storage.values()]
            return items[-limit:]

    def atomic_transition_status(
        self,
        proposal_id: str,
        expected_statuses: List[str],
        new_status: str,
        updated_proposal: RemediationProposal,
    ) -> bool:
        with self._lock:
            current = self._storage.get(proposal_id)
            if not current or current.status.value not in expected_statuses:
                return False
            self._storage[proposal_id] = updated_proposal.model_copy(deep=True)
            self._incident_index[updated_proposal.incident_id] = proposal_id
            return True


class LocalFileRemediationStore(BaseRemediationStore):
    """Local filesystem persistence storing proposals as JSON files."""

    def __init__(self, base_dir: str = "/tmp/aiops-investigations"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        self._lock = threading.Lock()

    def save_proposal(self, proposal: RemediationProposal) -> str:
        filename = f"{proposal.incident_id}_remediation.json"
        filepath = os.path.join(self.base_dir, filename)
        tmp_filepath = os.path.join(self.base_dir, f".{filename}.tmp.{uuid.uuid4().hex}")
        with self._lock:
            existing = self.get_proposal(proposal.proposal_id)
            if existing and existing.status in (RemediationStatus.OPERATOR_REJECTED, RemediationStatus.APPLIED_TO_MAIN):
                if proposal.status != existing.status:
                    raise PermissionError(
                        f"Cannot overwrite terminal proposal '{proposal.proposal_id}' (status: {existing.status.value}) with status '{proposal.status.value}'."
                    )
            with open(tmp_filepath, "w", encoding="utf-8") as f:
                json.dump(proposal.model_dump(mode="json"), f, indent=2)
            os.replace(tmp_filepath, filepath)
        return proposal.proposal_id

    def get_proposal(self, proposal_id: str) -> Optional[RemediationProposal]:
        with self._lock:
            for fname in os.listdir(self.base_dir):
                if fname.endswith("_remediation.json"):
                    fpath = os.path.join(self.base_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            if data.get("proposal_id") == proposal_id:
                                return RemediationProposal.model_validate(data)
                    except Exception:
                        continue
        return None

    def get_proposal_by_incident(self, incident_id: str) -> Optional[RemediationProposal]:
        filename = f"{incident_id}_remediation.json"
        filepath = os.path.join(self.base_dir, filename)
        with self._lock:
            if not os.path.exists(filepath):
                return None
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return RemediationProposal.model_validate(data)
            except Exception:
                return None

    def list_proposals(self, limit: int = 50) -> List[RemediationProposal]:
        proposals = []
        with self._lock:
            for fname in os.listdir(self.base_dir):
                if fname.endswith("_remediation.json"):
                    fpath = os.path.join(self.base_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            proposals.append(RemediationProposal.model_validate(data))
                    except Exception:
                        continue
        return proposals[-limit:]

    def atomic_transition_status(
        self,
        proposal_id: str,
        expected_statuses: List[str],
        new_status: str,
        updated_proposal: RemediationProposal,
    ) -> bool:
        with self._lock:
            current = self.get_proposal(proposal_id)
            if not current or current.status.value not in expected_statuses:
                return False
            self.save_proposal(updated_proposal)
            return True


class DynamoDBRemediationStore(BaseRemediationStore):
    """
    Cloud-durable DynamoDB-backed remediation proposal store.

    Uses dedicated table 'boutique-aiops-remediations' (hash key: proposal_id).
    Features:
    - O(1) point lookups by proposal_id via primary key GetItem.
    - O(1) lookups by incident_id via GSI 'incident-index' Query.
    - Concurrency-safe atomic state transitions via DynamoDB ConditionExpression.
    - Preserves audit evidence with 90-day retention TTL (not purged prematurely).
    - If pointed to legacy 'boutique-aiops-rca-reports' table, safely performs UpdateItem
      to prevent overwriting or deleting existing RCA reports.
    """

    DEFAULT_TABLE_NAME = "boutique-aiops-remediations"
    RCA_TABLE_NAME = "boutique-aiops-rca-reports"

    def __init__(self, region: str = "us-east-2", table_name: Optional[str] = None):
        try:
            import boto3
            from boto3.dynamodb.conditions import Attr, Key
            from botocore.exceptions import ClientError
        except ImportError as exc:
            raise ImportError(
                "boto3 is required for DynamoDBRemediationStore. "
                "Install it with: pip install boto3"
            ) from exc

        self._boto3 = boto3
        self._Attr = Attr
        self._Key = Key
        self._ClientError = ClientError
        self._table_name = table_name or os.getenv("AIOPS_DYNAMODB_REMEDIATIONS_TABLE", self.DEFAULT_TABLE_NAME)
        self._ddb = boto3.resource("dynamodb", region_name=region)
        self._table = self._ddb.Table(self._table_name)
        self._is_rca_table = (self._table_name == self.RCA_TABLE_NAME)

    def save_proposal(self, proposal: RemediationProposal) -> str:
        """Persists or updates a remediation proposal in DynamoDB."""
        # Defense-in-depth: Never overwrite terminal status
        existing = self.get_proposal(proposal.proposal_id)
        if existing and existing.status in (RemediationStatus.OPERATOR_REJECTED, RemediationStatus.APPLIED_TO_MAIN):
            if proposal.status != existing.status:
                raise PermissionError(
                    f"Cannot overwrite terminal proposal '{proposal.proposal_id}' (status: {existing.status.value}) with status '{proposal.status.value}'."
                )

        now_epoch = int(time.time())
        ttl_epoch = now_epoch + 90 * 86400  # 90-day retention for audit evidence

        if self._is_rca_table:
            # DEFENSE-IN-DEPTH: When pointing to RCA table, update attributes only.
            # NEVER call put_item, preserving all RCA diagnostic report attributes!
            self._table.update_item(
                Key={"incident_id": proposal.incident_id},
                UpdateExpression=(
                    "SET remediation_proposal = :p, proposal_status = :s, "
                    "proposal_id = :pid, proposal_ttl = :t"
                ),
                ExpressionAttributeValues={
                    ":p": json.dumps(proposal.model_dump(mode="json")),
                    ":s": proposal.status.value,
                    ":pid": proposal.proposal_id,
                    ":t": ttl_epoch,
                },
            )
            return proposal.proposal_id

        # Dedicated table: primary key is proposal_id
        item = {
            "proposal_id": proposal.proposal_id,
            "incident_id": proposal.incident_id,
            "remediation_proposal": json.dumps(proposal.model_dump(mode="json")),
            "proposal_status": proposal.status.value,
            "workload": proposal.workload,
            "category": proposal.category,
            "created_at": proposal.created_at.isoformat(),
            "ttl": ttl_epoch,
        }
        self._table.put_item(Item=item)
        return proposal.proposal_id

    def get_proposal(self, proposal_id: str) -> Optional[RemediationProposal]:
        """Retrieves a proposal by proposal_id. O(1) point lookup on dedicated table."""
        if self._is_rca_table:
            response = self._table.scan(
                FilterExpression=self._Attr("proposal_id").eq(proposal_id)
            )
            items = response.get("Items", []) if isinstance(response, dict) else []
            if not items:
                return None
            first = items[0] if isinstance(items, list) and items else None
            raw = first.get("remediation_proposal") if isinstance(first, dict) else None
            return RemediationProposal.model_validate(json.loads(raw)) if raw and isinstance(raw, str) else None

        response = self._table.get_item(
            Key={"proposal_id": proposal_id},
            ConsistentRead=True,
        )
        item = response.get("Item") if isinstance(response, dict) else None
        if not item or not isinstance(item, dict) or "remediation_proposal" not in item:
            return None
        try:
            raw = item["remediation_proposal"]
            return RemediationProposal.model_validate(json.loads(raw)) if isinstance(raw, str) else None
        except Exception:
            return None

    def get_proposal_by_incident(self, incident_id: str) -> Optional[RemediationProposal]:
        """Retrieves proposal by incident_id. Uses GSI incident-index on dedicated table."""
        if self._is_rca_table:
            response = self._table.get_item(Key={"incident_id": incident_id}, ConsistentRead=True)
            item = response.get("Item")
            if not item or "remediation_proposal" not in item:
                return None
            try:
                return RemediationProposal.model_validate(json.loads(item["remediation_proposal"]))
            except Exception:
                return None

        # Dedicated table: query GSI incident-index
        try:
            response = self._table.query(
                IndexName="incident-index",
                KeyConditionExpression=self._Key("incident_id").eq(incident_id),
            )
            items = response.get("Items", [])
            if items and "remediation_proposal" in items[0]:
                return RemediationProposal.model_validate(json.loads(items[0]["remediation_proposal"]))
        except Exception as e:
            logger.warning("GSI query failed on incident-index (%s), falling back to scan: %s", incident_id, e)

        # Fallback query / scan if GSI is indexing
        response = self._table.scan(
            FilterExpression=self._Attr("incident_id").eq(incident_id)
        )
        items = response.get("Items", [])
        if items and "remediation_proposal" in items[0]:
            return RemediationProposal.model_validate(json.loads(items[0]["remediation_proposal"]))
        return None

    def list_proposals(self, limit: int = 50) -> List[RemediationProposal]:
        """Lists proposals with pagination support, ordered by created_at descending."""
        proposals: List[RemediationProposal] = []
        scan_kwargs = {"Limit": min(limit, 100)}
        if self._is_rca_table:
            scan_kwargs["FilterExpression"] = self._Attr("remediation_proposal").exists()

        done = False
        while not done:
            response = self._table.scan(**scan_kwargs)
            for item in response.get("Items", []):
                raw = item.get("remediation_proposal")
                if not raw:
                    continue
                try:
                    proposals.append(RemediationProposal.model_validate(json.loads(raw)))
                except Exception:
                    continue

            lek = response.get("LastEvaluatedKey")
            if lek and len(proposals) < limit:
                scan_kwargs["ExclusiveStartKey"] = lek
            else:
                done = True

        proposals.sort(key=lambda p: p.created_at, reverse=True)
        return proposals[:limit]

    def atomic_transition_status(
        self,
        proposal_id: str,
        expected_statuses: List[str],
        new_status: str,
        updated_proposal: RemediationProposal,
    ) -> bool:
        """
        Atomically updates proposal status using DynamoDB conditional check.
        Ensures concurrent approvals or rejections fail closed without overwriting.
        """
        now_epoch = int(time.time())
        ttl_epoch = now_epoch + 90 * 86400

        cond = self._Attr("proposal_status").is_in(expected_statuses)

        if self._is_rca_table:
            try:
                self._table.update_item(
                    Key={"incident_id": updated_proposal.incident_id},
                    UpdateExpression=(
                        "SET remediation_proposal = :p, proposal_status = :s, "
                        "proposal_id = :pid, proposal_ttl = :t"
                    ),
                    ExpressionAttributeValues={
                        ":p": json.dumps(updated_proposal.model_dump(mode="json")),
                        ":s": new_status,
                        ":pid": proposal_id,
                        ":t": ttl_epoch,
                    },
                    ConditionExpression=cond,
                )
                return True
            except self._ClientError as err:
                if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                    return False
                raise

        item = {
            "proposal_id": updated_proposal.proposal_id,
            "incident_id": updated_proposal.incident_id,
            "remediation_proposal": json.dumps(updated_proposal.model_dump(mode="json")),
            "proposal_status": new_status,
            "workload": updated_proposal.workload,
            "category": updated_proposal.category,
            "created_at": updated_proposal.created_at.isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "ttl": ttl_epoch,
        }
        try:
            self._table.put_item(
                Item=item,
                ConditionExpression=cond,
            )
            return True
        except self._ClientError as err:
            if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise

