import uuid

from flask import request

from ..exceptions import NotFoundError, ValidationError
from ..models.claim import ClaimStatus
from ..schemas.claim import ClaimActionIn, ClaimCreate, ClaimFilter
from ..services.claim_service import ClaimService
from .base import BaseView

ACTIONS = {
    "approve": ClaimStatus.APPROVED,
    "reject": ClaimStatus.REJECTED,
    "pay": ClaimStatus.PAID,
}


class ClaimListView(BaseView):
    def __init__(self) -> None:
        self.service = ClaimService()

    def get(self):
        claims = self.service.list(self.parse_query(ClaimFilter))
        return {"data": [c.model_dump(mode="json") for c in claims]}, 200

    def post(self):
        key = request.headers.get("Idempotency-Key", "").strip()
        if not key or len(key) > 64:
            raise ValidationError("Idempotency-Key header is required (max 64 characters)")
        claim, created = self.service.submit(self.parse_body(ClaimCreate), key)
        return {"data": claim.model_dump(mode="json")}, (201 if created else 200)


class ClaimDetailView(BaseView):
    def __init__(self) -> None:
        self.service = ClaimService()

    def get(self, claim_id: uuid.UUID):
        return {"data": self.service.get(claim_id).model_dump(mode="json")}, 200


class ClaimActionView(BaseView):
    def __init__(self) -> None:
        self.service = ClaimService()

    def post(self, claim_id: uuid.UUID, action: str):
        target = ACTIONS.get(action)
        if target is None:
            raise NotFoundError(f"Unknown action: {action}")
        body = self.parse_body(ClaimActionIn)  # validates optional reason
        return {"data": self.service.transition(claim_id, target, body.reason).model_dump(mode="json")}, 200


class ClaimStatsView(BaseView):
    def __init__(self) -> None:
        self.service = ClaimService()

    def get(self):
        return {"data": self.service.stats().model_dump(mode="json")}, 200
