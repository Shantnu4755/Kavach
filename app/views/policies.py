import uuid

from ..schemas.policy import PolicyCreate, PolicyFilter
from ..services.policy_service import PolicyService
from .base import BaseView


class PolicyListView(BaseView):
    def __init__(self) -> None:
        self.service = PolicyService()

    def get(self):
        policies = self.service.list(self.parse_query(PolicyFilter))
        return {"data": [p.model_dump(mode="json") for p in policies]}, 200

    def post(self):
        policy = self.service.create(self.parse_body(PolicyCreate))
        return {"data": policy.model_dump(mode="json")}, 201


class PolicyDetailView(BaseView):
    def __init__(self) -> None:
        self.service = PolicyService()

    def get(self, policy_id: uuid.UUID):
        return {"data": self.service.get(policy_id).model_dump(mode="json")}, 200
