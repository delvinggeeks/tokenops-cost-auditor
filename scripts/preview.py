"""Founder preview: one command to a working v1.5 dashboard in the browser.

    make preview     (or: uv run python scripts/preview.py)

Starts the real application against a THROWAWAY local database seeded with
fixture data, and prints a sign-in link. Nothing here touches production:
the database, uploads and reports all live under .preview/, which is
gitignored and safe to delete.

The seed is deliberately a realistic mid-flight account — a connected
source, two audits a fortnight apart, a fix applied and then PROVED by the
later audit (so the verified headline is non-zero and honest), findings
still open, an armed alert, and last month's statement. Empty-state screens
are reachable by deleting .preview/ and passing --empty.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import uvicorn
from sqlalchemy import select

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import (
    AlertRule,
    Audit,
    Base,
    CallAggregate,
    FindingFeedback,
    FindingRow,
    Source,
    Subscription,
    User,
)
from tokenops_cost_auditor.services.connectors.crypto import encrypt_credential
from tokenops_cost_auditor.services.statements import build as statements
from tokenops_cost_auditor.web.auth import issue_magic_token

PREVIEW_DIR = Path(".preview")
EMAIL = "founder@tokenops-cost-auditor.com"
HOST, PORT = "127.0.0.1", 8000

FINDINGS = [
    # (finding_id, detector, route, severity, monthly_usd, fix_text)
    (
        "D2-001",
        "d2_missing_cache",
        "claude-sonnet-5",
        "high",
        1120.10,
        '"system": [{"type": "text", "text": SYSTEM_PROMPT,\n'
        '            "cache_control": {"type": "ephemeral"}}]',
    ),
    (
        "D1-002",
        "d1_oversized_model",
        "claude-opus-4-8",
        "med",
        688.75,
        'model="claude-sonnet-5"  # was claude-opus-4-8',
    ),
    (
        "D3-003",
        "d3_prompt_bloat",
        "gpt-5.6-sol",
        "med",
        512.40,
        "trim the accumulated few-shot examples from the support route",
    ),
    (
        "D6-004",
        "d6_chatty_loop",
        "claude-haiku-4-5-20251001",
        "low",
        164.05,
        "batch the loop's per-item calls into groups of 5",
    ),
]


def seed(settings: Settings, empty: bool) -> str:
    from tokenops_cost_auditor.persistence.repo import make_engine, make_session_factory

    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as session:
        if session.execute(select(User).where(User.email == EMAIL)).scalar_one_or_none():
            return EMAIL  # already seeded — re-running is safe

        user = User(email=EMAIL)
        session.add(user)
        session.flush()
        if empty:
            session.commit()
            return EMAIL

        session.add(Subscription(user_id=user.id, provider="stripe", plan="pro", currency="USD"))
        now = datetime.now(UTC)
        first, second = now - timedelta(days=21), now - timedelta(days=2)

        session.add(
            Source(
                user_id=user.id,
                provider="openai",
                label="production org",
                credentials_encrypted=encrypt_credential(settings.secret_key, "sk-preview"),
                last_pull_at=now - timedelta(hours=3),
                last_audit_at=second,
            )
        )

        # First audit: the baseline, with everything still open.
        a1 = Audit(
            user_id=user.id,
            status="done",
            created_at=first,
            report_ready_at=first,
            observed_days=30,
            row_count=1_243_000,
            total_spend_usd=8912.55,
            savings_pct=27.4,
            valid_pct=99.1,
            provider_mix="openai,anthropic",
            paid_via="subscription",
        )
        session.add(a1)
        session.flush()
        for fid, det, route, sev, usd, fix in FINDINGS:
            session.add(
                FindingRow(
                    audit_id=a1.id,
                    finding_id=fid,
                    detector=det,
                    route=route,
                    severity=sev,
                    monthly_impact_usd=usd,
                    confidence="estimated",
                    fix_text=fix,
                    evidence_sample=[
                        {
                            "row_idx": i,
                            "ts": f"{(first).date()}T09:1{i}:02Z",
                            "model": route,
                            "tokens": 28412 - i * 17,
                            "note": "uncached",
                        }
                        for i in range(3)
                    ],
                )
            )
        # The customer applied the cache fix the day after that audit.
        session.add(
            FindingFeedback(
                audit_id=a1.id,
                finding_id="D2-001",
                verdict="applied",
                actor=EMAIL,
                ts=first + timedelta(days=1),
            )
        )

        # Second audit PROVES it: the same route now costs far less, so the
        # verified headline is real rather than a projection (R-Q9).
        a2 = Audit(
            user_id=user.id,
            status="done",
            created_at=second,
            report_ready_at=second,
            observed_days=30,
            row_count=1_301_400,
            total_spend_usd=7640.20,
            savings_pct=19.8,
            valid_pct=99.4,
            provider_mix="openai,anthropic",
            paid_via="subscription",
        )
        session.add(a2)
        session.flush()
        for fid, det, route, sev, usd, fix in FINDINGS:
            reduced = 180.00 if fid == "D2-001" else usd
            session.add(
                FindingRow(
                    audit_id=a2.id,
                    finding_id=fid,
                    detector=det,
                    route=route,
                    severity=sev,
                    monthly_impact_usd=reduced,
                    confidence="estimated",
                    fix_text=fix,
                    evidence_sample=[
                        {
                            "row_idx": 1,
                            "ts": f"{second.date()}T11:02:19Z",
                            "model": route,
                            "tokens": 24110,
                            "note": "sampled",
                        }
                    ],
                )
            )
        for day in range(14):
            d = (second - timedelta(days=13 - day)).date()
            for model, cost in (
                ("gpt-5.6-sol", 148.0 + day * 3.1),
                ("claude-sonnet-5", 96.5 + day * 1.4),
            ):
                session.add(
                    CallAggregate(
                        audit_id=a2.id,
                        day=d,
                        model=model,
                        calls=4200 + day * 60,
                        prompt_tokens=18_400_000,
                        completion_tokens=940_000,
                        cached_tokens=6_100_000,
                        cost_usd=cost,
                    )
                )

        session.add(
            AlertRule(user_id=user.id, rule="waste_above_target", threshold=25.0, enabled=True)
        )
        session.add(
            AlertRule(user_id=user.id, rule="spend_spike_dod", threshold=30.0, enabled=True)
        )
        session.commit()

        # Last month's statement, archived and readable.
        last = second.replace(day=1) - timedelta(days=1)
        doc = statements.build(session, user, last.year, last.month)
        statements.archive(session, user, doc)
        session.commit()
    return EMAIL


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--empty", action="store_true", help="seed an empty account instead")
    ap.add_argument("--reset", action="store_true", help="delete .preview/ first")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()

    if args.reset and PREVIEW_DIR.exists():
        shutil.rmtree(PREVIEW_DIR)
    PREVIEW_DIR.mkdir(exist_ok=True)

    settings = Settings(
        app_env="dev",
        secret_key="preview-only-secret-" + "p" * 44,
        database_url=f"sqlite:///{PREVIEW_DIR / 'preview.db'}",
        upload_dir=PREVIEW_DIR / "uploads",
        report_dir=PREVIEW_DIR / "reports",
        backup_dir=PREVIEW_DIR / "backups",
        app_base_url=f"http://{HOST}:{args.port}",
        _env_file=None,  # never read the deployed .env
    )
    email = seed(settings, empty=args.empty)
    token = issue_magic_token(settings.secret_key, email)
    link = f"http://{HOST}:{args.port}/auth/verify?token={token}"

    print("\n" + "=" * 72)
    print("  TokenOps Cost Auditor — v1.5 preview (local, throwaway data)")
    print("=" * 72)
    print(f"\n  SIGN IN (click or paste — this is your magic link):\n\n    {link}\n")
    print(f"  Then the dashboard is at:   http://{HOST}:{args.port}/dashboard")
    print("\n  Worth clicking:")
    print(f"    Findings      http://{HOST}:{args.port}/findings   (row -> drawer)")
    print(f"    Alerts        http://{HOST}:{args.port}/alerts")
    print(f"    Statements    http://{HOST}:{args.port}/statements")
    print(f"    Settings      http://{HOST}:{args.port}/settings")
    print(f"    Billing       http://{HOST}:{args.port}/billing")
    print(f"    Guide         http://{HOST}:{args.port}/guide")
    print("\n  The guided tour appears on first load of the dashboard.")
    print("  Data lives in .preview/ — delete it or pass --reset to start over.")
    print("  Ctrl-C to stop.\n")

    app = __import__("tokenops_cost_auditor.main", fromlist=["create_app"]).create_app(settings)
    uvicorn.run(app, host=HOST, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
