"""Best-effort outbound delivery (R-PLATFORM slice 3, S-5). One attempt, a
short timeout, the status recorded either way so the UI can show it honestly.
A durable retry queue is a later SCALING slice — out of scope here."""

from __future__ import annotations

import json

import httpx
import structlog
from sqlalchemy import Engine, select

from tokenops_cost_auditor.obs import errors as obs_errors
from tokenops_cost_auditor.persistence.models import WebhookDelivery, WebhookEndpoint
from tokenops_cost_auditor.persistence.repo import make_session_factory
from tokenops_cost_auditor.services.webhooks.base import sign

log = structlog.get_logger("tokenops_cost_auditor.webhooks")

TIMEOUT_S = 5.0
EVENT_AUDIT_COMPLETED = "audit.completed"
SIGNATURE_HEADER = "X-TokenOps-Signature"
EVENT_HEADER = "X-TokenOps-Event"


class WebhookDispatcher:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def dispatch_audit_completed(self, workspace_id: str, payload: dict[str, object]) -> None:
        """Best-effort by construction: any failure here (bad endpoint config,
        DB hiccup, network error) is caught and logged, never raised — a
        webhook delivery problem must never fail the audit it reports on."""
        try:
            self._dispatch(workspace_id, {"event": EVENT_AUDIT_COMPLETED, **payload})
        except Exception as exc:
            obs_errors.capture_exception(exc)
            log.warning("webhook.dispatch_failed", workspace_id=workspace_id, error=str(exc))

    def _dispatch(self, workspace_id: str, body_obj: dict[str, object]) -> None:
        factory = make_session_factory(self.engine)
        with factory() as session:
            endpoints = (
                session.execute(
                    select(WebhookEndpoint).where(
                        WebhookEndpoint.workspace_id == workspace_id,
                        WebhookEndpoint.active.is_(True),
                    )
                )
                .scalars()
                .all()
            )
            if not endpoints:
                return
            body = json.dumps(body_obj, sort_keys=True).encode()
            for endpoint in endpoints:
                status_code = self._send(endpoint, body)
                session.add(
                    WebhookDelivery(
                        endpoint_id=endpoint.id,
                        event=EVENT_AUDIT_COMPLETED,
                        status_code=status_code,
                    )
                )
            session.commit()

    def _send(self, endpoint: WebhookEndpoint, body: bytes) -> int | None:
        if not endpoint.secret:
            return None  # revoked between the query and the send — nothing to sign with
        try:
            resp = httpx.post(
                endpoint.url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    SIGNATURE_HEADER: sign(endpoint.secret, body),
                    EVENT_HEADER: EVENT_AUDIT_COMPLETED,
                },
                timeout=TIMEOUT_S,
            )
            return resp.status_code
        except httpx.HTTPError as exc:
            log.warning("webhook.delivery_failed", endpoint_id=endpoint.id, error=str(exc))
            return None
