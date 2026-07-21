"""Plan catalogue (PLAN-V15 V-D8 / WP-6) — THE price config.

Every money amount the product renders comes from here (founder, 2026-07-22:
"never inline"). Prices themselves live in Settings so a change is a config
change, not a code change; this module gives them names, entitlements and
display strings.

R-PRICING-FINAL-2 (founder-ratified 2026-07-22): dual-market structure.
Global = USD via Stripe; India = INR via Razorpay. Each market has a LAUNCH
price for its first `launch_cohort_size` subscribers — grandfathered for
life because a provider-side subscription keeps charging what it started
at — and the display flips to the LIST price in code the moment the cohort
fills. Each viewer sees ONE currency (billing country decides at checkout;
a plain toggle shows the other market's pricing). This supersedes R-Q11's
display-both-currencies law.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import Subscription

FREE = "free"
PRO = "pro"
TEAM = "team"
PAID_PLANS = (PRO, TEAM)
ALL_PLANS = (FREE, PRO, TEAM)

# R-Q11: currency follows the customer's billing country, chosen at checkout.
INDIA = "IN"
CURRENCIES = ("USD", "INR")


@dataclass(frozen=True)
class Plan:
    key: str
    name: str
    usd: float | None  # LIST price; None = not sold as a subscription
    inr: float | None
    launch_usd: float | None  # launch-cohort price; None = no launch tier
    launch_inr: float | None
    spend_gate_usd: float | None  # stated audited-spend bound (copy, not metering)
    sources: int  # active provider connections allowed
    scheduled_audits: bool
    uploads: str
    blurb: str

    def price(self, currency: str, *, launch: bool = False) -> float | None:
        if launch and self.has_launch(currency):
            return self.launch_inr if currency.upper() == "INR" else self.launch_usd
        return self.inr if currency.upper() == "INR" else self.usd

    def has_launch(self, currency: str) -> bool:
        launch = self.launch_inr if currency.upper() == "INR" else self.launch_usd
        return bool(launch)

    def display(self, currency: str = "USD", *, launch: bool = False) -> str:
        amount = self.price(currency, launch=launch)
        if amount is None:
            return "—"
        return f"{_symbol(currency)}{amount:,.0f}/mo"

    def launch_note(self, currency: str, cohort_size: int) -> str:
        """The plain, checkable launch-cohort sentence (honesty rail: this is
        forward-looking regional launch pricing, never a fake 'was' price)."""
        return (
            f"Launch price for the first {cohort_size} subscribers — "
            f"{self.display(currency)} after."
        )

    def gate_line(self, currency: str) -> str:
        """Audited-spend bound. Audited spend is measured in USD everywhere
        (NFR-11: USD internal), so the gate is stated in USD in both views."""
        if self.spend_gate_usd is None:
            return ""
        return f"Covers up to ${self.spend_gate_usd / 1000:,.0f}K/mo of audited AI spend."


def _symbol(currency: str) -> str:
    return "₹" if currency.upper() == "INR" else "$"


def catalogue(settings: Settings) -> dict[str, Plan]:
    limits = settings.plan_source_limits
    return {
        FREE: Plan(
            key=FREE,
            name="Free",
            usd=None,
            inr=None,
            launch_usd=None,
            launch_inr=None,
            spend_gate_usd=None,
            sources=limits.get(FREE, 1),
            scheduled_audits=False,
            uploads="one audit of an uploaded log file",
            # R-FREE-CONNECT: the free audit runs on a connection OR a file.
            # R-STMT-GATING: the email behaviour stays said out loud.
            blurb="Connect a provider free — your first audit on us. Or drop "
            "in a usage file; we show you exactly where to get it. No card. "
            "Statements archived in-app; emailed when there's something to show.",
        ),
        PRO: Plan(
            key=PRO,
            name="Pro",
            usd=settings.plan_pro_usd,
            inr=settings.plan_pro_inr,
            launch_usd=settings.plan_pro_usd_launch or None,
            launch_inr=settings.plan_pro_inr_launch or None,
            spend_gate_usd=settings.plan_pro_spend_gate_usd,
            sources=limits.get(PRO, 1),
            scheduled_audits=True,
            uploads="unlimited manual uploads",
            blurb="One connected source, audited weekly, plus a daily spend "
            "digest, alerts and your Savings Statement emailed every month.",
        ),
        TEAM: Plan(
            # R-SAAS-BASICS 1: SOLD as "Scale" — the old name promised seats
            # the product can't cash (multi-user stays at the X-03 trigger).
            # The internal key stays "team": subscription rows and config keys
            # are data, and migrations are additive-only.
            key=TEAM,
            name="Scale",
            usd=settings.plan_team_usd,
            inr=settings.plan_team_inr,
            launch_usd=settings.plan_team_usd_launch or None,
            launch_inr=settings.plan_team_inr_launch or None,
            spend_gate_usd=settings.plan_team_spend_gate_usd,
            sources=limits.get(TEAM, 5),
            scheduled_audits=True,
            uploads="unlimited manual uploads",
            blurb="Five connected sources with priority support.",
        ),
    }


def get(settings: Settings, key: str) -> Plan:
    return catalogue(settings).get(key, catalogue(settings)[FREE])


def currency_for_country(country: str | None) -> str:
    """R-Q11: India bills in INR through Razorpay; everyone else USD/Stripe."""
    return "INR" if (country or "").upper() == INDIA else "USD"


def provider_for_currency(currency: str) -> str:
    return "razorpay" if currency.upper() == "INR" else "stripe"


def pick_currency(ccy_param: str | None, accept_language: str = "") -> str:
    """Which price set a VIEWER sees (checkout still decides by billing
    country). An explicit toggle choice wins; otherwise an Indian locale
    hint shows INR; the default is USD."""
    if ccy_param and ccy_param.upper() in CURRENCIES:
        return ccy_param.upper()
    return "INR" if "-in" in accept_language.lower() else "USD"


def viewer_currency(
    session: Session, user_id: str | None, ccy_param: str | None, accept_language: str = ""
) -> str:
    """One rule for every signed-in surface: a subscribed account sees its
    own billing currency; everyone else gets the viewer pick."""
    if user_id is not None:
        sub = session.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        ).scalar_one_or_none()
        if sub is not None and (sub.currency or "").upper() in CURRENCIES:
            return str(sub.currency).upper()
    return pick_currency(ccy_param, accept_language)


def cohort_used(session: Session, currency: str) -> int:
    """Subscriptions consumed from this market's launch cohort: distinct
    accounts that ever ACTIVATED with this market's provider, counted from
    the append-only audit log — NOT from Subscription rows, which are one
    mutable row per account (a later market switch would rewrite history
    and silently reopen a slot; cold-review f.2). Cancelled subscribers
    still count ('first N subscribers', not 'current N'); an account that
    only ever FAILED without activating never consumed a slot."""
    from tokenops_cost_auditor.persistence.models import AuditLogEntry

    provider = provider_for_currency(currency)
    entries = session.execute(
        select(AuditLogEntry.subject, AuditLogEntry.detail).where(
            AuditLogEntry.action == "subscription.activated"
        )
    ).all()
    return len(
        {
            subject
            for subject, detail in entries
            if isinstance(detail, dict) and detail.get("provider") == provider
        }
    )


def launch_open(session: Session, settings: Settings, currency: str) -> bool:
    """The code-enforced flip (R-PRICING-FINAL-2): launch pricing shows while
    the market's cohort has room, list pricing the moment it fills. The
    founder-side hosted payment page is updated on the ops-digest notice;
    until then a new subscriber could pay the launch price against a list
    display — an undercharge only, never the reverse."""
    return cohort_used(session, currency) < settings.launch_cohort_size


def one_shot_display(settings: Settings, currency: str = "USD") -> str:
    """The enterprise one-shot audit (R-Q5/Q6; deliberately not at parity —
    it carries founder time, not just compute)."""
    amount = settings.one_shot_inr if currency.upper() == "INR" else settings.one_shot_usd
    return f"{_symbol(currency)}{amount:,.0f}"


def one_shot_terms_display(settings: Settings) -> str:
    """Terms is a binding document covering BOTH markets, so it names both
    prices — contractual completeness, not pricing-page mixing (V-D10: the
    contract must never disagree with the checkout)."""
    return (
        f"{one_shot_display(settings, 'USD')} (global) / "
        f"{one_shot_display(settings, 'INR')} (India)"
    )
