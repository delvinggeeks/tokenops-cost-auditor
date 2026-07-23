"""Copilot seat-waste analyzer (WP-COPILOT-AGG, R-COPILOT).

A DIFFERENT analysis from the six token detectors: GitHub Copilot bills per
SEAT, not per token, so the waste is IDLE SEATS — licenses assigned to
people who have not used Copilot in a while. This module parses an admin
seat export (the /orgs/{org}/copilot/billing/seats JSON, or a CSV) and
produces one seat-governance Finding.

Two honesty boundaries, both from the R-COPILOT ruling:
- COUNTS-ONLY (FR-22 trivially): we read only each seat's last-activity and
  created dates and the pending-cancellation flag — never a login, never
  any content. The finding reports COUNTS; the customer looks up which
  seats in GitHub (the fix_text says exactly where).
- The dollar figure is a STATED INPUT, not a verified rate. Copilot's
  per-seat price is a SaaS subscription price, outside R-AUTO-PRICING's
  per-token feed, so `rate_usd` defaults to GitHub's public $19 and is
  labeled an assumption the customer confirms — the seat COUNTS are the
  measured fact, the rate is not.

Observe-only (X-02): we surface idle seats; reclaiming them is the
customer's action in GitHub. We never touch their org.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from tokenops_cost_auditor.services.rules.findings import (
    Confidence,
    Finding,
    Severity,
    severity_for_impact,
)

DEFAULT_IDLE_DAYS = 30
DEFAULT_SEAT_RATE_USD = 19.0  # GitHub Copilot Business public list price (an INPUT)


@dataclass(frozen=True)
class SeatRecord:
    """One billed seat, dates only — never a login (FR-22)."""

    last_activity_at: datetime | None
    created_at: datetime | None
    pending_cancellation: bool


@dataclass(frozen=True)
class SeatSummary:
    total: int
    active: int
    idle: int
    never_used: int
    pending_cancellation: int
    idle_days: int
    rate_usd: float
    monthly_recoverable_usd: float


def _parse_dt(value: object) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def parse_seats(blob: str) -> list[SeatRecord]:
    """Admin seat export -> SeatRecords. Accepts the GitHub API JSON
    ({"seats":[{"last_activity_at","created_at","pending_cancellation_date"}]})
    or a CSV with last_activity_at / created_at / pending_cancellation columns.
    Logins, if present, are IGNORED — dates and the flag only (FR-22)."""
    text = blob.strip()
    rows: list[dict[str, object]] = []
    if text.startswith("{") or text.startswith("["):
        data = json.loads(text)
        raw = data.get("seats", data) if isinstance(data, dict) else data
        if not isinstance(raw, list):
            raise ValueError("Copilot seats JSON has no 'seats' array")
        rows = [r for r in raw if isinstance(r, dict)]
    else:
        reader = csv.DictReader(io.StringIO(text))
        rows = [{k.lower().strip(): v for k, v in r.items()} for r in reader]

    out: list[SeatRecord] = []
    for r in rows:
        pc = r.get("pending_cancellation_date") or r.get("pending_cancellation")
        out.append(
            SeatRecord(
                last_activity_at=_parse_dt(r.get("last_activity_at")),
                created_at=_parse_dt(r.get("created_at")),
                pending_cancellation=bool(pc)
                and str(pc).strip().lower() not in ("", "false", "none", "0"),
            )
        )
    if not out:
        raise ValueError("no seats found in the export")
    return out


def analyze(
    seats: list[SeatRecord],
    *,
    idle_days: int = DEFAULT_IDLE_DAYS,
    rate_usd: float = DEFAULT_SEAT_RATE_USD,
    now: datetime | None = None,
) -> SeatSummary:
    """Count idle seats and the monthly dollars they represent."""
    now = now or datetime.now(UTC)
    cutoff = now.timestamp() - idle_days * 86400
    total = len(seats)
    never_used = sum(1 for s in seats if s.last_activity_at is None)
    idle = sum(
        1 for s in seats if s.last_activity_at is None or s.last_activity_at.timestamp() < cutoff
    )
    pending = sum(1 for s in seats if s.pending_cancellation)
    return SeatSummary(
        total=total,
        active=total - idle,
        idle=idle,
        never_used=never_used,
        pending_cancellation=pending,
        idle_days=idle_days,
        rate_usd=rate_usd,
        monthly_recoverable_usd=round(idle * rate_usd, 2),
    )


def build_finding(summary: SeatSummary) -> Finding:
    """The one seat-governance finding — labeled so it never reads as a
    token detector. Dollars are the idle-seat count times the STATED rate."""
    impact = summary.monthly_recoverable_usd
    return Finding(
        id="d7_idle_seats:copilot",
        detector="d7_idle_seats",
        severity=severity_for_impact(impact),
        monthly_cost_impact_usd=impact,
        # the rate is an input, not a verified price — the confidence says so
        confidence=Confidence.ESTIMATED,
        fix_text=(
            f"{summary.idle} of {summary.total} Copilot seats show no activity in "
            f"{summary.idle_days}+ days ({summary.never_used} never used). At "
            f"${summary.rate_usd:.0f}/seat/mo that is ${impact:,.2f}/mo. In GitHub → "
            f"your organization → Settings → Copilot → Access, sort by last activity "
            f"and reclaim the idle seats. Seat pricing is your plan's rate — confirm it "
            f"if it differs from the ${summary.rate_usd:.0f} assumed here."
        ),
        detail={
            "kind": "seat_governance",
            "total_seats": summary.total,
            "idle_seats": summary.idle,
            "never_used": summary.never_used,
            "pending_cancellation": summary.pending_cancellation,
            "idle_days": summary.idle_days,
            "rate_usd": summary.rate_usd,
            "rate_is_input": True,  # NOT an R-AUTO-PRICING verified figure
        },
    )


_ = Severity  # re-exported for callers building richer seat findings
