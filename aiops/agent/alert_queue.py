"""
Autonomous AIOps Platform — Durable Alert Queue Interface & Implementations

Provides:
- InMemoryAlertQueue: thread-safe, bounded memory queue for offline unit tests and local dev.
- SQSAlertQueue: production AWS SQS FIFO queue with deterministic deduplication,
  14-day retention, long polling, and dead-letter queue (DLQ) support.
"""

import time
import json
import queue
import hashlib
import logging
import threading
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = Exception

from .schemas import AlertItem

logger = logging.getLogger("aiops.alert_queue")


@dataclass
class QueueMessage:
    """Represents a dequeued alert investigation message."""

    message_id: str
    receipt_handle: str
    body: Dict[str, Any]
    receive_count: int
    episode_id: str
    alert: AlertItem
    cluster_identity: str
    truncated_alerts: int
    enqueued_at: float = field(default_factory=time.time)


class BaseAlertQueue(ABC):
    """Abstract interface for alert message queueing."""

    @abstractmethod
    def send_alert(
        self,
        episode_id: str,
        alert: AlertItem,
        cluster_identity: str = "boutique-dev-eks",
        truncated_alerts: int = 0,
    ) -> str:
        """Publishes an alert event to the queue. Returns message ID or raises exception."""
        pass

    @abstractmethod
    def receive_alert(
        self,
        wait_time_seconds: int = 20,
        visibility_timeout: int = 300,
    ) -> Optional[QueueMessage]:
        """Receives a single alert message from the queue."""
        pass

    @abstractmethod
    def receive_dlq_alert(
        self,
        wait_time_seconds: int = 10,
        visibility_timeout: int = 300,
    ) -> Optional[QueueMessage]:
        """Receives a single alert message from the dead-letter queue without deleting it."""
        pass

    @abstractmethod
    def delete_alert(self, receipt_handle: str) -> bool:
        """Deletes a message from the queue after successful processing."""
        pass

    @abstractmethod
    def change_visibility(self, receipt_handle: str, visibility_timeout: int) -> bool:
        """Extends or resets the message visibility timeout."""
        pass

    @abstractmethod
    def approximate_size(self) -> int:
        """Returns the approximate number of messages available in the queue."""
        pass


class InMemoryAlertQueue(BaseAlertQueue):
    """Thread-safe in-memory queue for offline unit tests and local development."""

    def __init__(self, maxsize: int = 10):
        self._queue: queue.Queue = queue.Queue(maxsize=maxsize)
        self._dlq_messages: List[QueueMessage] = []
        self._dlq_visibility: Dict[str, float] = {}  # message_id -> visible_after timestamp
        self._dlq_lock = threading.Lock()
        self._dlq_condition = threading.Condition(self._dlq_lock)
        self._counter: int = 0

    @property
    def maxsize(self) -> int:
        return self._queue.maxsize

    def empty(self) -> bool:
        return self._queue.empty()

    def full(self) -> bool:
        return self._queue.full()

    def get_nowait(self) -> QueueMessage:
        return self._queue.get_nowait()

    def task_done(self) -> None:
        self._queue.task_done()

    def qsize(self) -> int:
        return self._queue.qsize()

    def put_nowait(self, item) -> None:
        self._queue.put_nowait(item)

    def _create_message(
        self, prefix: str, episode_id: str, alert: AlertItem, cluster_identity: str, truncated_alerts: int, receive_count: int = 1
    ) -> QueueMessage:
        self._counter += 1
        tag = f"{prefix}-" if prefix else ""
        now = time.time()
        body = {
            "episode_id": episode_id,
            "alert": alert.model_dump(mode="json"),
            "cluster_identity": cluster_identity,
            "truncated_alerts": truncated_alerts,
            "enqueued_at": now,
        }
        return QueueMessage(
            message_id=f"mem-{tag}msg-{self._counter}",
            receipt_handle=f"mem-{tag}receipt-{self._counter}",
            body=body,
            receive_count=receive_count,
            episode_id=episode_id,
            alert=alert,
            cluster_identity=cluster_identity,
            truncated_alerts=truncated_alerts,
            enqueued_at=now,
        )

    def send_alert(
        self,
        episode_id: str,
        alert: AlertItem,
        cluster_identity: str = "boutique-dev-eks",
        truncated_alerts: int = 0,
    ) -> str:
        msg = self._create_message("", episode_id, alert, cluster_identity, truncated_alerts, 1)
        body_bytes = json.dumps(msg.body).encode("utf-8")
        if len(body_bytes) > 1048576:
            raise ValueError(
                f"Serialized message envelope size ({len(body_bytes)} bytes) exceeds the maximum 1 MiB limit (1048576 bytes)"
            )
        self._queue.put_nowait(msg)
        return msg.message_id

    def receive_alert(
        self,
        wait_time_seconds: int = 1,
        visibility_timeout: int = 300,
    ) -> Optional[QueueMessage]:
        try:
            return self._queue.get(timeout=min(wait_time_seconds, 0.5))
        except queue.Empty:
            return None

    def receive_dlq_alert(
        self,
        wait_time_seconds: int = 1,
        visibility_timeout: int = 300,
    ) -> Optional[QueueMessage]:
        """
        Receives a single message from the in-memory DLQ non-destructively.
        The message remains preserved in the DLQ.
        Applies visibility_timeout: the message is hidden from reception until
        its visibility window expires (time.time() >= visible_after).
        """
        wait_timeout = min(wait_time_seconds, 0.1) if wait_time_seconds > 0 else 0.0
        deadline = time.time() + wait_timeout

        with self._dlq_lock:
            while True:
                now = time.time()
                for msg in self._dlq_messages:
                    if now >= self._dlq_visibility.get(msg.message_id, 0.0):
                        self._dlq_visibility[msg.message_id] = now + visibility_timeout
                        return msg

                remaining = deadline - time.time()
                if remaining <= 0:
                    return None
                self._dlq_condition.wait(timeout=min(remaining, 0.02))

    def _enqueue_dlq(self, item: QueueMessage) -> None:
        with self._dlq_lock:
            self._dlq_messages.append(item)
            self._dlq_visibility[item.message_id] = 0.0
            self._dlq_condition.notify_all()

    def send_to_dlq(
        self,
        episode_id: str,
        alert: AlertItem,
        cluster_identity: str = "boutique-dev-eks",
        truncated_alerts: int = 0,
        receive_count: int = 3,
    ) -> str:
        msg = self._create_message("dlq", episode_id, alert, cluster_identity, truncated_alerts, receive_count)
        self._enqueue_dlq(msg)
        return msg.message_id

    def put_dlq_nowait(self, item: QueueMessage) -> None:
        self._enqueue_dlq(item)

    def approximate_dlq_size(self) -> int:
        with self._dlq_lock:
            return len(self._dlq_messages)

    def delete_alert(self, receipt_handle: str) -> bool:
        try:
            self._queue.task_done()
        except ValueError:
            pass
        return True

    def change_visibility(self, receipt_handle: str, visibility_timeout: int) -> bool:
        return True

    def approximate_size(self) -> int:
        return self._queue.qsize()

    def clear(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except Exception:
                break
        with self._dlq_lock:
            self._dlq_messages.clear()
            self._dlq_visibility.clear()
            self._dlq_condition.notify_all()



class SQSAlertQueue(BaseAlertQueue):
    """
    Production Amazon SQS FIFO queue with dead-letter queue (DLQ) support,
    14-day retention, long polling, and deterministic MessageGroupId / MessageDeduplicationId.
    """

    def __init__(
        self,
        queue_url: Optional[str] = None,
        dlq_url: Optional[str] = None,
        queue_name: Optional[str] = None,
        dlq_name: Optional[str] = None,
        sqs_client=None,
        region_name: str = "us-east-2",
        visibility_timeout_seconds: int = 300,
    ):
        q_url = queue_url.strip() if queue_url and queue_url.strip() else None
        d_url = dlq_url.strip() if dlq_url and dlq_url.strip() else None
        q_name = queue_name.strip() if queue_name and queue_name.strip() else None
        d_name = dlq_name.strip() if dlq_name and dlq_name.strip() else None

        has_names = bool(q_name or d_name)

        if has_names and (queue_url or dlq_url):
            raise ValueError(
                "Ambiguous SQSAlertQueue configuration: both queue URLs and queue names were provided. "
                "Specify either queue names or queue URLs, not both."
            )

        if has_names:
            if not q_name:
                raise ValueError("SQSAlertQueue requires a valid, non-empty queue_name")
            if not d_name:
                raise ValueError("SQSAlertQueue requires a valid, non-empty dlq_name")
        else:
            if not q_url:
                raise ValueError("SQSAlertQueue requires a valid, non-empty queue_url")
            if not d_url:
                raise ValueError("SQSAlertQueue requires a valid, non-empty dlq_url")

        self.region_name = region_name
        self.visibility_timeout_seconds = visibility_timeout_seconds

        if sqs_client is not None:
            self.client = sqs_client
        else:
            if boto3 is None:
                raise RuntimeError("boto3 is required for SQSAlertQueue")
            self.client = boto3.client("sqs", region_name=region_name)

        if has_names:
            self.queue_name = q_name
            self.dlq_name = d_name
            self.queue_url = self.client.get_queue_url(QueueName=q_name)["QueueUrl"]
            self.dlq_url = self.client.get_queue_url(QueueName=d_name)["QueueUrl"]
        else:
            self.queue_name = None
            self.dlq_name = None
            self.queue_url = q_url
            self.dlq_url = d_url

    def send_alert(
        self,
        episode_id: str,
        alert: AlertItem,
        cluster_identity: str = "boutique-dev-eks",
        truncated_alerts: int = 0,
    ) -> str:
        """
        Sends an alert to SQS FIFO using episode_id as MessageGroupId and a stable
        SHA256 deduplication ID based on episode identity, startsAt, and status.
        """
        raw_dedup = f"{episode_id}:{alert.startsAt.isoformat()}:{alert.status.value}"
        dedup_id = hashlib.sha256(raw_dedup.encode("utf-8")).hexdigest()

        body_dict = {
            "episode_id": episode_id,
            "alert": alert.model_dump(mode="json"),
            "cluster_identity": cluster_identity,
            "truncated_alerts": truncated_alerts,
            "enqueued_at": time.time(),
        }
        body_json = json.dumps(body_dict)
        body_bytes = body_json.encode("utf-8")
        max_bytes = 1048576  # 1 MiB hard envelope limit
        if len(body_bytes) > max_bytes:
            raise ValueError(
                f"Serialized SQS message envelope size ({len(body_bytes)} bytes) exceeds the maximum 1 MiB limit ({max_bytes} bytes)"
            )

        try:
            resp = self.client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=body_json,
                MessageGroupId=episode_id,
                MessageDeduplicationId=dedup_id,
            )
            msg_id = resp.get("MessageId", "unknown")
            logger.info("Successfully enqueued alert for episode %s to SQS FIFO (MessageId: %s)", episode_id, msg_id)
            return msg_id
        except Exception as e:
            logger.error("Failed to send alert for episode %s to SQS FIFO: %s", episode_id, str(e))
            raise

    def _receive_message(
        self,
        queue_url: str,
        wait_time_seconds: int,
        visibility_timeout: int,
        default_receive_count: int,
    ) -> Optional[QueueMessage]:
        try:
            resp = self.client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=wait_time_seconds,
                VisibilityTimeout=visibility_timeout,
                AttributeNames=["ApproximateReceiveCount"],
            )
            messages = resp.get("Messages", [])
            if not messages:
                return None

            msg = messages[0]
            attrs = msg.get("Attributes", {})
            receive_count = int(attrs.get("ApproximateReceiveCount", default_receive_count))
            body_dict = json.loads(msg["Body"])

            return QueueMessage(
                message_id=msg["MessageId"],
                receipt_handle=msg["ReceiptHandle"],
                body=body_dict,
                receive_count=receive_count,
                episode_id=body_dict["episode_id"],
                alert=AlertItem.model_validate(body_dict["alert"]),
                cluster_identity=body_dict.get("cluster_identity", "boutique-dev-eks"),
                truncated_alerts=int(body_dict.get("truncated_alerts", 0)),
                enqueued_at=float(body_dict.get("enqueued_at", time.time())),
            )
        except Exception as e:
            logger.error("Error receiving message from SQS queue %s: %s", queue_url, str(e))
            return None

    def receive_alert(
        self,
        wait_time_seconds: int = 20,
        visibility_timeout: int = 300,
    ) -> Optional[QueueMessage]:
        """Long polls SQS FIFO for the next message."""
        return self._receive_message(
            queue_url=self.queue_url,
            wait_time_seconds=wait_time_seconds,
            visibility_timeout=visibility_timeout,
            default_receive_count=1,
        )

    def receive_dlq_alert(
        self,
        wait_time_seconds: int = 10,
        visibility_timeout: int = 300,
    ) -> Optional[QueueMessage]:
        """
        Polls the SQS DLQ for a single message without deleting it.
        Applies visibility_timeout (default: 300s) to prevent continuous re-polling
        while preserving the message intact for manual operator inspection and recovery.
        """
        return self._receive_message(
            queue_url=self.dlq_url,
            wait_time_seconds=wait_time_seconds,
            visibility_timeout=visibility_timeout,
            default_receive_count=3,
        )

    def delete_alert(self, receipt_handle: str) -> bool:
        """Deletes a successfully processed message from SQS."""
        try:
            self.client.delete_message(
                QueueUrl=self.queue_url,
                ReceiptHandle=receipt_handle,
            )
            logger.debug("Successfully deleted message from SQS FIFO")
            return True
        except Exception as e:
            logger.error("Failed to delete message from SQS FIFO: %s", str(e))
            return False

    def change_visibility(self, receipt_handle: str, visibility_timeout: int) -> bool:
        """Extends or resets the message visibility timeout."""
        try:
            self.client.change_message_visibility(
                QueueUrl=self.queue_url,
                ReceiptHandle=receipt_handle,
                VisibilityTimeout=visibility_timeout,
            )
            return True
        except Exception as e:
            logger.warning("Failed to change visibility timeout for SQS message: %s", str(e))
            return False

    def approximate_size(self) -> int:
        try:
            resp = self.client.get_queue_attributes(
                QueueUrl=self.queue_url,
                AttributeNames=["ApproximateNumberOfMessages"],
            )
            attrs = resp.get("Attributes", {})
            return int(attrs.get("ApproximateNumberOfMessages", 0))
        except Exception:
            return 0


__all__ = [
    "QueueMessage",
    "BaseAlertQueue",
    "InMemoryAlertQueue",
    "SQSAlertQueue",
]
