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
from typing import Dict, Optional, List
from .schemas import RemediationProposal

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


class InMemoryRemediationStore(BaseRemediationStore):
    """Thread-safe in-memory store for unit tests and local simulation."""

    def __init__(self):
        self._lock = threading.Lock()
        self._storage: Dict[str, RemediationProposal] = {}
        self._incident_index: Dict[str, str] = {}

    def save_proposal(self, proposal: RemediationProposal) -> str:
        with self._lock:
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


class DynamoDBRemediationStore(BaseRemediationStore):
    """
    Cloud-durable DynamoDB-backed remediation proposal store.

    Reuses the 'boutique-aiops-rca-reports' table (hash key: incident_id).
    Proposals are stored as JSON blobs in a 'remediation_proposal' attribute alongside
    the existing RCA report data. A 'proposal_id' attribute enables scan-based lookups.

    Uses a 30-day TTL attribute to prevent unbounded table growth.
    boto3 is imported lazily inside __init__ so the class can be imported without
    requiring boto3 in environments that only use InMemoryRemediationStore.
    """

    TABLE_NAME = "boutique-aiops-rca-reports"

    def __init__(self, region: str = "us-east-2", table_name: Optional[str] = None):
        try:
            import boto3
            from boto3.dynamodb.conditions import Attr
        except ImportError as exc:
            raise ImportError(
                "boto3 is required for DynamoDBRemediationStore. "
                "Install it with: pip install boto3"
            ) from exc

        self._boto3 = boto3
        self._Attr = Attr
        self._table_name = table_name or self.TABLE_NAME
        self._ddb = boto3.resource("dynamodb", region_name=region)
        self._table = self._ddb.Table(self._table_name)

    def save_proposal(self, proposal: RemediationProposal) -> str:
        """Persists or updates a remediation proposal in DynamoDB."""
        item = {
            "incident_id": proposal.incident_id,
            "proposal_id": proposal.proposal_id,
            "remediation_proposal": json.dumps(proposal.model_dump(mode="json")),
            "proposal_status": proposal.status.value,
            "ttl": int(time.time()) + 30 * 86400,  # 30-day TTL
        }
        self._table.put_item(Item=item)
        return proposal.proposal_id

    def get_proposal(self, proposal_id: str) -> Optional[RemediationProposal]:
        """Retrieves a proposal by proposal_id via table scan (small dataset — acceptable)."""
        response = self._table.scan(
            FilterExpression=self._Attr("proposal_id").eq(proposal_id)
        )
        items = response.get("Items", [])
        if not items:
            return None
        raw = items[0].get("remediation_proposal")
        if not raw:
            return None
        try:
            return RemediationProposal.model_validate(json.loads(raw))
        except Exception:
            return None

    def get_proposal_by_incident(self, incident_id: str) -> Optional[RemediationProposal]:
        """Retrieves a proposal by incident_id via primary key lookup (O(1))."""
        response = self._table.get_item(Key={"incident_id": incident_id})
        item = response.get("Item")
        if not item or "remediation_proposal" not in item:
            return None
        try:
            return RemediationProposal.model_validate(json.loads(item["remediation_proposal"]))
        except Exception:
            return None

    def list_proposals(self, limit: int = 50) -> List[RemediationProposal]:
        """Lists recent proposals ordered by creation time descending."""
        response = self._table.scan(
            FilterExpression=self._Attr("remediation_proposal").exists()
        )
        proposals: List[RemediationProposal] = []
        for item in response.get("Items", []):
            raw = item.get("remediation_proposal")
            if not raw:
                continue
            try:
                proposals.append(RemediationProposal.model_validate(json.loads(raw)))
            except Exception:
                continue
        proposals.sort(key=lambda p: p.created_at, reverse=True)
        return proposals[:limit]

