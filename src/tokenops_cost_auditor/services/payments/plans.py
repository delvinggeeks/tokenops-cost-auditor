"""Plan catalogue (PLAN-V15 V-D8 / WP-6) — THE price config.

Every money amount the product renders comes from here (founder, 2026-07-22:
"never inline"). Prices themselves live in Settings so a change is a config
change, not a code change; this module gives them names, entitlements and
display strings.

R-Q11/Q12: Razorpay for India-billing customers (INR list fixed in config),
Stripe for everyone else (USD). One subscription per account.
"""

from __future__ import annotations

from dataclasses import dataclass

from tokenops_cost_auditor.config import Settings

FREE = "free"
PRO = "pro"
TEAM = "team"
PAID_PLANS = (PRO, TEAM)
ALL_PLANS = (FREE, PRO, TEAM)

# R-Q11: currency follows the customer's billing country, chosen at checkout.
INDIA = "IN"


@dataclass(frozen=True)
class Plan:
    key: str
    name: str
    usd: float | None  # None = not sold as a subscription
    inr: float | None
    sources: int  # active provider connections allowed
    scheduled_audits: bool
    uploads: str
    blurb: str

    def price(self, currency: str) -> float | None:
        return self.inr if currency.upper() == "INR" else self.usd

    def display(self, currency: str = "USD") -> str:
        amount = self.price(currency)
        if amount is None:
            return "—"
        symbol = "₹" if currency.upper() == "INR" else "$"
        return f"{symbol}{amount:,.0f}/mo"

    def display_both(self) -> str:
        """R-Q11: display BOTH currencies wherever a paid plan is shown."""
        if self.usd is None or self.inr is None:
            return "—"
        return f"${self.usd:,.0f}/mo · ₹{self.inr:,.0f}/mo"


def catalogue(settings: Settings) -> dict[str, Plan]:
    limits = settings.plan_source_limits
    return {
        FREE: Plan(
            key=FREE,
            name="Free",
            usd=None,
            inr=None,
            sources=limits.get(FREE, 0),
            scheduled_audits=False,
            uploads="one audit of an uploaded log file",
            blurb="One full six-detector audit of a log file you upload. No card.",
        ),
        PRO: Plan(
            key=PRO,
            name="Pro",
            usd=settings.plan_pro_usd,
            inr=settings.plan_pro_inr,
            sources=limits.get(PRO, 1),
            scheduled_audits=True,
            uploads="unlimited manual uploads",
            blurb="One connected source, audited weekly, plus alerts and your "
            "monthly Savings Statement.",
        ),
        TEAM: Plan(
            key=TEAM,
            name="Team",
            usd=settings.plan_team_usd,
            inr=settings.plan_team_inr,
            sources=limits.get(TEAM, 5),
            scheduled_audits=True,
            uploads="unlimited manual uploads",
            blurb="Five connected sources with priority processing.",
        ),
    }


def get(settings: Settings, key: str) -> Plan:
    return catalogue(settings).get(key, catalogue(settings)[FREE])


def currency_for_country(country: str | None) -> str:
    """R-Q11: India bills in INR through Razorpay; everyone else USD/Stripe."""
    return "INR" if (country or "").upper() == INDIA else "USD"


def provider_for_currency(currency: str) -> str:
    return "razorpay" if currency.upper() == "INR" else "stripe"


def one_shot_display(settings: Settings) -> str:
    """The $500 one-shot audit stays for enterprises (R-Q5/Q6 unchanged)."""
    inr = settings.inr_per_usd_display * 500.0
    return f"$500 · ₹{inr:,.0f}"
