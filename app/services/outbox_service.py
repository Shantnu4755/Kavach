import logging
import threading
import uuid

import requests
from sqlalchemy import func

from ..exceptions import ExternalServiceError
from ..extensions import db
from ..liveness import mark_alive
from ..repositories.claim_repository import OutboxRepository
from ..schemas.event import EventFilter, OutboxEventOut

logger = logging.getLogger(__name__)


class OutboxService:
    """Read side of the outbox, for the UI's events feed."""

    def __init__(self) -> None:
        self.outbox = OutboxRepository()

    def recent(self, f: EventFilter) -> list[OutboxEventOut]:
        with db.session() as s:
            return [OutboxEventOut.model_validate(e) for e in self.outbox.recent(s, f.limit)]


class KaryaClient:
    """Enqueues outbox events as Karya jobs. Karya de-duplicates on idempotency_key,
    so sending the same event twice (relay crashed before marking it) is safe."""

    QUEUE = "default"
    TASK = "kavach.claim_event"

    def __init__(self, base_url: str, timeout: tuple[float, float] = (2.0, 5.0)) -> None:
        self.url = f"{base_url.rstrip('/')}/jobs"
        self.timeout = timeout
        self.http = requests.Session()

    def enqueue(self, event_id: uuid.UUID, event_type: str, payload: dict) -> None:
        body = {
            "queue": self.QUEUE,
            "task": self.TASK,
            "payload": {"event_id": str(event_id), "event_type": event_type, **payload},
            "idempotency_key": f"kavach:{event_id}",
        }
        try:
            resp = self.http.post(self.url, json=body, timeout=self.timeout)
        except requests.RequestException as exc:
            raise ExternalServiceError("Karya is unreachable") from exc
        if resp.status_code >= 300:
            raise ExternalServiceError("Karya rejected the event", {"status": resp.status_code})


class OutboxRelay:
    """Transactional outbox relay: delivers events at least once, in order, and never loses one."""

    BATCH_SIZE = 50

    def __init__(self, client: KaryaClient, interval: float = 2.0) -> None:
        self.client = client
        self.interval = interval
        self.outbox = OutboxRepository()

    def publish_batch(self) -> int:
        """Send the oldest unpublished events. Returns how many were published."""
        published = 0
        with db.session() as s:
            for event in self.outbox.lock_unpublished(s, self.BATCH_SIZE):
                try:
                    self.client.enqueue(event.id, event.event_type, event.payload)
                except ExternalServiceError as exc:
                    logger.warning(
                        "relay_publish_failed", extra={"code": str(event.id), "error_message": exc.message}
                    )
                    break  # Karya is down: the rest wait safely in the table for the next round
                event.published_at = func.now()
                published += 1
        if published:
            logger.info("relay_published", extra={"code": published})
        return published

    def run(self, stop: threading.Event) -> None:
        logger.info("relay_started")
        while not stop.is_set():
            mark_alive()
            try:
                published = self.publish_batch()
            except Exception:
                logger.exception("relay_tick_failed")  # database hiccup: wait, then try again
                published = 0
            if published < self.BATCH_SIZE:  # a full batch means more are waiting: go again now
                stop.wait(self.interval)
        logger.info("relay_stopped")
