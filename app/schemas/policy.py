import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_number: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9-]+$")
    holder_name: str = Field(min_length=2, max_length=120)
    sum_insured: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    is_active: bool = True

    @field_validator("policy_number")
    @classmethod
    def normalise_number(cls, value: str) -> str:
        return value.upper()

    @field_validator("holder_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()


class PolicyFilter(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class PolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    policy_number: str
    holder_name: str
    sum_insured: Decimal
    is_active: bool
    created_at: datetime
