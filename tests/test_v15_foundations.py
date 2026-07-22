"""PLAN-V15 V-D1 foundations: key encryption (T-KEY-01..03), additive-only
migration guard (T-V15-MIG-01), new-model schema sanity."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tokenops_cost_auditor.persistence.models import (
    AlertRule,
    Base,
    FindingFeedback,
    Source,
    SourceUsage,
    Statement,
    Subscription,
    User,
)
from tokenops_cost_auditor.services.connectors.crypto import (
    CredentialError,
    decrypt_credential,
    encrypt_credential,
)

SECRET = "a" * 64
MIGRATION = next(
    Path("src/tokenops_cost_auditor/persistence/migrations/versions").glob("*003_v15*")
)


class TestKeyEncryption:
    def test_01_roundtrip(self) -> None:
        token = encrypt_credential(SECRET, "sk-admin-abc123")
        assert token != "sk-admin-abc123"
        assert "sk-admin" not in token  # ciphertext leaks nothing
        assert decrypt_credential(SECRET, token) == "sk-admin-abc123"

    def test_02_wrong_key_fails_user_safe(self) -> None:
        token = encrypt_credential(SECRET, "sk-admin-abc123")
        with pytest.raises(CredentialError) as exc:
            decrypt_credential("b" * 64, token)
        # user-safe message: never echoes ciphertext or plaintext
        assert "sk-admin" not in str(exc.value)
        assert token not in str(exc.value)

    def test_03_module_never_logs_and_model_repr_is_opaque(self) -> None:
        crypto_src = Path("src/tokenops_cost_auditor/services/connectors/crypto.py").read_text(
            encoding="utf-8"
        )
        assert not re.search(r"^\s*(import|from)\s+(logging|structlog)", crypto_src, re.M)
        # \b: a real print( call, not the credential_fingerprint( function name
        # (R-MULTI-SOURCE) — the guard's target is output, not the substring.
        assert not re.search(r"\bprint\(", crypto_src)
        src = Source(
            user_id="u1",
            provider="openai",
            label="Acme org",
            credentials_encrypted=encrypt_credential(SECRET, "sk-admin-abc123"),
        )
        assert "sk-admin" not in repr(src)
        assert "credentials" not in repr(src)


class TestMigrationAdditiveOnly:
    def test_01_upgrade_contains_no_destructive_ops(self) -> None:
        text = MIGRATION.read_text(encoding="utf-8")
        upgrade_body = text.split("def upgrade()")[1].split("def downgrade()")[0]
        for banned in ("drop_table", "drop_column", "alter_column", "drop_index"):
            assert banned not in upgrade_body, f"{banned} found in upgrade() — additive only"

    def test_02_revision_chain_head(self) -> None:
        text = MIGRATION.read_text(encoding="utf-8")
        assert re.search(r'down_revision.*=.*"b6f7e9711883"', text)


class TestNewModelsSchema:
    @pytest.fixture()
    def session(self, tmp_path: Path) -> Session:
        engine = create_engine(f"sqlite:///{tmp_path}/v15.db")
        Base.metadata.create_all(engine)
        return Session(engine)

    def test_01_source_usage_bucket_unique(self, session: Session) -> None:
        user = User(email="owner@example.com")
        session.add(user)
        session.flush()
        src = Source(user_id=user.id, provider="openai", label="org")
        session.add(src)
        session.flush()
        row = {
            "source_id": src.id,
            "day": date(2026, 7, 20),
            "model": "gpt-5.6-sol",
            "calls": 10,
            "prompt_tokens": 1000,
            "completion_tokens": 100,
            "cached_tokens": 0,
            "provenance": {"pull": "p1"},
        }
        session.add(SourceUsage(**row))
        session.commit()
        session.add(SourceUsage(**row))
        with pytest.raises(Exception, match=r"(?i)unique"):
            session.commit()

    def test_02_feedback_one_verdict_per_finding(self, session: Session) -> None:
        user = User(email="owner@example.com")
        session.add(user)
        session.flush()
        from tokenops_cost_auditor.persistence.models import Audit

        audit = Audit(user_id=user.id)
        session.add(audit)
        session.flush()
        session.add(
            FindingFeedback(audit_id=audit.id, finding_id="F1", verdict="applied", actor=user.email)
        )
        session.commit()
        session.add(
            FindingFeedback(
                audit_id=audit.id, finding_id="F1", verdict="dismissed", actor=user.email
            )
        )
        with pytest.raises(Exception, match=r"(?i)unique"):
            session.commit()

    def test_03_one_subscription_per_account(self, session: Session) -> None:
        user = User(email="owner@example.com")
        session.add(user)
        session.flush()
        session.add(Subscription(user_id=user.id, provider="stripe", plan="pro"))
        session.commit()
        session.add(Subscription(user_id=user.id, provider="razorpay", plan="team"))
        with pytest.raises(Exception, match=r"(?i)unique"):
            session.commit()

    def test_04_alert_rule_and_statement_uniques(self, session: Session) -> None:
        user = User(email="owner@example.com")
        session.add(user)
        session.flush()
        session.add(AlertRule(user_id=user.id, rule="spend_spike_dod", threshold=30.0))
        session.add(Statement(user_id=user.id, period="2026-07", body_text="x"))
        session.commit()
        session.add(AlertRule(user_id=user.id, rule="spend_spike_dod", threshold=50.0))
        with pytest.raises(Exception, match=r"(?i)unique"):
            session.commit()
