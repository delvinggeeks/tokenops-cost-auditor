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
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
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


class Audit(Base):
    __tablename__ = "audits"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
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
    provider: Mapped[str] = mapped_column(String(24), nullable=False)  # razorpay|stripe|manual|comp
    ref: Mapped[str | None] = mapped_column(String(120))  # provider payment reference
    amount: Mapped[float] = mapped_column(Float, nullable=False)  # major units
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="paid")
    # one payment = one audit credit (accepted default Q8): set when consumed
    audit_id: Mapped[str | None] = mapped_column(ForeignKey("audits.id", ondelete="SET NULL"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"  # FR-27: append-only processed-event dedup

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    detail: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),)


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
    provider: Mapped[str] = mapped_column(String(24), nullable=False)  # openai|anthropic
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    # Fernet token (HKDF from SECRET_KEY). Decrypted ONLY in the pull path;
    # revoke deletes this value. Never logged, never in repr (T-KEY-03).
    credentials_encrypted: Mapped[str | None] = mapped_column(Text)
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
    rule: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"  # WP-6; one per account (R-Q11)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
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
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    # The number leads the subject (R-DESIGN §4e); stored so a resend
    # delivers the same artifact rather than re-deriving it.
    subject: Mapped[str | None] = mapped_column(String(300))
    body_text: Mapped[str] = mapped_column(Text, nullable=False)  # dollars/counts only
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("user_id", "period", name="uq_statement_period"),)
