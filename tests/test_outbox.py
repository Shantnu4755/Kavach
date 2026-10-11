import threading
import uuid
from unittest.mock import MagicMock, patch

import pytest
import requests
from sqlalchemy import select

from app.config import ConfigError
from app.exceptions import ExternalServiceError
from app.extensions import db
from app.models.claim import OutboxEvent
from app.services.outbox_service import KaryaClient, OutboxRelay
from tests.helpers import make_claim, make_policy


def _events() -> list[OutboxEvent]:
    with db.session() as s:
        return list(s.execute(select(OutboxEvent).order_by(OutboxEvent.created_at)).scalars())


def test_every_change_writes_an_outbox_event(client):
    claim = make_claim(make_policy().id)
    client.post(f"/claims/{claim.id}/approve", json={"reason": "docs verified"})
    events = _events()
    assert [e.event_type for e in events] == ["claim.submitted", "claim.approved"]
    assert events[1].payload == {"claim_id": str(claim.id), "reason": "docs verified"}
    assert all(e.published_at is None for e in events)


def test_events_feed_newest_first(client):
    claim = make_claim(make_policy().id)
    client.post(f"/claims/{claim.id}/reject", json={})
    feed = client.get("/events?limit=1").get_json()["data"]
    assert [e["event_type"] for e in feed] == ["claim.rejected"]


def test_relay_publishes_and_marks_events(app):
    make_claim(make_policy().id)
    make_claim(make_policy().id)
    client = MagicMock(spec=KaryaClient)
    assert OutboxRelay(client).publish_batch() == 2
    assert client.enqueue.call_count == 2
    assert all(e.published_at is not None for e in _events())
    assert OutboxRelay(client).publish_batch() == 0  # nothing left


def test_relay_keeps_events_when_karya_is_down(app):
    make_claim(make_policy().id)
    make_claim(make_policy().id)
    client = MagicMock(spec=KaryaClient)
    client.enqueue.side_effect = [None, ExternalServiceError("Karya is unreachable")]
    assert OutboxRelay(client).publish_batch() == 1
    published = [e.published_at is not None for e in _events()]
    assert published == [True, False]  # the second waits for the next round


def test_two_relays_never_send_the_same_event(app):
    for _ in range(6):
        make_claim(make_policy().id)
    sent: list[uuid.UUID] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def enqueue(event_id, event_type, payload):
        with lock:
            sent.append(event_id)

    def relay() -> None:
        client = MagicMock(spec=KaryaClient)
        client.enqueue.side_effect = enqueue
        barrier.wait()
        OutboxRelay(client).publish_batch()

    threads = [threading.Thread(target=relay) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(sent) == len(set(sent))  # SKIP LOCKED: no event handed to both relays
    remaining = OutboxRelay(MagicMock(spec=KaryaClient)).publish_batch()
    assert len(sent) + remaining == 6


def test_relay_loop_survives_errors_and_stops(app):
    stop = threading.Event()
    relay = OutboxRelay(MagicMock(spec=KaryaClient), interval=0.01)
    calls = {"n": 0}

    def flaky_batch() -> int:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("database hiccup")
        stop.set()
        return 0

    with patch.object(relay, "publish_batch", side_effect=flaky_batch):
        relay.run(stop)
    assert calls["n"] == 2


def test_karya_client_sends_an_idempotent_job():
    client = KaryaClient("http://karya:8000/")
    event_id = uuid.uuid4()
    with patch.object(client.http, "post", return_value=MagicMock(status_code=201)) as post:
        client.enqueue(event_id, "claim.submitted", {"claim_id": "c1"})
    url = post.call_args.args[0]
    body = post.call_args.kwargs["json"]
    assert url == "http://karya:8000/jobs"
    assert body["task"] == "kavach.claim_event"
    assert body["idempotency_key"] == f"kavach:{event_id}"
    assert body["payload"] == {"event_id": str(event_id), "event_type": "claim.submitted", "claim_id": "c1"}


@pytest.mark.parametrize(
    "outcome",
    [requests.ConnectionError("refused"), MagicMock(status_code=503)],
)
def test_karya_client_errors_become_external_service_errors(outcome):
    client = KaryaClient("http://karya:8000")
    kwargs = {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
    with patch.object(client.http, "post", **kwargs), pytest.raises(ExternalServiceError):
        client.enqueue(uuid.uuid4(), "claim.paid", {})


def test_relay_entry_point_requires_karya_url(monkeypatch):
    from app import relay

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.delenv("KARYA_URL", raising=False)
    with pytest.raises(ConfigError):
        relay.main()


def test_relay_entry_point_runs_the_relay(monkeypatch):
    from app import relay

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("KARYA_URL", "http://karya-api:8000")
    with patch.object(relay, "db") as fake_db, patch.object(relay, "OutboxRelay") as fake_relay, \
            patch.object(relay.signal, "signal"):
        relay.main()
    fake_db.init_app.assert_called_once_with("postgresql+psycopg://u:p@localhost/db")
    fake_relay.return_value.run.assert_called_once()


def test_relay_loop_marks_the_process_alive(app, tmp_path):
    alive = tmp_path / "alive"
    stop = threading.Event()
    relay = OutboxRelay(MagicMock(spec=KaryaClient), interval=0.01)
    with patch("app.liveness.LIVENESS_FILE", alive):
        with patch.object(relay, "publish_batch", side_effect=lambda: stop.set() or 0):
            relay.run(stop)
    assert alive.exists()
