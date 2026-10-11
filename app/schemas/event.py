import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EventFilter(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)


class OutboxEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    event_type: str
    payload: dict
    created_at: datetime
    published_at: datetime | None
