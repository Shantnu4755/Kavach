import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..models.claim import ClaimStatus


class ClaimCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_id: uuid.UUID
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    description: str = Field(min_length=5, max_length=500)


class ClaimActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=300)


class ClaimFilter(BaseModel):
    status: ClaimStatus | None = None
    q: str | None = Field(default=None, min_length=1, max_length=100)  # search in description
    sort: Literal["created_at", "amount"] = "created_at"
    order: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    policy_id: uuid.UUID
    amount: Decimal
    status: ClaimStatus
    description: str
    created_at: datetime
    updated_at: datetime
    decided_at: datetime | None


class ClaimStats(BaseModel):
    total_claims: int
    by_status: dict[ClaimStatus, int]
    amount_under_review: Decimal
    approval_rate: float | None  # approved or paid / all decided claims
    avg_decision_seconds: float | None
