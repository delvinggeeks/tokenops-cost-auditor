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
        # a bare address reads as machine mail; the display name reads as a
        # company (founder walkthrough 2026-07-22)
        msg["From"] = f"TokenOps Cost Auditor <{self.from_addr}>"
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
            "Sign in to TokenOps Cost Auditor",
            "Use this secure link to sign in to your TokenOps Cost Auditor "
            "account:\n\n"
            f"{self.base_url}{link_url}\n\n"
            "The link works once and expires in 15 minutes. If you didn't "
            "request it, you can safely ignore this email — no one can sign "
            "in without access to this inbox.\n\n"
            "TokenOps Cost Auditor — by WitAura\n"
            f"{self.base_url}",
        )

    def workspace_invite(self, to_email: str, link_url: str, workspace_name: str) -> None:
        self._send(
            to_email,
            f"You're invited to join {workspace_name} on TokenOps Cost Auditor",
            f"You've been invited to join the {workspace_name} workspace on "
            "TokenOps Cost Auditor. Use this secure link to accept:\n\n"
            f"{self.base_url}{link_url}\n\n"
            "The link works once and expires in 7 days. You'll need to sign in "
            "with THIS email address to accept — a link alone can't join a "
            "different account. If you weren't expecting this, you can ignore "
            "this email.\n\n"
            "TokenOps Cost Auditor — by WitAura\n"
            f"{self.base_url}",
        )

    def report_ready(self, to_email: str, report_url: str) -> None:
        self._send(
            to_email,
            "Your audit report is ready",
            "Your TokenOps Cost Auditor report is ready:\n\n"
            f"{self.base_url}{report_url}\n\nThe link expires in 30 days.",
        )

    def alert(self, to_email: str, subject: str, body: str) -> None:
        """Alert mail: one column, text-first, no images, one CTA (R-DESIGN §4e)."""
        self._send(to_email, subject, body)

    def send_digest(self, to_email: str, body: str) -> None:
        """Founder ops digest (runbook §3; scripts/daily_digest.py)."""
        subject = "TokenOps daily digest"
        if "ALERTS:" in body:
            subject += " — ALERTS"
        self._send(to_email, subject, body)
