"""SQLAlchemy models (docs/02-HLD.md §4, docs/03-LLD.md §6).

FR-22: no prompt/completion text column exists anywhere. findings.evidence_sample
holds EvidenceRef dicts (counts/metadata, ≤20 enforced at write). audit_log is
append-only (no UPDATE/DELETE issued by code; DB grants at D13). All timestamps
UTC (NFR-11). Migrations additive-only (runbook §2). idempotency_keys per FR-26.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic constraint names so additive-only Alembic migrations stay stable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # single-use magic links: tokens issued at/before this instant are dead (FR-17)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # v1.5 V-D4g: guided-tour dismissal, server-side so it survives devices;
    # "Replay tour" clears it (R-DESIGN-V3 §2a).
    tour_dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # v1.5 V-D7 email preference. Transactional mail (magic links,
    # report-ready) is never opt-out; this covers the monthly statement.
    statement_emails: Mapped[bool | None] = mapped_column(Boolean)
    # R-DAILY-LOOP: when the daily spend digest last went out (dedupe stamp)
    last_daily_digest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Wave B digest control: opt out of the daily spend digest. None/True = on.
    daily_digest_emails: Mapped[bool | None] = mapped_column(Boolean)
    # R-F1 SIGN-OFF (2026-07-23): peer-benchmark cohort membership.
    # None = included (the default, disclosed); False = excluded. The
    # training frame and every future cohort computation MUST honor it.
    benchmark_sharing: Mapped[bool | None] = mapped_column(Boolean)
    # Wave B activity center: when the customer last opened their activity
    # feed. Events after this are "new" (the topbar bell badge).
    activity_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Session epoch (readiness audit 2026-07-22): sessions are stateless signed
    # cookies, so "log out"/"close account" could only clear the ACTING
    # browser — a cookie captured elsewhere stayed valid to TTL. Any session
    # issued at-or-before this instant is now rejected, so bumping it kills
    # every existing session for the user.
    sessions_valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # O-1b (R-ORG): the workspace the user is currently acting in. Plain
    # String(32), no FK (the O-0 additive-safe convention) — repo.
    # active_workspace_id validates it against LIVE memberships and falls back to
    # the personal workspace, so a stale/foreign value can never scope a read.
    # None (the backfill default is the personal workspace) is treated as "not
    # switched" → personal workspace.
    active_workspace_id: Mapped[str | None] = mapped_column(String(32))


class Workspace(Base):
    """O-0 (R-ORG): the tenancy root. Every resource is owned by a workspace;
    every user belongs to at least one (their personal workspace-of-one, the
    single-tenant default). The audit ENGINE never sees this table — tenancy
    lives only at the web/persistence boundary (CLAUDE.md R-ORG)."""

    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    # True for a backfilled workspace-of-one (never renamed by an org). Lets the
    # UI say "your workspace" vs a named org, and O-1 invites target real orgs.
    personal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # FR-35 (R-MODEL-FACTORY): explicit per-workspace opt-in to the cohort
    # export — the ONLY data path into the model factory. NOT NULL default
    # False: absence = excluded, the safe default IS the law. Distinct from
    # User.benchmark_sharing (in-product benchmark cohort, opt-OUT default
    # included) — this flag governs data LEAVING to the factory, nothing else.
    cohort_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class WorkspaceMember(Base):
    """O-0: who belongs to a workspace and their role. O-0 only ever writes
    role='owner' (the minter); O-1 adds invites/members, O-2 the other roles.
    One row per (workspace, user)."""

    __tablename__ = "workspace_members"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="owner")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),
        # O-0 (R-ORG): make the workspace-of-one 1:1 invariant a DB FACT, not an
        # incidental one — at most ONE owner membership per user. A partial
        # unique index (portable: Postgres + SQLite ≥3.8 both honor the WHERE),
        # so the racy self-heal path in get_or_create_workspace can't mint a
        # second personal workspace (cold-reviewer O-0 f.1). O-1 revisits when a
        # user may own more than one workspace.
        Index(
            "uq_owner_membership_per_user",
            "user_id",
            unique=True,
            sqlite_where=text("role = 'owner'"),
            postgresql_where=text("role = 'owner'"),
        ),
    )


class WorkspaceInvite(Base):
    """O-1b (R-ORG): invite a person (by email) into a workspace with a role.
    Reuses the LinkCode grammar — the code is a SECRET shown once and stored only
    as a keyed HMAC (`code_hash`); acceptance is single-use via an atomic
    consume. The invitee's email must match on accept (defense in depth: a leaked
    code alone cannot join a different account)."""

    __tablename__ = "workspace_invites"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="member")
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    invited_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Audit(Base):
    __tablename__ = "audits"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # O-0 (R-ORG): the owning workspace. Backfilled 1:1 from the user's
    # workspace and set on creation. Plain String(32), no FK — additive-safe on
    # both backends (the source_id convention). Reads stay user_id-scoped in O-0
    # (correct while 1 user = 1 workspace); O-1 re-scopes reads to workspace_id.
    workspace_id: Mapped[str | None] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    provider_mix: Mapped[str | None] = mapped_column(String(200))
    row_count: Mapped[int | None] = mapped_column(Integer)
    # v1.5: distinct UTC days the audit covered — R-Q9 needs it to gate
    # verified savings on a post-application audit of >= 7 days.
    observed_days: Mapped[int | None] = mapped_column(Integer)
    valid_pct: Mapped[float | None] = mapped_column(Float)
    total_spend_usd: Mapped[float | None] = mapped_column(Float)
    projected_spend_usd: Mapped[float | None] = mapped_column(Float)
    savings_pct: Mapped[float | None] = mapped_column(Float)
    # FR-30: metered-API billing could not be assumed for this audit's
    # traffic, so any figure derived from it carries the equiv-spend line.
    equiv_spend: Mapped[bool | None] = mapped_column(Boolean)
    paid_via: Mapped[str | None] = mapped_column(String(32))
    # R-MULTI-SOURCE (migration 013): which connected account produced this
    # audit; NULL for uploads and for connected audits that ran before
    # attribution shipped. Plain string, no FK — sources are soft-deleted
    # (revoked, never dropped), so integrity is by convention and the column
    # stays trivially additive on both backends.
    source_id: Mapped[str | None] = mapped_column(String(32), index=True)
    error: Mapped[str | None] = mapped_column(Text)  # user-safe message only (LLD §8)
    upload_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    report_ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FindingRow(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_id: Mapped[str] = mapped_column(
        ForeignKey("audits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    finding_id: Mapped[str] = mapped_column(String(16), nullable=False)
    detector: Mapped[str] = mapped_column(String(32), nullable=False)
    # v1.5 R-Q9: the route this finding is about (model id when the detector
    # names one). Route identity is what a re-audit must reproduce before
    # any saving is called verified.
    route: Mapped[str | None] = mapped_column(String(120))
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    monthly_impact_usd: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    fix_text: Mapped[str] = mapped_column(Text, nullable=False)
    # ≤20 items, counts/metadata only (FR-22)
    evidence_sample: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)


class CallAggregate(Base):
    __tablename__ = "call_aggregates"  # aggregates only, FR-22

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_id: Mapped[str] = mapped_column(
        ForeignKey("audits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day: Mapped[object] = mapped_column(Date, nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    calls: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cached_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cost_usd: Mapped[float | None] = mapped_column(Float)


class AuditLogEntry(Base):
    __tablename__ = "audit_log"  # append-only

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[str] = mapped_column(String(120), nullable=False)
    detail: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # NOTE: no workspace_id here — billing visibility is role-gated in O-2
    # (founder ruling 2026-07-24), so the payment ledger stays user-scoped and
    # its workspace column lands with O-2, not O-1b.
    provider: Mapped[str] = mapped_column(String(24), nullable=False)  # razorpay|stripe|manual|comp
    ref: Mapped[str | None] = mapped_column(String(120))  # provider payment reference
    amount: Mapped[float] = mapped_column(Float, nullable=False)  # major units
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="paid")
    # one payment = one audit credit (accepted default Q8): set when consumed
    audit_id: Mapped[str | None] = mapped_column(ForeignKey("audits.id", ondelete="SET NULL"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # At most ONE signup comp credit per user (readiness audit 2026-07-22):
    # partial unique index so a concurrent first-login can't double-grant the
    # free meter. Real paid rows are unconstrained. Migration 009 mirrors this.
    __table_args__ = (
        Index(
            "uq_payments_one_comp_per_user",
            "user_id",
            unique=True,
            sqlite_where=text("provider = 'comp'"),
            postgresql_where=text("provider = 'comp'"),
        ),
    )


class WebhookEvent(Base):
    __tablename__ = "webhook_events"  # FR-27: append-only processed-event dedup

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    detail: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),)


class WebhookEndpoint(Base):
    """R-PLATFORM slice 3 (S-5): a workspace-registered outbound delivery
    target. `secret` signs every `audit.completed` POST (HMAC-SHA256) — unlike
    a credential we only ever verify (ApiToken/IngestKey token_hash), WE must
    hold this material to sign each delivery, so it is stored plaintext, never
    logged or re-rendered after creation. Revoke NULLs the secret and flips
    `active` (authority law), keeping the row so WebhookDelivery history
    survives removal."""

    __tablename__ = "webhook_endpoints"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    secret: Mapped[str | None] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebhookDelivery(Base):
    """R-PLATFORM slice 3: one best-effort delivery attempt (no durable retry
    queue — a later SCALING slice), so the UI can show recent status honestly."""

    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    endpoint_id: Mapped[str] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event: Mapped[str] = mapped_column(String(40), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)  # None = request never completed
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"  # FR-26; purged with upload lifecycle

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    audit_id: Mapped[str] = mapped_column(
        ForeignKey("audits.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_idem_user_key"),)


# ---- v1.5 MONITOR (PLAN-V15 V-D1; migrations additive-only) ----


class Source(Base):
    __tablename__ = "sources"  # T2 ACCOUNT connections (R-CONNECT / PLAN-V15 §0 R-Q5)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(String(32), index=True)  # O-0 (R-ORG)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)  # openai|anthropic
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    # Fernet token (HKDF from SECRET_KEY). Decrypted ONLY in the pull path;
    # revoke deletes this value. Never logged, never in repr (T-KEY-03).
    credentials_encrypted: Mapped[str | None] = mapped_column(Text)
    # R-MULTI-SOURCE: keyed one-way HMAC of the API key — blocks connecting
    # the SAME key twice (double-counting) while allowing another account of
    # the same provider. NULL on pre-013 rows until the next pull backfills.
    key_fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    # active | paused (downgrade, oldest-first — R-Q6) | revoked
    schedule: Mapped[str] = mapped_column(String(16), default="daily")  # pull cadence
    last_pull_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_audit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceUsage(Base):
    __tablename__ = "source_usage"  # T2 pulled aggregates — counts only (FR-22 tier law)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day: Mapped[object] = mapped_column(Date, nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    calls: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cached_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cost_usd: Mapped[float | None] = mapped_column(Float)  # provider-reported when present
    # docs/12 Stage-1 contract: pull id, endpoint, dedup stats — metadata only
    provenance: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (UniqueConstraint("source_id", "day", "model", name="uq_source_usage_bucket"),)


class SavedView(Base):
    __tablename__ = "saved_views"  # FR-32 C3 (R-PROCEED 2026-07-23): named filter sets

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(String(32), index=True)  # O-0 (R-ORG)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    # Canonical re-serialization of parse_filters output — NEVER the raw
    # querystring, so a stored view can only contain whitelisted filter keys.
    params: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_saved_view_user_name"),)


class StageEvent(Base):
    __tablename__ = "stage_events"  # WP-PIPELINE-UI: real per-stage timings

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_id: Mapped[str] = mapped_column(
        ForeignKey("audits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(24), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # counts/ids only (FR-22): rows, rejected, priced, unpriced models,
    # per-detector finding counts INCLUDING honest zeros
    detail: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)


class PullEvent(Base):
    __tablename__ = "pull_events"  # WP-PIPELINE-UI: every pull, incl. failures

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    buckets_in: Mapped[int] = mapped_column(Integer, default=0)
    upserted: Mapped[int] = mapped_column(Integer, default=0)  # new rows
    updated: Mapped[int] = mapped_column(Integer, default=0)  # latest-wins rewrites
    error: Mapped[str | None] = mapped_column(String(300))  # user-safe words only


class AlertCheck(Base):
    __tablename__ = "alert_checks"  # WP-PIPELINE-UI: silence you can verify

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(String(32), index=True)  # O-1b (R-ORG)
    rule: Mapped[str] = mapped_column(String(32), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    crossed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    note: Mapped[str] = mapped_column(String(200), nullable=False, default="")


class LinkCode(Base):
    __tablename__ = "link_codes"  # WP-CC-LINK: short-lived, one-shot, hashed

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IngestKey(Base):
    __tablename__ = "ingest_keys"  # S-0 (R-SDK-PLATFORM): the paste-able DSN

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(String(32), index=True)  # O-0 (R-ORG)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    # Keyed one-way HMAC of the ingest key (credential_fingerprint context).
    # The plaintext lives only in the customer's environment. NULL after
    # revoke: key material DELETED, row kept for audit attribution
    # (authority-law parity with devices and sources).
    key_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # R-PLATFORM slice 5: usage VISIBILITY, not enforcement (X-01/X-02 unchanged
    # — never gates traffic). One cheap UPDATE per request alongside
    # last_used_at; no per-day bucket table this slice (see routes_ingest /
    # api_auth for the best-effort write that can never fail the API call).
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ApiToken(Base):
    __tablename__ = "api_tokens"  # S-6 (R-SDK-PLATFORM): personal READ-scoped token

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(String(32), index=True)  # O-0 (R-ORG)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    # Keyed one-way HMAC of the token (credential_fingerprint) — parity with
    # ingest keys and devices. NULL after revoke: material DELETED, row kept
    # for audit attribution. This credential is READ-only by construction:
    # the read endpoints are the ONLY thing it authenticates.
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    # Space-free CSV of granted read scopes (api_scopes.READ_SCOPES). A token
    # NEVER carries a write scope — ingest stays the write-only ik_ path.
    scopes: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # R-PLATFORM slice 5: request count alongside last_used_at — see IngestKey.
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class OAuthApp(Base):
    __tablename__ = "oauth_apps"  # S-6: a third-party app a customer registers

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(String(32), index=True)  # O-0 (R-ORG)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    # Public identifier (oac_…); safe to embed in an authorize URL.
    client_id: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    # Keyed HMAC of the confidential secret (oas_…). NULL after revoke.
    client_secret_hash: Mapped[str | None] = mapped_column(String(64))
    # Newline-separated EXACT redirect URIs. Authorization only ever redirects
    # to a byte-exact member of this set (no prefix/substring match) — the
    # open-redirect guard.
    redirect_uris: Mapped[str] = mapped_column(Text, nullable=False)
    # The ceiling of scopes this app may ever request (CSV). The user consents
    # to a subset of THIS, which is itself a subset of READ_SCOPES.
    scopes: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OAuthAuthCode(Base):
    __tablename__ = "oauth_auth_codes"  # S-6: single-use, short-TTL auth code

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    app_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_apps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The resource owner who approved. Their audits are what the token reads.
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    # PKCE (RFC 7636): the S256 challenge; the token exchange proves knowledge
    # of the verifier. Required for every app — public-client-safe by default.
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Set the instant the code is redeemed — a second redemption is refused.
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OAuthAccessToken(Base):
    __tablename__ = "oauth_access_tokens"  # S-6: issued READ-scoped access token

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    app_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_apps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Keyed HMAC of the at_… token. Revocation is at the APP level
    # (OAuthApp.revoked_at kills every token it issued); there is no per-token
    # revoke, so no revoked_at column here — the resolver rejects tokens of a
    # revoked app. The nullable/unique hash mirrors the other credential tables.
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    scopes: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Device(Base):
    __tablename__ = "devices"  # WP-CC-LINK: linked Claude Code machines

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(String(32), index=True)  # O-0 (R-ORG)
    hostname: Mapped[str] = mapped_column(String(120), nullable=False)
    # Keyed one-way HMAC of the device token (crypto.credential_fingerprint
    # context) — the plaintext exists only in the customer's config file.
    # NULL after revoke: the key material is DELETED, the row keeps its
    # identity for audit attribution (authority-law parity with sources).
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    # R-CC-LINK 2: the recorded moment a human read the consent text and agreed.
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_ship_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FindingFeedback(Base):
    __tablename__ = "finding_feedback"  # L0 labeling pipeline (docs/12 Stage 3)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_id: Mapped[str] = mapped_column(
        ForeignKey("audits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    finding_id: Mapped[str] = mapped_column(String(16), nullable=False)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    # applied | dismissed | not_relevant
    # Customer-reported figure; shown separately, NEVER in the verified headline (R-Q9)
    savings_realized_usd: Mapped[float | None] = mapped_column(Float)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("audit_id", "finding_id", name="uq_feedback_finding"),)


class AlertRule(Base):
    __tablename__ = "alert_rules"  # WP-3 observe-and-alert ONLY (X-02 stands)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(String(32), index=True)  # O-0 (R-ORG)
    rule: Mapped[str] = mapped_column(String(32), nullable=False)
    # spend_spike_dod | waste_above_target | new_high_finding | soft_budget
    threshold: Mapped[float | None] = mapped_column(Float)  # semantics per rule
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("user_id", "rule", name="uq_alert_user_rule"),)


class AlertEvent(Base):
    __tablename__ = "alert_events"  # append-only fired-alert log

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(String(32), index=True)  # O-1b (R-ORG)
    rule: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"  # WP-6; one per account (R-Q11)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    workspace_id: Mapped[str | None] = mapped_column(String(32), index=True)  # O-0 (R-ORG)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)  # razorpay|stripe
    plan: Mapped[str] = mapped_column(String(16), nullable=False, default="free")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    # active | past_due (day 0-6) | read_only (day 7-20) | cancelled (day 21 → Free)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    external_ref: Mapped[str | None] = mapped_column(String(200))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # dunning anchor
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Statement(Base):
    __tablename__ = "statements"  # WP-4 Savings Statement archive

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(String(32), index=True)  # O-0 (R-ORG)
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    # The number leads the subject (R-DESIGN §4e); stored so a resend
    # delivers the same artifact rather than re-deriving it.
    subject: Mapped[str | None] = mapped_column(String(300))
    body_text: Mapped[str] = mapped_column(Text, nullable=False)  # dollars/counts only
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("user_id", "period", name="uq_statement_period"),)
