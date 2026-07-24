"""PaymentPort (docs/02-HLD.md C7, FR-18): provider-agnostic payment links +
credit accounting. One completed payment = one audit credit (accepted default
Q8); admin mark-paid and comp grants flow through the same table."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from tokenops_cost_auditor.persistence.models import Payment


class PaymentLinkPort(Protocol):
    provider: str

    def payment_link(self) -> str | None:
        """Static env-configured payment link (ADR-6), or None when not configured."""
        ...


def unconsumed_credit(session: Session, user_id: str) -> Payment | None:
    """Oldest paid, not-yet-consumed credit for this user (FR-18).

    O-1: Payment has NO workspace_id column (O-0 stamped 10 tables; Payment
    was left per-user by design) — pay-per-audit credits stay a per-user
    ledger. Deferred to O-1b/O-2 with the billing-model decision. Leak-safe."""
    return session.scalar(
        select(Payment)
        .where(
            Payment.user_id == user_id,
            Payment.status == "paid",
            Payment.audit_id.is_(None),
        )
        .order_by(Payment.ts)
        .limit(1)
    )


def claim_credit(session: Session, user_id: str, audit_id: str) -> Payment | None:
    """Atomically claim one credit for an audit (G5 cold-reviewer f.1).

    The UPDATE only succeeds while audit_id IS NULL, so two concurrent uploads
    racing for the same payment row cannot both consume it — the loser's
    rowcount is 0 and it moves to the next candidate (or gets None -> 402).
    Portable across sqlite/postgres (no row locks needed).
    """
    while True:
        candidate_id = session.scalar(
            select(Payment.id)
            .where(
                Payment.user_id == user_id,
                Payment.status == "paid",
                Payment.audit_id.is_(None),
            )
            .order_by(Payment.ts)
            .limit(1)
        )
        if candidate_id is None:
            return None
        result = session.execute(
            update(Payment)
            .where(Payment.id == candidate_id, Payment.audit_id.is_(None))
            .values(audit_id=audit_id)
        )
        claimed = getattr(result, "rowcount", 0)  # CursorResult in practice
        if claimed == 1:
            return session.get(Payment, candidate_id)
        # lost the race for this row; try the next unclaimed credit


def grant_payment(
    session: Session,
    user_id: str,
    provider: str,
    amount: float,
    currency: str,
    ref: str | None = None,
) -> Payment:
    payment = Payment(user_id=user_id, provider=provider, amount=amount, currency=currency, ref=ref)
    session.add(payment)
    session.flush()
    return payment
