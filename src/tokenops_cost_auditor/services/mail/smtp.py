"""SMTP adapter (FR-20) — env-gated: selected only when SMTP_HOST is set.
Provider-agnostic (any SMTP endpoint); STARTTLS when the server offers it."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

import structlog

log = structlog.get_logger("tokenops_cost_auditor.mail")


class SmtpMailAdapter:
    def __init__(
        self, host: str, port: int, user: str, password: str, from_addr: str, base_url: str = ""
    ) -> None:
        self.host, self.port = host, port
        self.user, self.password = user, password
        self.from_addr = from_addr
        self.base_url = base_url.rstrip("/")

    def _send(self, to_email: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = self.from_addr
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(self.host, self.port, timeout=10) as server:
            server.ehlo()
            if server.has_extn("starttls"):
                server.starttls()
                server.ehlo()
            if self.user:
                server.login(self.user, self.password)
            server.send_message(msg)
        log.info("mail.sent", to=to_email, subject=subject)

    def magic_link(self, to_email: str, link_url: str) -> None:
        self._send(
            to_email,
            "Your TokenOps Cost Auditor sign-in link",
            "Click to sign in (works once, expires in 15 minutes):\n\n"
            f"{self.base_url}{link_url}\n\nIf you didn't request this, ignore this email.",
        )

    def report_ready(self, to_email: str, report_url: str) -> None:
        self._send(
            to_email,
            "Your audit report is ready",
            "Your TokenOps Cost Auditor report is ready:\n\n"
            f"{self.base_url}{report_url}\n\nThe link expires in 30 days.",
        )
