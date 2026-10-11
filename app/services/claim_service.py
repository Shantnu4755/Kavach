import logging
import uuid
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from ..exceptions import BusinessRuleError, ConflictError, NotFoundError
from ..extensions import db
from ..models.claim import ALLOWED_TRANSITIONS, Claim, ClaimStatus
from ..repositories.claim_repository import ClaimRepository, OutboxRepository
from ..repositories.policy_repository import PolicyRepository
from ..schemas.claim import ClaimCreate, ClaimFilter, ClaimOut, ClaimStats

logger = logging.getLogger(__name__)


class ClaimService:
    def __init__(self) -> None:
        self.claims = ClaimRepository()
        self.policies = PolicyRepository()
        self.outbox = OutboxRepository()

    def submit(self, data: ClaimCreate, idempotency_key: str) -> tuple[ClaimOut, bool]:
        """Returns (claim, created). A repeated key returns the original claim."""
        with db.session() as s:
            existing = self.claims.get_by_idempotency_key(s, idempotency_key)
            if existing:
                return ClaimOut.model_validate(existing), False

            policy = self.policies.get(s, data.policy_id)
            if policy is None:
                raise NotFoundError("Policy not found", {"policy_id": str(data.policy_id)})
            if not policy.is_active:
                raise BusinessRuleError("Policy is not active")
            if data.amount > policy.sum_insured:
                raise BusinessRuleError(
                    "Claim amount exceeds sum insured",
                    {"amount": str(data.amount), "sum_insured": str(policy.sum_insured)},
                )

            claim = Claim(
                policy_id=data.policy_id,
                amount=data.amount,
                description=data.description,
                idempotency_key=idempotency_key,
            )
            self.claims.add(s, claim)
            try:
                s.flush()  # surfaces a duplicate key from a parallel request
            except IntegrityError:
                s.rollback()
                existing = self.claims.get_by_idempotency_key(s, idempotency_key)
                if existing is None:
                    raise ConflictError("Could not create claim, please retry") from None
                return ClaimOut.model_validate(existing), False

            self.outbox.add(s, "claim.submitted", {"claim_id": str(claim.id), "amount": str(claim.amount)})
            logger.info("claim_submitted", extra={"code": str(claim.id)})
            return ClaimOut.model_validate(claim), True

    def transition(self, claim_id: uuid.UUID, target: ClaimStatus, reason: str | None = None) -> ClaimOut:
        with db.session() as s:
            claim = self.claims.get_for_update(s, claim_id)  # row lock: no race between approve and reject
            if claim is None:
                raise NotFoundError("Claim not found")
            if target not in ALLOWED_TRANSITIONS[claim.status]:
                raise ConflictError(f"Cannot move claim from {claim.status.value} to {target.value}")
            if claim.status == ClaimStatus.SUBMITTED:
                claim.decided_at = func.now()
            claim.status = target
            payload = {"claim_id": str(claim.id)}
            if reason:
                payload["reason"] = reason
            self.outbox.add(s, f"claim.{target.value.lower()}", payload)
            s.flush()
            return ClaimOut.model_validate(claim)

    def get(self, claim_id: uuid.UUID) -> ClaimOut:
        with db.session() as s:
            claim = self.claims.get(s, claim_id)
            if claim is None:
                raise NotFoundError("Claim not found")
            return ClaimOut.model_validate(claim)

    def list(self, f: ClaimFilter) -> list[ClaimOut]:
        with db.session() as s:
            claims = self.claims.list(s, f.status, f.limit, f.offset, q=f.q, sort=f.sort, order=f.order)
            return [ClaimOut.model_validate(c) for c in claims]

    def stats(self) -> ClaimStats:
        with db.session() as s:
            counts = self.claims.counts_by_status(s)
            under_review = self.claims.amount_in_status(s, ClaimStatus.SUBMITTED)
            avg_seconds = self.claims.avg_decision_seconds(s)
        by_status = {status: counts.get(status, 0) for status in ClaimStatus}
        approved = by_status[ClaimStatus.APPROVED] + by_status[ClaimStatus.PAID]
        decided = approved + by_status[ClaimStatus.REJECTED]
        return ClaimStats(
            total_claims=sum(by_status.values()),
            by_status=by_status,
            amount_under_review=Decimal(under_review),
            approval_rate=round(approved / decided, 4) if decided else None,
            avg_decision_seconds=round(avg_seconds, 1) if avg_seconds is not None else None,
        )
