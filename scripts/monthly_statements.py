"""Ofelia entrypoint: issue last month's Savings Statement to every user.

Runs on the 1st. Idempotent: a statement already sent is never rebuilt or
re-sent by this job (an archived artifact does not change after it leaves).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import get_settings
from tokenops_cost_auditor.persistence.models import User
from tokenops_cost_auditor.services.mail.base import LogMailAdapter
from tokenops_cost_auditor.services.mail.smtp import SmtpMailAdapter
from tokenops_cost_auditor.services.statements import build as statements


def previous_month(now: datetime) -> tuple[int, int]:
    return (now.year - 1, 12) if now.month == 1 else (now.year, now.month - 1)


def main() -> int:
    settings = get_settings()
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
    year, month = previous_month(datetime.now(UTC))
    issued = skipped = failed = 0
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        for user in session.execute(select(User)).scalars().all():
            # Per-user isolation: one bad address or build must not cost every
            # later user their statement (V-D6 cold-review f.4).
            try:
                if user.statement_emails is False:  # NULL = opted in
                    skipped += 1
                    continue
                doc = statements.build(session, user, year, month)
                row = statements.archive(session, user, doc)
                session.flush()
                if statements.send(session, mail, user, row):
                    issued += 1
                else:
                    skipped += 1
                session.commit()
            except Exception as exc:
                session.rollback()
                failed += 1
                print(f"  statement failed for {user.id}: {str(exc)[:120]}", file=sys.stderr)
    print(
        f"statements {year:04d}-{month:02d}: issued={issued} already_sent={skipped} failed={failed}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
