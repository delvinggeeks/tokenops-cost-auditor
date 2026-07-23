"""Source pull: decrypt key -> fetch usage -> upsert source_usage buckets.

The ONLY place stored credentials are decrypted (crypto.py contract).
Upsert is idempotent on (source_id, day, model): re-pulls update counts in
place, never duplicate — PullStats.summary() is logged on EVERY pull
(UAT-D5 law analog for T2). Provenance (endpoint, page count, pull stats)
is stored per row; counts only (FR-22)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import PullEvent, Source, SourceUsage, utcnow
from tokenops_cost_auditor.services.connectors import (
    anthropic_usage,
    azure_usage,
    bedrock_usage,
    openai_usage,
    vertex_usage,
)
from tokenops_cost_auditor.services.connectors.base import PullStats, SupportsGet
from tokenops_cost_auditor.services.connectors.crypto import (
    credential_fingerprint,
    decrypt_credential,
)

log = structlog.get_logger("tokenops_cost_auditor.connectors")

# Fetchers share one calling shape: (credential, start, end, client) ->
# (buckets, pages). Azure's credential is the packed four-field JSON and its
# client also POSTs (token exchange); Callable[...] keeps the registry honest
# about that widening.
_CLIENTS: dict[str, tuple[Callable[..., tuple[list[dict[str, Any]], int]], str]] = {
    "openai": (openai_usage.fetch_usage, openai_usage.BASE_URL),
    "anthropic": (anthropic_usage.fetch_usage, anthropic_usage.BASE_URL),
    "azure-openai": (azure_usage.fetch_usage, azure_usage.BASE_URL),
    "bedrock": (bedrock_usage.fetch_usage, bedrock_usage.BASE_URL),
    "vertex-ai": (vertex_usage.fetch_usage, vertex_usage.BASE_URL),
}


def run_pull(
    session: Session,
    settings: Settings,
    source: Source,
    http_client: SupportsGet
    | azure_usage.SupportsHttp
    | bedrock_usage.SupportsSignedPost
    | None = None,
) -> PullStats:
    if source.provider not in _CLIENTS:
        raise ValueError(f"unknown provider: {source.provider}")
    if source.status != "active" or not source.credentials_encrypted:
        raise ValueError("source is not active (paused/revoked sources are never pulled)")

    fetch, endpoint = _CLIENTS[source.provider]
    api_key = decrypt_credential(settings.secret_key, source.credentials_encrypted)
    if source.key_fingerprint is None:
        # R-MULTI-SOURCE backfill: pre-013 sources gain their fingerprint on
        # the first pull after upgrade, so the same-key-twice guard covers
        # them without ever re-asking for the key. Rides this pull's commit.
        source.key_fingerprint = credential_fingerprint(settings.secret_key, api_key)

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
            # Latest-wins by design (G-V1 cold-reviewer f.4): the row always
            # reflects its most recent fetch; pull history lives in the
            # PullStats summary logged on every pull, not per row.
            existing.provenance = provenance
            stats.updated_existing += 1
    source.last_pull_at = utcnow()
    # WP-PIPELINE-UI: every pull leaves a ledger row (rides the caller's
    # commit, same transaction as the usage upserts it describes).
    session.add(
        PullEvent(
            source_id=source.id,
            ok=True,
            buckets_in=stats.buckets_in,
            upserted=stats.upserted,
            updated=stats.updated_existing,
        )
    )
    log.info("connector.pull", summary=stats.summary(), source_id=source.id)
    return stats


def record_pull_failure(session: Session, source_id: str, exc: Exception) -> None:
    """The failure half of the pull ledger ("every pull, including the
    failures"). USER-SAFE words only: the typed auth error keeps its message;
    anything else collapses to a generic line — internals stay in logs.
    Commits in its own transaction; callers invoke it AFTER rollback."""
    text = (
        "provider rejected the stored key"
        if isinstance(exc, openai_usage.ConnectorAuthError)
        else "pull failed — provider or network error"
    )
    session.add(PullEvent(source_id=source_id, ok=False, error=text))
    session.commit()
