"""
Autonomous AIOps Platform — Episode Lifecycle & Deduplication Store

Provides thread-safe in-memory and durable Amazon DynamoDB episode tracking.
Enforces:
- 24-hour episode retention with in-application TTL verification.
- Atomic lease claiming and stale-lease recovery for worker resilience.
- Dual-write prevention (episodes are claimed by workers after SQS enqueue).
- Out-of-order resolved alert protection (resolved-before-firing and mid-flight resolution).
"""

import time
import hashlib
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = Exception

from .schemas import AlertItem

logger = logging.getLogger("aiops.episode_store")


class EpisodeRecord(dict):
    """Episode record supporting both dictionary and attribute access for backward compatibility."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'EpisodeRecord' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


class BaseEpisodeStore(ABC):
    """Abstract interface for incident episode deduplication and lifecycle management."""

    @staticmethod
    def calculate_episode_id(cluster_identity: str, fingerprint: str, starts_at: datetime) -> str:
        """Calculates deterministic SHA256 episode identifier."""
        starts_at_str = starts_at.isoformat()
        raw = f"{cluster_identity}:{fingerprint}:{starts_at_str}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @abstractmethod
    def record_resolved_episode(self, episode_id: str, alert: AlertItem) -> bool:
        """Records or updates an episode to resolved status."""
        pass

    @abstractmethod
    def is_episode_active(self, episode_id: str) -> bool:
        """Returns True if the episode is currently active and firing within TTL."""
        pass

    @abstractmethod
    def is_episode_resolved(self, episode_id: str) -> bool:
        """Returns True if the episode has been marked resolved within TTL."""
        pass

    @abstractmethod
    def get_episode(self, episode_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves episode record if present and not expired."""
        pass

    @abstractmethod
    def claim_episode(
        self,
        episode_id: str,
        alert: AlertItem,
        worker_id: str,
        lease_duration: int = 180,
        cluster_identity: str = "boutique-dev-eks",
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Atomically claims an episode for worker investigation.
        Returns: (claimed, episode_data, reason)
        Reasons: 'claimed', 'resolved', 'completed', 'locked', 'contention'
        """
        pass

    @abstractmethod
    def renew_lease(self, episode_id: str, worker_id: str, lease_duration: int = 180) -> bool:
        """Extends worker lease expiration."""
        pass

    @abstractmethod
    def complete_episode(self, episode_id: str, worker_id: str) -> bool:
        """Marks episode investigation as completed."""
        pass

    @abstractmethod
    def fail_episode(self, episode_id: str, worker_id: str, error_message: str) -> bool:
        """Marks episode investigation as failed, releasing lease for retry."""
        pass

    @abstractmethod
    def mark_dead_lettered(self, episode_id: str, worker_id: str, error_message: str) -> bool:
        """Marks episode investigation as terminal failure / dead-lettered."""
        pass

    @abstractmethod
    def reconcile_dead_lettered(self, episode_id: str, error_message: str = "Reconciled from SQS DLQ") -> bool:
        """
        Reconciles an episode to dead_lettered if eligible (stale/failed/queued).
        Must not overwrite episodes already marked completed or resolved.
        Only reconciles expired/stale investigations or eligible failed/queued episodes.
        """
        pass

    @abstractmethod
    def mark_resolved_cancelled(self, episode_id: str, worker_id: Optional[str] = None) -> bool:
        """Marks episode as cancelled because alert resolved before/during investigation."""
        pass

    @abstractmethod
    def record_model_disabled(self, episode_id: str, worker_id: Optional[str] = None) -> bool:
        """Records intake when Bedrock model execution is disabled by policy."""
        pass


class InMemoryEpisodeStore(BaseEpisodeStore):
    """Thread-safe in-memory episode store for local tests and offline execution."""

    def __init__(self, ttl_seconds: int = 86400):
        import threading
        self.ttl_seconds = ttl_seconds
        self._episodes: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _is_expired(self, item: Dict[str, Any], now: float) -> bool:
        return item.get("ttl", 0) <= now

    def record_resolved_episode(self, episode_id: str, alert: AlertItem) -> bool:
        with self._lock:
            now = time.time()
            existing = self._episodes.get(episode_id)
            if existing and not self._is_expired(existing, now):
                existing.update({"status": "resolved", "resolved_at": now, "updated_at": now, "ttl": now + self.ttl_seconds})
                if existing.get("investigation_status") in (None, "queued"):
                    existing["investigation_status"] = "resolved_no_investigation"
                return True

            self._episodes[episode_id] = EpisodeRecord({
                "episode_id": episode_id,
                "fingerprint": alert.fingerprint,
                "starts_at": alert.startsAt.isoformat(),
                "status": "resolved",
                "alert_name": alert.labels.get("alertname", "unknown"),
                "workload": alert.labels.get("workload") or alert.labels.get("pod") or "unknown",
                "namespace": alert.labels.get("namespace", "boutique"),
                "investigation_status": "resolved_no_investigation",
                "accepted_at": now,
                "updated_at": now,
                "resolved_at": now,
                "ttl": now + self.ttl_seconds,
                "attempt_count": 0,
                "lease_owner": None,
                "lease_until": 0,
            })
            return True

    def is_episode_active(self, episode_id: str) -> bool:
        with self._lock:
            rec = self._episodes.get(episode_id)
            return bool(rec and not self._is_expired(rec, time.time()) and rec.get("status") == "firing")

    def is_episode_active_or_queued(self, episode_id: str) -> bool:
        """Backwards-compatibility alias for existing test suites."""
        return self.is_episode_active(episode_id)

    def record_accepted_episode(
        self,
        ep_id: str,
        fingerprint: str = "",
        starts_at: str = "",
        alert_name: str = "",
        workload: str = "",
        namespace: str = "boutique",
        is_truncated: bool = False,
        truncated_count: int = 0,
    ) -> None:
        """Backwards-compatibility method for in-memory tests."""
        with self._lock:
            now = time.time()
            self._episodes[ep_id] = EpisodeRecord({
                "episode_id": ep_id,
                "fingerprint": fingerprint,
                "starts_at": starts_at,
                "status": "firing",
                "alert_name": alert_name,
                "workload": workload,
                "namespace": namespace,
                "investigation_status": "queued",
                "accepted_at": now,
                "updated_at": now,
                "ttl": now + self.ttl_seconds,
                "is_truncated": is_truncated,
                "truncated_count": truncated_count,
            })

    def is_episode_resolved(self, episode_id: str) -> bool:
        with self._lock:
            rec = self._episodes.get(episode_id)
            return bool(rec and not self._is_expired(rec, time.time()) and rec.get("status") == "resolved")

    def get_episode(self, episode_id: str) -> Optional[EpisodeRecord]:
        with self._lock:
            now = time.time()
            rec = self._episodes.get(episode_id)
            if not rec or self._is_expired(rec, now):
                return None
            return rec

    def claim_episode(
        self,
        episode_id: str,
        alert: AlertItem,
        worker_id: str,
        lease_duration: int = 180,
        cluster_identity: str = "boutique-dev-eks",
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        with self._lock:
            now = time.time()
            rec = self._episodes.get(episode_id)

            if rec and not self._is_expired(rec, now):
                if rec.get("status") == "resolved":
                    return False, dict(rec), "resolved"
                if rec.get("investigation_status") == "completed":
                    return False, dict(rec), "completed"
                # Check active lease by another worker
                if (
                    rec.get("investigation_status") == "investigating"
                    and rec.get("lease_until", 0) > now
                    and rec.get("lease_owner") != worker_id
                ):
                    return False, dict(rec), "locked"

                # Stale lease or previously failed / queued: claim it
                rec["investigation_status"] = "investigating"
                rec["lease_owner"] = worker_id
                rec["lease_until"] = now + lease_duration
                rec["attempt_count"] = rec.get("attempt_count", 0) + 1
                rec["updated_at"] = now
                return True, dict(rec), "claimed"

            # Brand new episode (Dual-write prevention: first time seen by worker)
            new_rec = EpisodeRecord({
                "episode_id": episode_id,
                "fingerprint": alert.fingerprint,
                "starts_at": alert.startsAt.isoformat(),
                "status": "firing",
                "alert_name": alert.labels.get("alertname", "unknown"),
                "workload": alert.labels.get("workload") or alert.labels.get("pod") or "unknown",
                "namespace": alert.labels.get("namespace", "boutique"),
                "investigation_status": "investigating",
                "accepted_at": now,
                "updated_at": now,
                "ttl": now + self.ttl_seconds,
                "lease_owner": worker_id,
                "lease_until": now + lease_duration,
                "attempt_count": 1,
            })
            self._episodes[episode_id] = new_rec
            return True, dict(new_rec), "claimed"

    def renew_lease(self, episode_id: str, worker_id: str, lease_duration: int = 180) -> bool:
        with self._lock:
            rec = self._episodes.get(episode_id)
            if not rec or rec.get("lease_owner") != worker_id:
                return False
            rec["lease_until"] = time.time() + lease_duration
            return True

    def _release_rec(self, rec: Dict[str, Any], status: str, error_message: Optional[str] = None) -> bool:
        rec["investigation_status"] = status
        rec["lease_owner"] = None
        rec["lease_until"] = 0
        rec["updated_at"] = time.time()
        if error_message is not None:
            rec["last_error"] = error_message
        return True

    def complete_episode(self, episode_id: str, worker_id: str) -> bool:
        with self._lock:
            rec = self._episodes.get(episode_id)
            if not rec or self._is_expired(rec, time.time()):
                return False
            if (
                rec.get("lease_owner") != worker_id
                or rec.get("status") != "firing"
                or rec.get("investigation_status") != "investigating"
            ):
                return False
            return self._release_rec(rec, "completed")

    def fail_episode(self, episode_id: str, worker_id: str, error_message: str) -> bool:
        with self._lock:
            rec = self._episodes.get(episode_id)
            if not rec or self._is_expired(rec, time.time()):
                return False
            if rec.get("lease_owner") != worker_id or rec.get("investigation_status") != "investigating":
                return False
            return self._release_rec(rec, "failed", error_message)

    def mark_dead_lettered(self, episode_id: str, worker_id: str, error_message: str) -> bool:
        with self._lock:
            rec = self._episodes.get(episode_id)
            if not rec or self._is_expired(rec, time.time()):
                return False
            if rec.get("lease_owner") != worker_id or rec.get("investigation_status") != "investigating":
                return False
            return self._release_rec(rec, "dead_lettered", error_message)

    def reconcile_dead_lettered(self, episode_id: str, error_message: str = "Reconciled from SQS DLQ") -> bool:
        with self._lock:
            rec = self._episodes.get(episode_id)
            now = time.time()
            if not rec or self._is_expired(rec, now) or rec.get("status") == "resolved":
                return False
            inv = rec.get("investigation_status")
            if inv in ("completed", "resolved_cancelled"):
                return False
            if not ((inv == "investigating" and rec.get("lease_until", 0) <= now) or inv in ("failed", "queued")):
                return False
            return self._release_rec(rec, "dead_lettered", error_message)

    def mark_resolved_cancelled(self, episode_id: str, worker_id: Optional[str] = None) -> bool:
        with self._lock:
            rec = self._episodes.get(episode_id)
            if not rec:
                return False
            if worker_id and rec.get("lease_owner") and rec.get("lease_owner") != worker_id:
                return False
            return self._release_rec(rec, "resolved_cancelled")

    def record_model_disabled(self, episode_id: str, worker_id: Optional[str] = None) -> bool:
        with self._lock:
            rec = self._episodes.get(episode_id)
            if not rec or self._is_expired(rec, time.time()):
                return False
            if worker_id and (rec.get("lease_owner") != worker_id or rec.get("investigation_status") != "investigating"):
                return False
            return self._release_rec(rec, "model_disabled")

    def clear(self) -> None:
        with self._lock:
            self._episodes.clear()


class DynamoDBEpisodeStore(BaseEpisodeStore):
    """
    Production durable episode store backed by Amazon DynamoDB.
    Guarantees atomic conditional updates, stale-lease reclamation, and 24-hour TTL lifecycle.
    """

    def __init__(
        self,
        table_name: str = "boutique-aiops-episodes",
        dynamodb_client=None,
        region_name: str = "us-east-2",
        ttl_seconds: int = 86400,
    ):
        self.table_name = table_name
        self.ttl_seconds = ttl_seconds
        self.region_name = region_name
        if dynamodb_client is not None:
            self.client = dynamodb_client
        else:
            if boto3 is None:
                raise RuntimeError("boto3 is required for DynamoDBEpisodeStore")
            self.client = boto3.client("dynamodb", region_name=region_name)

    def _deserialize_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Converts low-level DynamoDB AttributeValue dict to standard Python types."""
        res: Dict[str, Any] = {}
        for k, v in item.items():
            if "S" in v:
                res[k] = v["S"]
            elif "N" in v:
                val = v["N"]
                res[k] = float(val) if "." in val else int(val)
            elif "BOOL" in v:
                res[k] = v["BOOL"]
            elif "NULL" in v:
                res[k] = None
        return res

    def record_resolved_episode(self, episode_id: str, alert: AlertItem) -> bool:
        now = int(time.time())
        ttl = now + self.ttl_seconds
        try:
            self.client.update_item(
                TableName=self.table_name,
                Key={"episode_id": {"S": episode_id}},
                UpdateExpression="""
                    SET #st = :resolved,
                        fingerprint = if_not_exists(fingerprint, :fp),
                        starts_at = if_not_exists(starts_at, :sa),
                        alert_name = if_not_exists(alert_name, :an),
                        workload = if_not_exists(workload, :wl),
                        namespace = if_not_exists(namespace, :ns),
                        investigation_status = if_not_exists(investigation_status, :res_status),
                        resolved_at = :now,
                        updated_at = :now,
                        #ttl = :ttl
                """,
                ExpressionAttributeNames={
                    "#st": "status",
                    "#ttl": "ttl",
                },
                ExpressionAttributeValues={
                    ":resolved": {"S": "resolved"},
                    ":res_status": {"S": "resolved_no_investigation"},
                    ":fp": {"S": alert.fingerprint},
                    ":sa": {"S": alert.startsAt.isoformat()},
                    ":an": {"S": alert.labels.get("alertname", "unknown")},
                    ":wl": {"S": alert.labels.get("workload") or alert.labels.get("pod") or "unknown"},
                    ":ns": {"S": alert.labels.get("namespace", "boutique")},
                    ":now": {"N": str(now)},
                    ":ttl": {"N": str(ttl)},
                },
            )
            logger.info("Recorded resolved episode %s in DynamoDB table %s", episode_id, self.table_name)
            return True
        except Exception as e:
            logger.error("Failed to record resolved episode %s in DynamoDB: %s", episode_id, str(e))
            raise

    def is_episode_active(self, episode_id: str) -> bool:
        ep = self.get_episode(episode_id)
        return bool(ep and ep.get("status") == "firing")

    def is_episode_resolved(self, episode_id: str) -> bool:
        ep = self.get_episode(episode_id)
        return bool(ep and ep.get("status") == "resolved")

    def get_episode(self, episode_id: str) -> Optional[Dict[str, Any]]:
        now = int(time.time())
        try:
            resp = self.client.get_item(
                TableName=self.table_name,
                Key={"episode_id": {"S": episode_id}},
                ConsistentRead=True,
            )
            item = resp.get("Item")
            if not item:
                return None
            data = self._deserialize_item(item)
            # Enforce in-application TTL check
            if data.get("ttl", 0) <= now:
                logger.info("Episode %s TTL has expired (ttl=%s, now=%s). Treating as non-existent.", episode_id, data.get("ttl"), now)
                return None
            return EpisodeRecord(data)
        except Exception as e:
            logger.error("Failed to get episode %s from DynamoDB: %s", episode_id, str(e))
            raise

    def claim_episode(
        self,
        episode_id: str,
        alert: AlertItem,
        worker_id: str,
        lease_duration: int = 180,
        cluster_identity: str = "boutique-dev-eks",
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        now = int(time.time())
        ttl = now + self.ttl_seconds
        lease_until = now + lease_duration

        # 1. Try atomic first-time insert (Dual-write prevention: worker creates episode after SQS dequeue)
        put_item = {
            "episode_id": {"S": episode_id},
            "fingerprint": {"S": alert.fingerprint},
            "starts_at": {"S": alert.startsAt.isoformat()},
            "status": {"S": "firing"},
            "investigation_status": {"S": "investigating"},
            "alert_name": {"S": alert.labels.get("alertname", "unknown")},
            "workload": {"S": alert.labels.get("workload") or alert.labels.get("pod") or "unknown"},
            "namespace": {"S": alert.labels.get("namespace", "boutique")},
            "accepted_at": {"N": str(now)},
            "updated_at": {"N": str(now)},
            "ttl": {"N": str(ttl)},
            "lease_owner": {"S": worker_id},
            "lease_until": {"N": str(lease_until)},
            "attempt_count": {"N": "1"},
        }
        try:
            self.client.put_item(
                TableName=self.table_name,
                Item=put_item,
                ConditionExpression="attribute_not_exists(episode_id)",
            )
            logger.info("Worker %s successfully claimed new episode %s", worker_id, episode_id)
            return True, self._deserialize_item(put_item), "claimed"
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                logger.error("DynamoDB error putting new episode %s: %s", episode_id, str(e))
                raise

        # 2. Episode already exists: fetch existing item and evaluate state
        existing = self.get_episode(episode_id)
        if not existing:
            # Item either expired or missing; attempt atomic conditional write that only permits
            # creating a missing item or reclaiming a genuinely expired item without overwriting
            # a concurrent resolved event.
            put_item["attempt_count"] = {"N": "1"}
            try:
                self.client.put_item(
                    TableName=self.table_name,
                    Item=put_item,
                    ConditionExpression="attribute_not_exists(episode_id) OR #ttl <= :now",
                    ExpressionAttributeNames={"#ttl": "ttl"},
                    ExpressionAttributeValues={":now": {"N": str(now)}},
                )
                logger.info("Worker %s successfully claimed expired episode %s", worker_id, episode_id)
                return True, self._deserialize_item(put_item), "claimed"
            except ClientError as e:
                if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                    logger.info("Episode %s concurrently recreated or resolved. Rejecting expired reclaim.", episode_id)
                    return False, None, "contention"
                logger.error("Error claiming expired episode %s: %s", episode_id, str(e))
                raise

        if existing.get("status") == "resolved":
            logger.info("Episode %s is already resolved. Rejecting claim.", episode_id)
            return False, existing, "resolved"

        if existing.get("investigation_status") == "completed":
            logger.info("Episode %s investigation already completed. Rejecting duplicate claim.", episode_id)
            return False, existing, "completed"

        if (
            existing.get("investigation_status") == "investigating"
            and existing.get("lease_until", 0) > now
            and existing.get("lease_owner") != worker_id
        ):
            logger.warning(
                "Episode %s is locked by active worker %s until %s. Rejecting claim.",
                episode_id,
                existing.get("lease_owner"),
                existing.get("lease_until"),
            )
            return False, existing, "locked"

        # 3. Episode is eligible for reclaim (stale lease, failed, or queued)
        try:
            self.client.update_item(
                TableName=self.table_name,
                Key={"episode_id": {"S": episode_id}},
                UpdateExpression="""
                    SET investigation_status = :inv,
                        lease_owner = :owner,
                        lease_until = :new_lease,
                        attempt_count = if_not_exists(attempt_count, :zero) + :one,
                        updated_at = :now
                """,
                ConditionExpression="""
                    attribute_exists(episode_id) AND
                    #st = :firing AND
                    investigation_status <> :completed AND
                    (lease_until <= :now OR investigation_status IN (:failed, :queued) OR lease_owner = :owner)
                """,
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={
                    ":inv": {"S": "investigating"},
                    ":owner": {"S": worker_id},
                    ":new_lease": {"N": str(lease_until)},
                    ":zero": {"N": "0"},
                    ":one": {"N": "1"},
                    ":now": {"N": str(now)},
                    ":firing": {"S": "firing"},
                    ":completed": {"S": "completed"},
                    ":failed": {"S": "failed"},
                    ":queued": {"S": "queued"},
                },
            )
            existing["investigation_status"] = "investigating"
            existing["lease_owner"] = worker_id
            existing["lease_until"] = lease_until
            existing["attempt_count"] = existing.get("attempt_count", 0) + 1
            logger.info("Worker %s successfully reclaimed episode %s (Attempt %d)", worker_id, episode_id, existing["attempt_count"])
            return True, existing, "claimed"
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                logger.warning("Contention claiming episode %s by worker %s", episode_id, worker_id)
                return False, existing, "contention"
            logger.error("Error updating episode claim for %s: %s", episode_id, str(e))
            raise

    def renew_lease(self, episode_id: str, worker_id: str, lease_duration: int = 180) -> bool:
        now = int(time.time())
        new_lease = now + lease_duration
        try:
            self.client.update_item(
                TableName=self.table_name,
                Key={"episode_id": {"S": episode_id}},
                UpdateExpression="SET lease_until = :new_lease, updated_at = :now",
                ConditionExpression="attribute_exists(episode_id) AND lease_owner = :owner AND investigation_status = :inv",
                ExpressionAttributeValues={
                    ":new_lease": {"N": str(new_lease)},
                    ":now": {"N": str(now)},
                    ":owner": {"S": worker_id},
                    ":inv": {"S": "investigating"},
                },
            )
            return True
        except ClientError as e:
            logger.warning("Failed to renew lease for episode %s (worker: %s): %s", episode_id, worker_id, str(e))
            return False

    def _release_investigation(
        self,
        episode_id: str,
        new_status: str,
        worker_id: Optional[str] = None,
        error_message: Optional[str] = None,
        extra_condition: str = "",
        extra_names: Optional[Dict[str, str]] = None,
        extra_values: Optional[Dict[str, Any]] = None,
    ) -> bool:
        now = int(time.time())
        try:
            update_expr = "SET investigation_status = :new_st, lease_owner = :none, lease_until = :zero, updated_at = :now"
            vals: Dict[str, Any] = {
                ":new_st": {"S": new_status},
                ":none": {"S": ""},
                ":zero": {"N": "0"},
                ":now": {"N": str(now)},
            }
            if error_message is not None:
                update_expr += ", last_error = :err"
                vals[":err"] = {"S": str(error_message)[:1024]}

            cond = "attribute_exists(episode_id)"
            if worker_id:
                cond += " AND lease_owner = :owner AND investigation_status = :inv"
                vals[":owner"] = {"S": worker_id}
                vals[":inv"] = {"S": "investigating"}

            if extra_condition:
                cond += extra_condition
            if extra_values:
                vals.update(extra_values)

            kwargs: Dict[str, Any] = {
                "TableName": self.table_name,
                "Key": {"episode_id": {"S": episode_id}},
                "UpdateExpression": update_expr,
                "ConditionExpression": cond,
                "ExpressionAttributeValues": vals,
            }
            if extra_names:
                kwargs["ExpressionAttributeNames"] = extra_names

            self.client.update_item(**kwargs)
            logger.info("Episode %s transitioned to %s", episode_id, new_status)
            return True
        except ClientError as e:
            logger.error("Failed transitioning episode %s to %s: %s", episode_id, new_status, str(e))
            return False

    def complete_episode(self, episode_id: str, worker_id: str) -> bool:
        return self._release_investigation(
            episode_id,
            "completed",
            worker_id=worker_id,
            extra_condition=" AND #st = :firing",
            extra_names={"#st": "status"},
            extra_values={":firing": {"S": "firing"}},
        )

    def fail_episode(self, episode_id: str, worker_id: str, error_message: str) -> bool:
        return self._release_investigation(
            episode_id, "failed", worker_id=worker_id, error_message=error_message
        )

    def mark_dead_lettered(self, episode_id: str, worker_id: str, error_message: str) -> bool:
        return self._release_investigation(
            episode_id, "dead_lettered", worker_id=worker_id, error_message=error_message
        )

    def reconcile_dead_lettered(self, episode_id: str, error_message: str = "Reconciled from SQS DLQ") -> bool:
        now = int(time.time())
        try:
            self.client.update_item(
                TableName=self.table_name,
                Key={"episode_id": {"S": episode_id}},
                UpdateExpression="SET investigation_status = :dlq, last_error = :err, lease_owner = :none, lease_until = :zero, updated_at = :now",
                ConditionExpression=(
                    "attribute_exists(episode_id) AND "
                    "#st <> :resolved AND "
                    "investigation_status <> :completed AND "
                    "investigation_status <> :res_canc AND "
                    "("
                        "investigation_status IN (:failed, :queued) OR "
                        "(investigation_status = :inv AND lease_until <= :now)"
                    ")"
                ),
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={
                    ":dlq": {"S": "dead_lettered"},
                    ":err": {"S": str(error_message)[:1024]},
                    ":none": {"S": ""},
                    ":zero": {"N": "0"},
                    ":now": {"N": str(now)},
                    ":resolved": {"S": "resolved"},
                    ":completed": {"S": "completed"},
                    ":res_canc": {"S": "resolved_cancelled"},
                    ":failed": {"S": "failed"},
                    ":queued": {"S": "queued"},
                    ":inv": {"S": "investigating"},
                },
            )
            logger.warning("Episode %s reconciled to dead_lettered from DLQ in DynamoDB", episode_id)
            return True
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code == "ConditionalCheckFailedException":
                logger.info(
                    "Episode %s not eligible for DLQ reconciliation (active lease, completed, or resolved)",
                    episode_id,
                )
            else:
                logger.error("Failed to reconcile episode %s to dead_lettered: %s", episode_id, str(e))
            return False
        except Exception as e:
            logger.error("Unexpected error reconciling episode %s to dead_lettered: %s", episode_id, str(e))
            return False

    def mark_resolved_cancelled(self, episode_id: str, worker_id: Optional[str] = None) -> bool:
        now = int(time.time())
        try:
            cond = "attribute_exists(episode_id)"
            expr_vals: Dict[str, Any] = {
                ":rc": {"S": "resolved_cancelled"},
                ":none": {"S": ""},
                ":zero": {"N": "0"},
                ":now": {"N": str(now)},
            }
            expr_names: Optional[Dict[str, str]] = None
            if worker_id:
                cond += " AND (lease_owner = :owner OR attribute_not_exists(lease_owner) OR lease_owner = :none OR #st = :res)"
                expr_vals[":owner"] = {"S": worker_id}
                expr_vals[":res"] = {"S": "resolved"}
                expr_names = {"#st": "status"}

            kwargs: Dict[str, Any] = {
                "TableName": self.table_name,
                "Key": {"episode_id": {"S": episode_id}},
                "UpdateExpression": "SET investigation_status = :rc, lease_owner = :none, lease_until = :zero, updated_at = :now",
                "ConditionExpression": cond,
                "ExpressionAttributeValues": expr_vals,
            }
            if expr_names:
                kwargs["ExpressionAttributeNames"] = expr_names

            self.client.update_item(**kwargs)
            logger.info("Episode %s marked resolved_cancelled in DynamoDB", episode_id)
            return True
        except ClientError as e:
            logger.error("Failed to mark episode %s resolved_cancelled: %s", episode_id, str(e))
            return False

    def record_model_disabled(self, episode_id: str, worker_id: Optional[str] = None) -> bool:
        return self._release_investigation(episode_id, "model_disabled", worker_id=worker_id)


__all__ = [
    "EpisodeRecord",
    "BaseEpisodeStore",
    "InMemoryEpisodeStore",
    "DynamoDBEpisodeStore",
]
