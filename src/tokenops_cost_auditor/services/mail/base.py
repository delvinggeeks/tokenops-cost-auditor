"""MailPort (docs/02-HLD.md C8, FR-20). SMTP adapter lands at D8; the log adapter
is the default whenever SMTP_* is unconfigured (dev/test: links appear in logs)."""

from __future__ import annotations

from typing import Protocol

import structlog

log = structlog.get_logger("tokenops_cost_auditor.mail")


class MailPort(Protocol):
    def report_ready(self, to_email: str, report_url: str) -> None: ...

    def magic_link(self, to_email: str, link_url: str) -> None: ...


class LogMailAdapter:
    """Structured-log delivery — never sends network mail (PLAN §0.2 MAIL)."""

    def report_ready(self, to_email: str, report_url: str) -> None:
        log.info("mail.report_ready", to=to_email, url=report_url)

    def magic_link(self, to_email: str, link_url: str) -> None:
        log.info("mail.magic_link", to=to_email, url=link_url)
