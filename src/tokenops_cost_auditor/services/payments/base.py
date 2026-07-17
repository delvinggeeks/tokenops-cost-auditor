"""PaymentPort (docs/02-HLD.md C7, FR-18): provider-agnostic payment links +
credit accounting. One completed payment = one audit credit (accepted default
Q8); admin mark-paid and comp grants flow through the same table."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.persistence.models import Payment


class PaymentLinkPort(Protocol):
    provider: str

    def payment_link(self) -> str | None:
        """Static env-configured payment link (ADR-6), or None when not configured."""
        ...


def unconsumed_credit(session: Session, user_id: str) -> Payment | None:
    """Oldest paid, not-yet-consumed credit for this user (FR-18)."""
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
