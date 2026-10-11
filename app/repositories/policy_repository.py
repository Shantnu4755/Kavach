import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.policy import Policy


class PolicyRepository:
    def add(self, s: Session, policy: Policy) -> None:
        s.add(policy)

    def get(self, s: Session, policy_id: uuid.UUID) -> Policy | None:
        return s.get(Policy, policy_id)

    def get_by_number(self, s: Session, policy_number: str) -> Policy | None:
        stmt = select(Policy).where(Policy.policy_number == policy_number)
        return s.execute(stmt).scalar_one_or_none()

    def list(self, s: Session, limit: int, offset: int) -> list[Policy]:
        stmt = select(Policy).order_by(Policy.created_at.desc()).limit(limit).offset(offset)
        return list(s.execute(stmt).scalars())
