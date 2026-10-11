import logging
import uuid

from sqlalchemy.exc import IntegrityError

from ..exceptions import ConflictError, NotFoundError
from ..extensions import db
from ..models.policy import Policy
from ..repositories.policy_repository import PolicyRepository
from ..schemas.policy import PolicyCreate, PolicyFilter, PolicyOut

logger = logging.getLogger(__name__)


class PolicyService:
    def __init__(self) -> None:
        self.policies = PolicyRepository()

    def create(self, data: PolicyCreate) -> PolicyOut:
        with db.session() as s:
            if self.policies.get_by_number(s, data.policy_number):
                raise ConflictError("Policy number already exists", {"policy_number": data.policy_number})
            policy = Policy(**data.model_dump())
            self.policies.add(s, policy)
            try:
                s.flush()  # surfaces a duplicate number from a parallel request
            except IntegrityError as exc:
                raise ConflictError(
                    "Policy number already exists", {"policy_number": data.policy_number}
                ) from exc
            logger.info("policy_created", extra={"code": policy.policy_number})
            return PolicyOut.model_validate(policy)

    def get(self, policy_id: uuid.UUID) -> PolicyOut:
        with db.session() as s:
            policy = self.policies.get(s, policy_id)
            if policy is None:
                raise NotFoundError("Policy not found", {"policy_id": str(policy_id)})
            return PolicyOut.model_validate(policy)

    def list(self, f: PolicyFilter) -> list[PolicyOut]:
        with db.session() as s:
            return [PolicyOut.model_validate(p) for p in self.policies.list(s, f.limit, f.offset)]
