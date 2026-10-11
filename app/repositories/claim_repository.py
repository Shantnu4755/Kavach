import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.claim import Claim, ClaimStatus, OutboxEvent

_SORT_COLUMNS = {"created_at": Claim.created_at, "amount": Claim.amount}


class ClaimRepository:
    def add(self, s: Session, claim: Claim) -> None:
        s.add(claim)

    def get(self, s: Session, claim_id: uuid.UUID) -> Claim | None:
        return s.get(Claim, claim_id)

    def get_for_update(self, s: Session, claim_id: uuid.UUID) -> Claim | None:
        stmt = select(Claim).where(Claim.id == claim_id).with_for_update()
        return s.execute(stmt).scalar_one_or_none()

    def get_by_idempotency_key(self, s: Session, key: str) -> Claim | None:
        stmt = select(Claim).where(Claim.idempotency_key == key)
        return s.execute(stmt).scalar_one_or_none()

    def list(
        self,
        s: Session,
        status: ClaimStatus | None,
        limit: int,
        offset: int,
        q: str | None = None,
        sort: str = "created_at",
        order: str = "desc",
    ) -> list[Claim]:
        column = _SORT_COLUMNS[sort]
        ordering = column.asc() if order == "asc" else column.desc()
        stmt = select(Claim).order_by(ordering, Claim.id).limit(limit).offset(offset)
        if status:
            stmt = stmt.where(Claim.status == status)
        if q:
            stmt = stmt.where(Claim.description.ilike(f"%{q}%"))
        return list(s.execute(stmt).scalars())

    def counts_by_status(self, s: Session) -> dict[ClaimStatus, int]:
        rows = s.execute(select(Claim.status, func.count()).group_by(Claim.status)).all()
        return {status: count for status, count in rows}

    def amount_in_status(self, s: Session, status: ClaimStatus) -> Decimal:
        stmt = select(func.coalesce(func.sum(Claim.amount), 0)).where(Claim.status == status)
        return Decimal(s.execute(stmt).scalar_one())

    def avg_decision_seconds(self, s: Session) -> float | None:
        seconds = func.extract("epoch", Claim.decided_at - Claim.created_at)
        value = s.execute(select(func.avg(seconds)).where(Claim.decided_at.is_not(None))).scalar_one()
        return float(value) if value is not None else None


class OutboxRepository:
    def add(self, s: Session, event_type: str, payload: dict) -> None:
        s.add(OutboxEvent(event_type=event_type, payload=payload))

    def recent(self, s: Session, limit: int) -> list[OutboxEvent]:
        stmt = select(OutboxEvent).order_by(OutboxEvent.created_at.desc()).limit(limit)
        return list(s.execute(stmt).scalars())

    def lock_unpublished(self, s: Session, limit: int) -> list[OutboxEvent]:
        """Oldest unpublished events, row-locked; rows another relay holds are skipped, not waited on."""
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(s.execute(stmt).scalars())
