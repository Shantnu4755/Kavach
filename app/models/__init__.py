"""Import every model module here so Alembic autogenerate and create_all see all tables."""

from .claim import ALLOWED_TRANSITIONS, Claim, ClaimStatus, OutboxEvent
from .policy import Policy

__all__ = ["ALLOWED_TRANSITIONS", "Claim", "ClaimStatus", "OutboxEvent", "Policy"]
