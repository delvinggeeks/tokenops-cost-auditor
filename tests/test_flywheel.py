"""M-FLY-0 — T-FLY-01..06: training-frame contract (A1) + cohort ledger (A2).

The laws under test:
- FR-22 as executable schema: FRAME_COLUMNS is the frame, every str field
  enum/id-shaped, a free-text column cannot ship (T-FLY-02).
- R-F1-SIGNOFF: benchmark_sharing=False means excluded from the first byte —
  the frame AND every rung count (T-FLY-04).
- Honesty Law: rungs live only at config thresholds, boundaries exact
  (T-FLY-05); customers see no countdown — founder surfaces only (T-FLY-06).
- Determinism + keyed pseudonymity (T-FLY-01/03).
- NFR-01 posture: the flywheel package imports no network, no rules, no
  pricing (T-FLY-07 source guard).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import select

from tokenops_cost_auditor.persistence.models import (
    Audit,
    FindingFeedback,
    FindingRow,
    User,
)
from tokenops_cost_auditor.services.flywheel import cohort, frame

SECRET = "s" * 64


def seed_customer(
    app: FastAPI,
    email: str,
    *,
    sharing: bool | None = None,
    findings: int = 1,
    verdict: str | None = None,
    savings: float | None = None,
    when: datetime | None = None,
    paid_via: str | None = None,
) -> str:
    with app.state.session_factory() as session:
        user = User(email=email, benchmark_sharing=sharing)
        session.add(user)
        session.flush()
        audit = Audit(
            user_id=user.id,
            status="done",
            row_count=100,
            observed_days=10,
            total_spend_usd=10.0,
            paid_via=paid_via,
            created_at=when or datetime.now(UTC),
            report_ready_at=when or datetime.now(UTC),
        )
        session.add(audit)
        session.flush()
        for i in range(findings):
            session.add(
                FindingRow(
                    audit_id=audit.id,
                    finding_id=f"D2-{i:03d}",
                    detector="d2_missing_cache",
                    route="claude-sonnet-5",
                    severity="high",
                    monthly_impact_usd=50.0,
                    confidence="estimated",
                    fix_text="cache it",
                    evidence_sample=[{"row_idx": 1, "tokens": 10}],
                )
            )
        if verdict is not None:
            session.add(
                FindingFeedback(
                    audit_id=audit.id,
                    finding_id="D2-000",
                    verdict=verdict,
                    savings_realized_usd=savings,
                    actor=email,
                )
            )
        session.commit()
        return user.id


class TestFrame:
    def test_01_extract_is_deterministic(self, app: FastAPI) -> None:
        seed_customer(app, "a@x.com", verdict="applied", savings=80.0)
        seed_customer(app, "b@x.com", findings=2, paid_via="subscription")
        with app.state.session_factory() as session:
            one = frame.extract(session, SECRET)
            two = frame.extract(session, SECRET)
        assert one == two and len(one) == 3

    def test_02_schema_allowlist_is_law(self) -> None:
        """T-FLY-02: names the offender when the contract is broken."""
        assert frame.schema_violations() == []
        assert set(frame.ENUM_OR_ID_FIELDS) <= set(frame.FRAME_COLUMNS)

    def test_03_pseudonym_is_keyed_stable_one_way(self, app: FastAPI) -> None:
        uid = seed_customer(app, "a@x.com")
        p1 = frame.cohort_pseudonym(SECRET, uid)
        assert p1 == frame.cohort_pseudonym(SECRET, uid)  # stable
        assert uid not in p1 and "a@x.com" not in p1  # one-way, no identity leak
        assert p1 != frame.cohort_pseudonym("t" * 64, uid)  # keyed
        with app.state.session_factory() as session:
            rows = frame.extract(session, SECRET)
        assert rows and all(r.customer == p1 for r in rows)

    def test_04_excluded_accounts_never_enter(self, app: FastAPI) -> None:
        """R-F1: the column contract, enforced at the source."""
        seed_customer(app, "in@x.com")
        out_id = seed_customer(app, "out@x.com", sharing=False)
        with app.state.session_factory() as session:
            rows = frame.extract(session, SECRET)
            status = cohort.status(session, app.state.settings)
        out_pseudonym = frame.cohort_pseudonym(SECRET, out_id)
        assert rows and all(r.customer != out_pseudonym for r in rows)
        assert status.customers_with_audit == 1  # excluded counts toward NO rung

    def test_05_verdict_and_savings_are_passthrough_labels(self, app: FastAPI) -> None:
        seed_customer(app, "a@x.com", verdict="applied", savings=80.0)
        with app.state.session_factory() as session:
            row = frame.extract(session, SECRET)[0]
        assert row.verdict == "applied"
        assert row.savings_realized_usd == 80.0  # customer-reported, carried as-is
        assert row.tier == "upload"


class TestCohort:
    def test_06_rung_boundaries_are_exact(self, app: FastAPI) -> None:
        """T-FLY-05: 9 ≠ 10 — the Honesty Law lives at the boundary."""
        for i in range(9):
            seed_customer(app, f"u{i}@x.com")
        with app.state.session_factory() as session:
            s9 = cohort.status(session, app.state.settings)
        assert not s9.rungs[0].live and "needs 1 more" in s9.rungs[0].note
        seed_customer(app, "u9@x.com")
        with app.state.session_factory() as session:
            s10 = cohort.status(session, app.state.settings)
        assert s10.rungs[0].live and s10.rungs[0].note == "LIVE"
        assert not s10.rungs[1].live  # L2 keys on LABELED customers (0 here)

    def test_07_l3_needs_customers_and_months(self, app: FastAPI) -> None:
        old = datetime.now(UTC) - timedelta(days=200)
        for i in range(50):
            seed_customer(app, f"u{i}@x.com", when=old if i == 0 else None)
        with app.state.session_factory() as session:
            s = cohort.status(session, app.state.settings)
        assert s.customers_with_audit == 50
        assert s.history_months >= 6
        assert s.rungs[2].live

    def test_08_founder_surfaces_only(self, app: FastAPI) -> None:
        """The digest line renders; no customer surface mentions the cohort
        countdown (zero-state law — grep the app templates)."""
        seed_customer(app, "a@x.com")
        with app.state.session_factory() as session:
            line = cohort.status(session, app.state.settings).digest_line()
        assert re.match(r"Flywheel: 1 audited / 0 labeled", line)
        assert "dormant" in line
        templates = Path("src/tokenops_cost_auditor/web/templates/app")
        for tpl in templates.rglob("*.html"):
            assert "Flywheel:" not in tpl.read_text(), f"{tpl} leaks the founder ledger"


class TestPackagePosture:
    def test_09_flywheel_imports_no_engine_or_network(self) -> None:
        """T-FLY-07: R-F4 — the guard never meets an ML lib, the engine never
        meets the flywheel. Source-level, same spirit as T-NFR-01."""
        pkg = Path("src/tokenops_cost_auditor/services/flywheel")
        banned = re.compile(
            r"^\s*(from|import)\s+(requests|httpx|urllib|openai|anthropic|sklearn|"
            r"tokenops_cost_auditor\.services\.(rules|pricing|connectors))",
            re.M,
        )
        for mod in pkg.glob("*.py"):
            hit = banned.search(mod.read_text())
            assert hit is None, f"{mod.name}: {hit.group(0)!r}"

    def test_10_thresholds_are_config_driven_not_hardcoded(self, app: FastAPI) -> None:
        """vv f.3 mutation guard: a rung hard-coding its threshold dies here —
        the SAME data flips rungs when the config value changes."""
        from tokenops_cost_auditor.config import Settings

        for i in range(3):
            seed_customer(app, f"u{i}@x.com", verdict="applied")
        tiny = Settings(
            app_env="test",
            secret_key=SECRET,
            database_url="sqlite://",
            flywheel_l1_min_customers=3,
            flywheel_l2_min_customers=3,
            flywheel_l3_min_customers=3,
            flywheel_l3_min_history_months=0,
            _env_file=None,
        )
        with app.state.session_factory() as session:
            default = cohort.status(session, app.state.settings)
            custom = cohort.status(session, tiny)
        assert not any(r.live for r in default.rungs)  # 3 < 10/25/50
        assert all(r.live for r in custom.rungs)  # same data, config decides

    def test_11_l2_boundary_is_exact(self, app: FastAPI) -> None:
        """vv f.4 / PLAN-FLYWHEEL AC: 24 labeled ≠ 25 labeled."""
        for i in range(24):
            seed_customer(app, f"u{i}@x.com", verdict="applied")
        with app.state.session_factory() as session:
            s24 = cohort.status(session, app.state.settings)
        assert not s24.rungs[1].live and "needs 1 more" in s24.rungs[1].note
        seed_customer(app, "u24@x.com", verdict="dismissed")  # any L0 verdict labels
        with app.state.session_factory() as session:
            s25 = cohort.status(session, app.state.settings)
        assert s25.rungs[1].live

    def test_12_founder_surfaces_actually_render(self, app: FastAPI) -> None:
        """vv f.6: the digest line and admin row are shipped surfaces, not
        just a formatting function — render both for real."""
        import sys
        from pathlib import Path as P

        sys.path.insert(0, str(P("scripts").resolve()))
        seed_customer(app, "a@x.com")
        import importlib.util

        spec = importlib.util.spec_from_file_location("daily_digest", P("scripts/daily_digest.py"))
        assert spec is not None and spec.loader is not None
        digest_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(digest_mod)
        with app.state.session_factory() as session:
            body = digest_mod.build_digest(session, app.state.settings)
        assert "Flywheel: 1 audited / 0 labeled" in body
        # admin row: token-gate the fixture app, then fetch the panel
        from fastapi.testclient import TestClient

        app.state.settings.admin_token = "test-admin-token"
        page = TestClient(app).get("/admin", headers={"X-Admin-Token": "test-admin-token"})
        assert page.status_code == 200
        assert "Flywheel: 1 audited" in page.text


class TestBenchmarks:
    """M-FLY-1 B1 — golden percentile method, leakage law, honest dormancy."""

    GOLDEN = (2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35)  # NOTES derivation

    def _seed_cohort(self, app: FastAPI, values: tuple[int, ...]) -> list[str]:
        ids = []
        for i, v in enumerate(values):
            uid = seed_customer(app, f"c{i}@x.com")
            with app.state.session_factory() as session:
                audit = session.execute(select(Audit).where(Audit.user_id == uid)).scalar_one()
                audit.savings_pct = float(v)
                session.commit()
            ids.append(uid)
        return ids

    def test_13_golden_percentiles(self, app: FastAPI) -> None:
        """Pins the NOTES-sheet derivation exactly (founder-verification row)."""
        from tokenops_cost_auditor.services.flywheel import benchmarks as bench

        ids = self._seed_cohort(app, self.GOLDEN)
        with app.state.session_factory() as session:
            expect = {0: 8, 4: 42, 6: 58, 11: 100}  # index in GOLDEN -> percentile
            for idx, want in expect.items():
                b = bench.waste_percentile(session, app.state.settings, ids[idx])
                assert b.live and b.n == 12
                assert b.percentile == want, f"v={self.GOLDEN[idx]}: {b.percentile} != {want}"

    def test_14_dormant_below_threshold_and_absent_on_dashboard(self, app: FastAPI) -> None:
        from fastapi.testclient import TestClient

        from tokenops_cost_auditor.services.flywheel import benchmarks as bench

        ids = self._seed_cohort(app, self.GOLDEN[:9])  # 9 < 10
        with app.state.session_factory() as session:
            b = bench.waste_percentile(session, app.state.settings, ids[0])
        assert not b.live and b.percentile is None
        page = TestClient(app).get("/dashboard", headers={"X-User-Email": "c0@x.com"})
        assert "How you compare" not in page.text  # absence, never a countdown

    def test_15_live_widget_prints_population_and_leaks_nothing(self, app: FastAPI) -> None:
        """Honesty + leakage laws on the RENDERED surface: own rank + n only —
        no other company's waste value appears anywhere in the HTML."""
        from fastapi.testclient import TestClient

        self._seed_cohort(app, self.GOLDEN)
        page = TestClient(app).get("/dashboard", headers={"X-User-Email": "c4@x.com"})
        html = re.sub(r"\s+", " ", page.text)
        assert "42nd percentile" in html
        assert "based on 12 companies" in html
        assert "leaner than 58% of companies" in html
        # leakage: no cohort member's absolute waste share renders (own = 14)
        for v in [x for x in self.GOLDEN if x != 14]:
            assert f"{v}.0%" not in html and f"waste {v}" not in html

    def test_16_opted_out_customer_is_out_of_cohort_and_unranked(self, app: FastAPI) -> None:
        from tokenops_cost_auditor.services.flywheel import benchmarks as bench

        ids = self._seed_cohort(app, self.GOLDEN)
        with app.state.session_factory() as session:
            user = session.get(User, ids[0])
            assert user is not None
            user.benchmark_sharing = False
            session.commit()
        with app.state.session_factory() as session:
            own = bench.waste_percentile(session, app.state.settings, ids[0])
            other = bench.waste_percentile(session, app.state.settings, ids[4])
        assert not own.live  # no rank for the opted-out account
        assert other.n == 11  # and its value left the pool entirely
