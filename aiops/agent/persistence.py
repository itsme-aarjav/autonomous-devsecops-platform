"""
Persistence adapters for AIOps agent root cause analysis results.
Provides thread-safe in-memory and local filesystem persistence with deduplication tracking.

STORAGE PERSISTENCE CLASSIFICATION:
- InMemoryPersistenceAdapter: In-process volatile storage for tests and ephemeral runs.
- LocalFilePersistenceAdapter: Local directory JSON storage (default /tmp/aiops-investigations/).
  IMPORTANT: /tmp/ storage is local to the container/pod and EPHEMERAL. It does not survive
  pod recreation, node reschedule, or horizontal scaling. In future production stages,
  durable persistence can be implemented via S3, DynamoDB, or PostgreSQL adhering to BasePersistenceAdapter.
"""

from abc import ABC, abstractmethod
import json
import os
import threading
import time
import logging
from typing import Dict, Optional, Any
from datetime import datetime, timezone

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = Exception

from .schemas import RootCauseAnalysis

logger = logging.getLogger("aiops.persistence")


class BasePersistenceAdapter(ABC):
    """Abstract persistence interface for root cause analysis results."""

    @abstractmethod
    def save_result(self, rca: RootCauseAnalysis) -> str:
        """Persist analysis result and return record identifier."""
        pass

    @abstractmethod
    def get_result(self, incident_id: str) -> Optional[RootCauseAnalysis]:
        """Retrieve analysis result by incident ID."""
        pass

    @abstractmethod
    def is_duplicate(self, dedup_key: str) -> bool:
        """Check if deduplication key has been processed."""
        pass

    @abstractmethod
    def record_dedup_key(self, dedup_key: str, incident_id: str) -> None:
        """Record deduplication key with associated incident ID."""
        pass


class InMemoryPersistenceAdapter(BasePersistenceAdapter):
    """Thread-safe in-memory storage adapter for testing and ephemeral execution."""

    def __init__(self):
        self._lock = threading.Lock()
        self._storage: Dict[str, RootCauseAnalysis] = {}
        self._dedup_keys: Dict[str, str] = {}

    def save_result(self, rca: RootCauseAnalysis) -> str:
        with self._lock:
            self._storage[rca.incident_id] = rca
            return rca.incident_id

    def get_result(self, incident_id: str) -> Optional[RootCauseAnalysis]:
        with self._lock:
            return self._storage.get(incident_id)

    def is_duplicate(self, dedup_key: str) -> bool:
        with self._lock:
            return dedup_key in self._dedup_keys

    def record_dedup_key(self, dedup_key: str, incident_id: str) -> None:
        with self._lock:
            self._dedup_keys[dedup_key] = incident_id

    def clear(self) -> None:
        """Clear all stored state (primarily for tests)."""
        with self._lock:
            self._storage.clear()
            self._dedup_keys.clear()


class LocalFilePersistenceAdapter(BasePersistenceAdapter):
    """
    File-system persistence adapter storing RCA reports in JSON format.
    NOTE: /tmp/ storage is node-local and ephemeral.
    """

    def __init__(self, base_dir: str = "/tmp/aiops-investigations"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        self._dedup_file = os.path.join(self.base_dir, "dedup_index.json")
        self._lock = threading.Lock()
        self._init_dedup_file()

    def _init_dedup_file(self) -> None:
        with self._lock:
            if not os.path.exists(self._dedup_file):
                with open(self._dedup_file, "w") as f:
                    json.dump({}, f)

    def _read_dedup_index(self) -> Dict[str, str]:
        try:
            with open(self._dedup_file, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write_dedup_index(self, index: Dict[str, str]) -> None:
        with open(self._dedup_file, "w") as f:
            json.dump(index, f, indent=2)

    def save_result(self, rca: RootCauseAnalysis) -> str:
        filepath = os.path.join(self.base_dir, f"{rca.incident_id}.json")
        with self._lock:
            with open(filepath, "w") as f:
                json.dump(rca.model_dump(), f, indent=2)
        return rca.incident_id

    def get_result(self, incident_id: str) -> Optional[RootCauseAnalysis]:
        filepath = os.path.join(self.base_dir, f"{incident_id}.json")
        with self._lock:
            if not os.path.exists(filepath):
                return None
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                    return RootCauseAnalysis.model_validate(data)
            except Exception:
                return None

    def is_duplicate(self, dedup_key: str) -> bool:
        with self._lock:
            index = self._read_dedup_index()
            return dedup_key in index

    def record_dedup_key(self, dedup_key: str, incident_id: str) -> None:
        with self._lock:
            index = self._read_dedup_index()
            index[dedup_key] = incident_id
            self._write_dedup_index(index)


class DynamoDBPersistenceAdapter(BasePersistenceAdapter):
    """
    Production durable persistence adapter storing Root Cause Analysis reports in Amazon DynamoDB.
    Enforces 30-day retention via DynamoDB TTL attribute and in-application timestamp verification.
    """

    def __init__(
        self,
        table_name: str = "boutique-aiops-rca-reports",
        dynamodb_client=None,
        region_name: str = "us-east-2",
        ttl_seconds: int = 2592000,  # 30 days
    ):
        self.table_name = table_name
        self.ttl_seconds = ttl_seconds
        self.region_name = region_name
        if dynamodb_client is not None:
            self.client = dynamodb_client
        else:
            if boto3 is None:
                raise RuntimeError("boto3 is required for DynamoDBPersistenceAdapter")
            self.client = boto3.client("dynamodb", region_name=region_name)

    def save_result(self, rca: RootCauseAnalysis) -> str:
        """Persists the Root Cause Analysis report as an item in DynamoDB."""
        now_epoch = int(time.time())
        ttl_epoch = now_epoch + self.ttl_seconds
        created_at_iso = datetime.now(timezone.utc).isoformat()

        item: Dict[str, Any] = {
            "incident_id": {"S": rca.incident_id},
            "category": {"S": rca.category},
            "confidence_score": {"N": str(rca.confidence_score)},
            "summary": {"S": rca.summary},
            "root_cause": {"S": rca.root_cause},
            "supporting_evidence": {"L": [{"S": str(s)} for s in rca.supporting_evidence]},
            "recommended_actions": {"L": [{"S": str(a)} for a in rca.recommended_actions]},
            "risks": {"L": [{"S": str(r)} for r in rca.risks]},
            "is_destructive": {"BOOL": bool(rca.is_destructive)},
            "created_at": {"S": created_at_iso},
            "ttl": {"N": str(ttl_epoch)},
        }

        try:
            self.client.put_item(
                TableName=self.table_name,
                Item=item,
            )
            logger.info(
                "Successfully persisted RCA report for incident %s to DynamoDB table %s",
                rca.incident_id,
                self.table_name,
            )
            return rca.incident_id
        except Exception as e:
            logger.error("Failed to persist RCA report for incident %s to DynamoDB: %s", rca.incident_id, str(e))
            raise

    def get_result(self, incident_id: str) -> Optional[RootCauseAnalysis]:
        """Retrieves and deserializes an RCA report from DynamoDB, validating TTL."""
        try:
            resp = self.client.get_item(
                TableName=self.table_name,
                Key={"incident_id": {"S": incident_id}},
                ConsistentRead=True,
            )
            item = resp.get("Item")
            if not item:
                return None

            # Enforce in-application TTL check (do not assume DynamoDB purges immediately)
            if "ttl" in item and "N" in item["ttl"]:
                item_ttl = int(item["ttl"]["N"])
                if item_ttl <= int(time.time()):
                    logger.warning(
                        "RCA report for %s has expired (TTL %d <= now). Treating as expired.",
                        incident_id,
                        item_ttl,
                    )
                    return None

            data = {
                "incident_id": item["incident_id"]["S"],
                "category": item["category"]["S"],
                "confidence_score": float(item["confidence_score"]["N"]),
                "summary": item["summary"]["S"],
                "root_cause": item["root_cause"]["S"],
                "supporting_evidence": [elem["S"] for elem in item.get("supporting_evidence", {}).get("L", [])],
                "recommended_actions": [elem["S"] for elem in item.get("recommended_actions", {}).get("L", [])],
                "risks": [elem["S"] for elem in item.get("risks", {}).get("L", [])],
                "is_destructive": item.get("is_destructive", {}).get("BOOL", False),
            }
            return RootCauseAnalysis.model_validate(data)
        except Exception as e:
            logger.error("Error retrieving RCA report for %s from DynamoDB: %s", incident_id, str(e))
            return None

    def is_duplicate(self, dedup_key: str) -> bool:
        """Checks if a deduplication key exists in DynamoDB."""
        try:
            resp = self.client.get_item(
                TableName=self.table_name,
                Key={"incident_id": {"S": f"dedup:{dedup_key}"}},
                ConsistentRead=True,
            )
            item = resp.get("Item")
            if not item:
                return False
            if "ttl" in item and "N" in item["ttl"]:
                if int(item["ttl"]["N"]) <= int(time.time()):
                    return False
            return True
        except Exception:
            return False

    def record_dedup_key(self, dedup_key: str, incident_id: str) -> None:
        """Records a deduplication key in DynamoDB with 30-day TTL."""
        try:
            now_epoch = int(time.time())
            ttl_epoch = now_epoch + self.ttl_seconds
            self.client.put_item(
                TableName=self.table_name,
                Item={
                    "incident_id": {"S": f"dedup:{dedup_key}"},
                    "target_incident_id": {"S": incident_id},
                    "created_at": {"S": datetime.now(timezone.utc).isoformat()},
                    "ttl": {"N": str(ttl_epoch)},
                },
            )
        except Exception as e:
            logger.warning("Failed to record dedup key %s in DynamoDB: %s", dedup_key, str(e))
