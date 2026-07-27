"""Settings → Webhooks (R-PLATFORM slice 3, S-5). A workspace registers an
outbound URL; every completed audit POSTs a signed `audit.completed` event to
each active endpoint (services/webhooks/dispatcher.py, wired via
AuditRunner.webhooks). Observe-and-notify only — X-01/X-02 SAFE: this surface
never sits in the request path and never enforces anything on the customer's
LLM traffic.

Managing endpoints is a MANAGE_SOURCES action (O-2): the list is visible to
every role (VIEW is universal — mirrors routes_sources.py), but the add/remove
controls render only for owner/admin (R-ORG: absent, never a disabled
403-trap) and a forged POST from a non-manager fails closed with 403.
"""

from __future__ import annotations

import secrets
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.api.routes_upload import current_user
from tokenops_cost_auditor.obs.ratelimit import limiter
from tokenops_cost_auditor.persistence.models import WebhookDelivery, WebhookEndpoint, utcnow
from tokenops_cost_auditor.persistence.repo import (
    active_role,
    active_workspace_id,
    get_or_create_user,
)
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.web import authz
from tokenops_cost_auditor.web.routes_dashboard import _render, _session, _shell_ctx

router = APIRouter(prefix="/settings/webhooks", tags=["webhooks"])

MAX_ENDPOINTS_PER_WORKSPACE = 10
RECENT_DELIVERIES_LIMIT = 20


def _require_manage_sources(session: Session, user_id: str) -> None:
    """O-2 RBAC: registering/removing an outbound endpoint is a MANAGE_SOURCES
    action — owner or admin only. Fail-closed at the route boundary: a
    member/viewer 403s before any write, even if they forge the POST directly."""
    authz.ensure(
        active_role(session, user_id),
        authz.Perm.MANAGE_SOURCES,
        detail="only an owner or admin can manage webhooks",
    )


def _valid_webhook_url(url: str) -> bool:
    """Absolute http(s) URL; https required except for loopback (dev)."""
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if p.scheme not in ("http", "https") or not p.netloc:
        return False
    host = p.hostname or ""
    return not (p.scheme == "http" and host not in ("localhost", "127.0.0.1", "::1"))


@router.get("", response_class=HTMLResponse)
def webhooks_page(request: Request, user_email: str = Depends(current_user)) -> HTMLResponse:
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        ws = active_workspace_id(session, user.id)
        assert ws is not None  # every authenticated user has an active workspace (O-0)
        endpoints = (
            session.execute(
                select(WebhookEndpoint)
                .where(WebhookEndpoint.workspace_id == ws, WebhookEndpoint.active.is_(True))
                .order_by(WebhookEndpoint.created_at)
            )
            .scalars()
            .all()
        )
        endpoint_url_by_id = {e.id: e.url for e in endpoints}
        deliveries: list[WebhookDelivery] = []
        if endpoint_url_by_id:
            deliveries = list(
                session.execute(
                    select(WebhookDelivery)
                    .where(WebhookDelivery.endpoint_id.in_(endpoint_url_by_id))
                    .order_by(WebhookDelivery.attempted_at.desc())
                    .limit(RECENT_DELIVERIES_LIMIT)
                )
                .scalars()
                .all()
            )
        delivery_view = [
            {
                "endpoint_url": endpoint_url_by_id.get(d.endpoint_id, "(removed endpoint)"),
                "event": d.event,
                "status_code": d.status_code,
                "attempted_at": d.attempted_at,
            }
            for d in deliveries
        ]
        ctx = _shell_ctx(session, request, user, "webhooks")
    return _render(
        request,
        "app/webhooks.html",
        endpoints=endpoints,
        deliveries=delivery_view,
        settings_tab="webhooks",
        **{k: v for k, v in ctx.items() if k != "plan"},
    )


@router.post("", response_class=HTMLResponse)
@limiter.limit("5/minute")
def create_webhook(
    request: Request, url: str = Form(""), user_email: str = Depends(current_user)
) -> HTMLResponse:
    """Register an outbound endpoint. The signing secret is shown ONCE here;
    unlike a credential we only ever verify, we must keep it (plaintext) to
    sign every future delivery — see WebhookEndpoint's docstring."""
    target = url.strip()
    if not _valid_webhook_url(target):
        raise HTTPException(
            status_code=400,
            detail="give an absolute https URL (http only for localhost)",
        )
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        _require_manage_sources(session, user.id)
        ws = active_workspace_id(session, user.id)
        assert ws is not None
        active = session.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.workspace_id == ws, WebhookEndpoint.active.is_(True)
            )
        ).scalars()
        if len(list(active)) >= MAX_ENDPOINTS_PER_WORKSPACE:
            raise HTTPException(
                status_code=403,
                detail=f"{MAX_ENDPOINTS_PER_WORKSPACE} webhook endpoints is the "
                "limit — remove one first",
            )
        secret = f"whsec_{secrets.token_urlsafe(32)}"
        session.add(WebhookEndpoint(workspace_id=ws, url=target, secret=secret))
        auditlog.append(session, user_email, "webhook.endpoint_added", target)
        session.commit()
    tpl = request.app.state.jinja.get_template("app/_webhook_secret.html")
    return HTMLResponse(tpl.render(secret=secret, url=target))


@router.post("/{endpoint_id}/delete")
def delete_webhook(
    request: Request, endpoint_id: str, user_email: str = Depends(current_user)
) -> RedirectResponse:
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        _require_manage_sources(session, user.id)
        ws = active_workspace_id(session, user.id)
        row = session.get(WebhookEndpoint, endpoint_id)
        if row is None or row.workspace_id != ws:
            raise HTTPException(status_code=404, detail="webhook endpoint not found")
        row.active = False
        row.secret = None  # authority law: signing material deleted
        row.revoked_at = utcnow()
        auditlog.append(session, user_email, "webhook.endpoint_removed", row.url)
        session.commit()
    return RedirectResponse("/settings/webhooks", status_code=303)
