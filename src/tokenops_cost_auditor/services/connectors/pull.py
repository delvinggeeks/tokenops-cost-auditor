"""Source pull: decrypt key -> fetch usage -> upsert source_usage buckets.

The ONLY place stored credentials are decrypted (crypto.py contract).
Upsert is idempotent on (source_id, day, model): re-pulls update counts in
place, never duplicate — PullStats.summary() is logged on EVERY pull
(UAT-D5 law analog for T2). Provenance (endpoint, page count, pull stats)
is stored per row; counts only (FR-22)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import Source, SourceUsage, utcnow
from tokenops_cost_auditor.services.connectors import anthropic_usage, openai_usage
from tokenops_cost_auditor.services.connectors.base import PullStats, SupportsGet
from tokenops_cost_auditor.services.connectors.crypto import decrypt_credential

log = structlog.get_logger("tokenops_cost_auditor.connectors")

_CLIENTS = {
    "openai": (openai_usage.fetch_usage, openai_usage.BASE_URL),
    "anthropic": (anthropic_usage.fetch_usage, anthropic_usage.BASE_URL),
}


def run_pull(
    session: Session,
    settings: Settings,
    source: Source,
    http_client: SupportsGet | None = None,
) -> PullStats:
    if source.provider not in _CLIENTS:
        raise ValueError(f"unknown provider: {source.provider}")
    if source.status != "active" or not source.credentials_encrypted:
        raise ValueError("source is not active (paused/revoked sources are never pulled)")

    fetch, endpoint = _CLIENTS[source.provider]
    api_key = decrypt_credential(settings.secret_key, source.credentials_encrypted)

    end_day = datetime.now(UTC).date()
    if source.last_pull_at is not None:
        # overlap 1 day so late-arriving provider revisions get upserted
        start_day = source.last_pull_at.date() - timedelta(days=1)
    else:
        start_day = end_day - timedelta(days=settings.connect_backfill_days)

    buckets, pages = fetch(api_key, start_day, end_day, http_client)
    del api_key  # narrow the plaintext lifetime; never logged (T-KEY-03 law)

    stats = PullStats(provider=source.provider, endpoint=endpoint, pages=pages)
    stats.buckets_in = len(buckets)
    provenance = {"endpoint": endpoint, "pages": pages, "window": f"{start_day}..{end_day}"}
    for b in buckets:
        existing = session.execute(
            select(SourceUsage).where(
                SourceUsage.source_id == source.id,
                SourceUsage.day == b["day"],
                SourceUsage.model == b["model"],
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                SourceUsage(
                    source_id=source.id,
                    provenance=provenance,
                    **{
                        k: b[k]
                        for k in (
                            "day",
                            "model",
                            "calls",
                            "prompt_tokens",
                            "completion_tokens",
                            "cached_tokens",
                        )
                    },
                )
            )
            stats.upserted += 1
        else:
            for field_name in ("calls", "prompt_tokens", "completion_tokens", "cached_tokens"):
                setattr(existing, field_name, b[field_name])
            existing.provenance = provenance
            stats.updated_existing += 1
    source.last_pull_at = utcnow()
    log.info("connector.pull", summary=stats.summary(), source_id=source.id)
    return stats
