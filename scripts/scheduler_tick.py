"""Ofelia entrypoint (hourly): pull due sources, run due weekly audits.

Runs in the app container against the live DB (same pattern as
daily_digest.py). Exit 0 even with per-source errors — they are logged and
surface in the daily digest; a hard nonzero exit is reserved for the
scheduler itself being unable to run (DB down)."""

from __future__ import annotations

import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import get_settings
from tokenops_cost_auditor.services.connectors.schedule import tick
from tokenops_cost_auditor.services.mail.base import LogMailAdapter
from tokenops_cost_auditor.services.mail.smtp import SmtpMailAdapter
from tokenops_cost_auditor.services.pricing.table import PricingTable


def main() -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    mail = (
        SmtpMailAdapter(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_user,
            settings.smtp_password,
            settings.smtp_from,
            settings.app_base_url,
        )
        if settings.smtp_host
        else LogMailAdapter()
    )
    with Session(engine) as session:
        stats = tick(session, settings, PricingTable.load(), mail=mail)
    print(
        f"scheduler tick: pulled={stats['pulled']} pull_errors={stats['pull_errors']} "
        f"audited={stats['audited']} audit_errors={stats['audit_errors']} "
        f"alerts_fired={stats.get('alerts_fired', 0)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
