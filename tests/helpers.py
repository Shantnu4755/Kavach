import uuid
from decimal import Decimal

from app.schemas.claim import ClaimCreate
from app.schemas.policy import PolicyCreate
from app.services.claim_service import ClaimService
from app.services.policy_service import PolicyService


def make_policy(sum_insured: str = "500000.00", active: bool = True, number: str | None = None):
    return PolicyService().create(
        PolicyCreate(
            policy_number=number or f"BOM-{uuid.uuid4().hex[:8]}",
            holder_name="Test User",
            sum_insured=Decimal(sum_insured),
            is_active=active,
        )
    )


def make_claim(policy_id: uuid.UUID, amount: str = "25000.00", key: str | None = None):
    data = ClaimCreate(policy_id=policy_id, amount=Decimal(amount), description="Hospital stay")
    claim, _ = ClaimService().submit(data, key or uuid.uuid4().hex)
    return claim
