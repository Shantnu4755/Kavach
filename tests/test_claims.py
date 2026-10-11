import threading
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.exceptions import ConflictError
from app.extensions import db
from app.models.claim import Claim, ClaimStatus
from app.schemas.claim import ClaimCreate
from app.services.claim_service import ClaimService
from tests.helpers import make_claim, make_policy


def _submit(client, policy_id, key="claim-001", amount="25000.00"):
    return client.post(
        "/claims",
        json={"policy_id": str(policy_id), "amount": amount, "description": "Hospital stay"},
        headers={"Idempotency-Key": key},
    )


def _claim_count() -> int:
    with db.session() as s:
        return s.execute(select(func.count()).select_from(Claim)).scalar_one()


# --- PDF "Tests to write" ---------------------------------------------------------------


def test_same_idempotency_key_twice_returns_one_claim(client):
    policy = make_policy()
    first = _submit(client, policy.id)
    second = _submit(client, policy.id)
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.get_json()["data"]["id"] == second.get_json()["data"]["id"]
    assert _claim_count() == 1


def test_parallel_submissions_with_one_key_create_one_row(app):
    policy = make_policy()
    data = ClaimCreate(policy_id=policy.id, amount=Decimal("100.00"), description="Parallel claim")
    workers = 8
    barrier = threading.Barrier(workers)
    results: list[tuple[str, bool]] = []
    errors: list[Exception] = []

    def submit() -> None:
        barrier.wait()
        try:
            claim, created = ClaimService().submit(data, "parallel-key")
            results.append((str(claim.id), created))
        except Exception as exc:  # collected and asserted below
            errors.append(exc)

    threads = [threading.Thread(target=submit) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert _claim_count() == 1
    assert len({claim_id for claim_id, _ in results}) == 1
    assert sum(created for _, created in results) == 1


def test_paid_to_approved_is_409(client):
    claim = make_claim(make_policy().id)
    for action in ("approve", "pay"):
        assert client.post(f"/claims/{claim.id}/{action}", json={}).status_code == 200
    resp = client.post(f"/claims/{claim.id}/approve", json={})
    assert resp.status_code == 409
    assert resp.get_json()["error"]["message"] == "Cannot move claim from PAID to APPROVED"


def test_amount_above_sum_insured_is_400(client):
    policy = make_policy(sum_insured="1000.00")
    resp = _submit(client, policy.id, amount="1000.01")
    assert resp.status_code == 400
    error = resp.get_json()["error"]
    assert error["code"] == "business_rule_violation"
    assert error["details"] == {"amount": "1000.01", "sum_insured": "1000.00"}


# --- state machine and locking -----------------------------------------------------------


def test_approve_and_reject_racing_only_one_wins(app):
    claim = make_claim(make_policy().id)
    barrier = threading.Barrier(2)
    outcomes: dict[ClaimStatus, str] = {}

    def move(target: ClaimStatus) -> None:
        barrier.wait()
        try:
            ClaimService().transition(claim.id, target)
            outcomes[target] = "ok"
        except ConflictError:
            outcomes[target] = "conflict"

    threads = [threading.Thread(target=move, args=(t,)) for t in (ClaimStatus.APPROVED, ClaimStatus.REJECTED)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes.values()) == ["conflict", "ok"]


@pytest.mark.parametrize(
    ("path", "expected"),
    [(["approve"], "APPROVED"), (["reject"], "REJECTED"), (["approve", "pay"], "PAID")],
)
def test_legal_transitions(client, path, expected):
    claim = make_claim(make_policy().id)
    for action in path:
        resp = client.post(f"/claims/{claim.id}/{action}", json={"reason": "checked"})
    assert resp.get_json()["data"]["status"] == expected
    assert resp.get_json()["data"]["decided_at"] is not None


@pytest.mark.parametrize("path", [["pay"], ["reject", "approve"], ["approve", "reject"]])
def test_illegal_transitions_are_409(client, path):
    claim = make_claim(make_policy().id)
    for action in path[:-1]:
        client.post(f"/claims/{claim.id}/{action}", json={})
    assert client.post(f"/claims/{claim.id}/{path[-1]}", json={}).status_code == 409


def test_unknown_action_and_unknown_claim_are_404(client):
    claim = make_claim(make_policy().id)
    assert client.post(f"/claims/{claim.id}/cancel", json={}).status_code == 404
    assert client.post(f"/claims/{uuid.uuid4()}/approve", json={}).status_code == 404
    assert client.get(f"/claims/{uuid.uuid4()}").status_code == 404


# --- submit validation ---------------------------------------------------------------------


@pytest.mark.parametrize("key", [None, "", "k" * 65])
def test_idempotency_key_is_required_and_bounded(client, key):
    headers = {"Idempotency-Key": key} if key is not None else {}
    resp = client.post("/claims", json={}, headers=headers)
    assert resp.status_code == 422
    assert "Idempotency-Key" in resp.get_json()["error"]["message"]


def test_claim_on_unknown_or_inactive_policy(client):
    assert _submit(client, uuid.uuid4(), key="k-1").status_code == 404
    inactive = make_policy(active=False)
    resp = _submit(client, inactive.id, key="k-2")
    assert resp.status_code == 400
    assert resp.get_json()["error"]["message"] == "Policy is not active"


def test_claim_rejects_extra_fields_and_bad_amounts(client):
    policy = make_policy()
    resp = client.post(
        "/claims",
        json={"policy_id": str(policy.id), "amount": "1.001", "description": "ok desc", "status": "PAID"},
        headers={"Idempotency-Key": "k-3"},
    )
    assert resp.status_code == 422
    assert {e["loc"][0] for e in resp.get_json()["error"]["details"]["errors"]} == {"amount", "status"}


# --- reading -----------------------------------------------------------------------------


def test_list_filter_search_sort_and_paginate(client):
    policy = make_policy()
    small = make_claim(policy.id, amount="100.00")
    big = make_claim(policy.id, amount="900.00")
    client.post(f"/claims/{big.id}/approve", json={})

    def ids(query: str) -> list[str]:
        return [c["id"] for c in client.get(f"/claims{query}").get_json()["data"]]

    assert ids("?status=APPROVED") == [str(big.id)]
    assert ids("?sort=amount&order=asc") == [str(small.id), str(big.id)]
    assert ids("?sort=amount&order=desc&limit=1") == [str(big.id)]
    assert ids("?sort=amount&order=desc&limit=1&offset=1") == [str(small.id)]
    assert ids("?q=hospital") == ids("")
    assert ids("?q=nothing-like-this") == []
    assert client.get(f"/claims/{small.id}").get_json()["data"]["amount"] == "100.00"
    assert client.get("/claims?status=LOST").status_code == 422


def test_stats(client):
    policy = make_policy()
    claims = [make_claim(policy.id, amount=a) for a in ("100.00", "200.00", "300.00", "400.00")]
    client.post(f"/claims/{claims[0].id}/approve", json={})
    client.post(f"/claims/{claims[1].id}/approve", json={})
    client.post(f"/claims/{claims[1].id}/pay", json={})
    client.post(f"/claims/{claims[2].id}/reject", json={})

    stats = client.get("/claims/stats").get_json()["data"]
    assert stats["total_claims"] == 4
    assert stats["by_status"] == {"SUBMITTED": 1, "APPROVED": 1, "REJECTED": 1, "PAID": 1}
    assert stats["amount_under_review"] == "400.00"
    assert stats["approval_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert stats["avg_decision_seconds"] >= 0


def test_stats_when_empty(client):
    stats = client.get("/claims/stats").get_json()["data"]
    assert stats["total_claims"] == 0
    assert stats["approval_rate"] is None
    assert stats["avg_decision_seconds"] is None


def test_insert_race_on_same_key_returns_the_winner(app):
    """Request A has inserted the key but not committed; request B passed its lookup and inserts too.
    B blocks on the unique index, gets IntegrityError when A commits, and returns A's claim."""
    policy = make_policy()
    a_flushed = threading.Event()
    result: dict[str, object] = {}

    def request_a() -> None:
        with db.session() as s:
            winner = Claim(
                policy_id=policy.id, amount=Decimal("10.00"), description="Winner", idempotency_key="race"
            )
            s.add(winner)
            s.flush()
            result["winner_id"] = winner.id
            a_flushed.set()
            threading.Event().wait(0.5)  # keep the transaction open while B inserts

    def request_b() -> None:
        a_flushed.wait()
        data = ClaimCreate(policy_id=policy.id, amount=Decimal("10.00"), description="Loser")
        result["b"] = ClaimService().submit(data, "race")

    threads = [threading.Thread(target=request_a), threading.Thread(target=request_b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    claim, created = result["b"]
    assert created is False
    assert claim.id == result["winner_id"]
    assert _claim_count() == 1
