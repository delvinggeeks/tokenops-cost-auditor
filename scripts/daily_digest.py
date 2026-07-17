"""Daily ops digest email (runbook §3) — business metrics as SQL, not dashboards.

Runs daily 03:00 UTC in the app container (ofelia.ini "daily-digest"). Sections:
audits run last 24h + failures, revenue marked, purge count, and ALERT lines for
backup absent >26h, disk >80%, pricing-table age >14d (NFR-15), and last
pricing_refresh failure (FR-29 — status file written by scripts/pricing_refresh.py).
DIGEST_TO unset -> body printed to stdout only (dev/staging); SMTP settings reuse
the FR-20 mail configuration.
"""

from __future__ import annotations

import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import Audit, AuditLogEntry, Payment
from tokenops_cost_auditor.persistence.repo import make_engine, make_session_factory
from tokenops_cost_auditor.services.pricing.table import PricingTable

BACKUP_MAX_AGE_H = 26  # runbook §3 alert condition
DISK_ALERT_PCT = 80
PRICING_MAX_AGE_DAYS = 14  # NFR-15
REFRESH_STATUS_REL = ".ops/pricing_refresh.json"  # written by scripts/pricing_refresh.py


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _last_backup_age_h(backup_dir: Path, now: datetime) -> float | None:
    dumps = list(backup_dir.glob("tokenops_*.dump"))
    if not dumps:
        return None
    newest = max(d.stat().st_mtime for d in dumps)
    return (now - datetime.fromtimestamp(newest, tz=UTC)).total_seconds() / 3600


def _refresh_failure_line(report_dir: Path) -> str | None:
    """FR-29: surface the last pricing_refresh failure, if its status file says so."""
    status_path = report_dir / REFRESH_STATUS_REL
    if not status_path.exists():
        return None
    import json

    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except ValueError:
        return f"pricing_refresh status file unreadable: {status_path}"
    if status.get("ok"):
        return None
    return (
        f"pricing_refresh FAILED at {status.get('ran_at', '?')}: "
        f"{status.get('error', 'unknown error')} (FR-29 — run manually, runbook §8)"
    )


def build_digest(session: Session, settings: Settings, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    since = now - timedelta(hours=24)
    lines: list[str] = [f"TokenOps Cost Auditor — daily digest {now:%Y-%m-%d %H:%M} UTC", ""]

    # audits last 24h
    audits = [a for a in session.scalars(select(Audit)) if _as_utc(a.created_at) >= since]
    by_status: dict[str, int] = {}
    for a in audits:
        by_status[a.status] = by_status.get(a.status, 0) + 1
    lines.append(f"Audits (24h): {len(audits)} ({by_status or 'none'})")
    failures = [a for a in session.scalars(select(Audit).where(Audit.status == "failed"))]
    if failures:
        lines.append(f"FAILED audits needing triage: {len(failures)}")
        lines.extend(f"  - {a.id}: {a.error or 'no message'}" for a in failures[:10])

    # revenue marked last 24h
    payments = [p for p in session.scalars(select(Payment)) if _as_utc(p.ts) >= since]
    by_currency: dict[str, float] = {}
    for p in payments:
        by_currency[p.currency] = by_currency.get(p.currency, 0.0) + p.amount
    revenue = ", ".join(f"{amt:.2f} {cur}" for cur, amt in sorted(by_currency.items())) or "0"
    lines.append(f"Revenue marked (24h): {revenue} across {len(payments)} payment(s)")

    # purges last 24h (FR-21 evidence)
    purges = [
        e
        for e in session.scalars(
            select(AuditLogEntry).where(AuditLogEntry.action == "audit.purged")
        )
        if _as_utc(e.ts) >= since
    ]
    lines.append(f"Purges (24h): {len(purges)}")

    # R-GTM-CONTROL: weekly early-access signups = Phase-2 trigger evidence
    week_ago = now - timedelta(days=7)
    signups = [
        e
        for e in session.scalars(
            select(AuditLogEntry).where(AuditLogEntry.action == "early_access.signup")
        )
        if _as_utc(e.ts) >= week_ago
    ]
    lines.append(f"Control-plane early-access signups (7d): {len(signups)}")

    # alerts
    alerts: list[str] = []
    backup_age = _last_backup_age_h(Path(settings.backup_dir), now)
    if backup_age is None:
        alerts.append("no backup dump found at all (NFR-08)")
    elif backup_age > BACKUP_MAX_AGE_H:
        alerts.append(f"backup absent >{BACKUP_MAX_AGE_H}h (latest is {backup_age:.0f}h old)")

    # uploads and backups may back onto different filesystems (named volume vs
    # bind mount) — sample both, deduping filesystems by their total size+free
    seen_fs: set[tuple[int, int]] = set()
    for label, path in (("uploads", settings.upload_dir), ("backups", settings.backup_dir)):
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            alerts.append(f"disk usage check failed for {label} ({path})")
            continue
        if (usage.total, usage.free) in seen_fs:
            continue
        seen_fs.add((usage.total, usage.free))
        pct = usage.used / usage.total * 100
        if pct > DISK_ALERT_PCT:
            alerts.append(f"disk {pct:.0f}% full at {label} ({path}) (> {DISK_ALERT_PCT}%)")

    table = PricingTable.load()
    if table.last_verified is None:
        alerts.append("prices.yaml has NO last_verified date (NFR-15)")
    else:
        age = (now.date() - table.last_verified).days
        marker = " — STALE, re-verify (runbook §8)" if age > PRICING_MAX_AGE_DAYS else ""
        lines.append(f"Pricing table: last_verified {table.last_verified} ({age} days){marker}")
        if age > PRICING_MAX_AGE_DAYS:
            alerts.append(f"pricing table {age} days old (> {PRICING_MAX_AGE_DAYS}, NFR-15)")

    refresh_line = _refresh_failure_line(Path(settings.report_dir))
    if refresh_line:
        alerts.append(refresh_line)

    if failures:
        alerts.append(f"{len(failures)} audit(s) in failed status")

    lines.append("")
    if alerts:
        lines.append("ALERTS:")
        lines.extend(f"  !! {a}" for a in alerts)
    else:
        lines.append("No alerts.")
    return "\n".join(lines)


def main() -> int:
    settings = Settings()
    engine = make_engine(settings.database_url)
    with make_session_factory(engine)() as session:
        body = build_digest(session, settings)
    print(body)
    if settings.digest_to and settings.smtp_host:
        from tokenops_cost_auditor.services.mail.smtp import SmtpMailAdapter

        adapter = SmtpMailAdapter(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_user,
            settings.smtp_password,
            settings.smtp_from,
            base_url=settings.app_base_url,
        )
        adapter.send_digest(settings.digest_to, body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
