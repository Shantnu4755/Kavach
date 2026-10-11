import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import Base


class ClaimStatus(str, enum.Enum):
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PAID = "PAID"


ALLOWED_TRANSITIONS: dict[ClaimStatus, set[ClaimStatus]] = {
    ClaimStatus.SUBMITTED: {ClaimStatus.APPROVED, ClaimStatus.REJECTED},
    ClaimStatus.APPROVED: {ClaimStatus.PAID},
    ClaimStatus.REJECTED: set(),
    ClaimStatus.PAID: set(),
}


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policies.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[ClaimStatus] = mapped_column(
        Enum(ClaimStatus, name="claim_status"), default=ClaimStatus.SUBMITTED, index=True
    )
    description: Mapped[str] = mapped_column(String(500))
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # set once, when the claim leaves SUBMITTED; powers "average time to decision"
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
