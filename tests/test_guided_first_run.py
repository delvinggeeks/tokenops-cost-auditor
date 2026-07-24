"""Guided first run (#4) + output preview (#5) — founder walkthrough punch-list.

Walks the WHOLE first-run journey as a brand-new signed-in user (R-VERTICAL,
ship=walk): they land with no source and no audit and must (a) be GUIDED to
their first audit and (b) see a PREVIEW of real sample-engine output — fenced
HARD as SAMPLE so it can never read as their own figures (the data-coherence
honesty law, founder 2026-07-24) — and the moment a real audit completes the
guided surface + preview are GONE and the live widgets take over. Every preview
figure is the real engine's output (metrics.first_run_preview), never invented;
the expected values are read from that same function so the tests can never
assert a fiction.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from markupsafe import escape

from tokenops_cost_auditor.persistence.models import Audit, FindingRow, User, utcnow
from tokenops_cost_auditor.services.dashboard import metrics
from tokenops_cost_auditor.web import help as help_registry

USER = "firstrun@example.com"
HDR = {"X-User-Email": USER}


def _page(app: FastAPI) -> str:
    """The dashboard HTML with whitespace collapsed — so an assertion is not
    defeated by the line breaks Jinja preserves inside a wrapped paragraph."""
    return " ".join(TestClient(app).get("/dashboard", headers=HDR).text.split())


def _rendered(text: str) -> str:
    """Plain text as it appears in the HTML: apostrophes are escaped to &#39;."""
    return str(escape(text))


def _seed_done_audit_with_finding(app: FastAPI) -> None:
    """A completed audit with a real finding → PAST the first-run state, so the
    guided hero + SAMPLE preview give way to the live widget grid showing the
    user's OWN numbers."""
    with app.state.session_factory() as s:
        u = User(email=USER)
        s.add(u)
        s.flush()
        audit = Audit(
            user_id=u.id,
            status="done",
            observed_days=7,
            total_spend_usd=1000.0,
            report_ready_at=utcnow(),
        )
        s.add(audit)
        s.flush()
        s.add(
            FindingRow(
                audit_id=audit.id,
                finding_id="D2-001",
                detector="d2_missing_cache",
                severity="high",
                monthly_impact_usd=120.0,
                confidence="estimated",
                fix_text="cache it",
                evidence_sample=[],
                route="chat",
            )
        )
        s.commit()


class TestGuidedFirstRun:
    def test_new_user_lands_in_the_guided_first_run(self, app: FastAPI) -> None:
        page = _page(app)
        # #4 the guided path: headline + the three steps + the step-1 marker
        assert "money hiding in your LLM spend" in page
        assert "Get your logs in" in page
        assert "YOU ARE HERE" in page
        # both next-actions are named (their routes are exercised below)
        assert "Upload a log file" in page and "Connect a source" in page

    def test_next_actions_are_reachable(self, app: FastAPI) -> None:
        # the guided CTAs point at LIVE 200 routes, not dead ends (reachability law)
        c = TestClient(app)
        assert c.get("/upload", headers=HDR).status_code == 200
        assert c.get("/sources", headers=HDR).status_code == 200
        assert c.get("/sample").status_code == 200  # the "full sample report" link

    def test_output_preview_shows_real_engine_sample(self, app: FastAPI) -> None:
        # expected values come from the SAME function the template renders from,
        # so this can never assert a fiction — only that they reach the page.
        prev = metrics.first_run_preview(app.state.settings, app.state.pricing_table)
        page = _page(app)
        assert f"${prev['monthly_savings_usd']:,.2f}" in page  # money is the hero
        assert f"{prev['savings_pct']:.1f}% of sample spend" in page
        # EVERY previewed finding's plain title (help registry, web layer) renders
        assert prev["findings"], "the sample must produce at least one finding"
        for f in prev["findings"]:
            assert _rendered(help_registry.detector_plain(f["detector"])) in page

    def test_preview_is_fenced_as_sample_and_never_reads_as_own(self, app: FastAPI) -> None:
        page = _page(app)
        # the honesty fence (data-coherence law): unmistakably SAMPLE
        assert "SAMPLE — NOT YOUR DATA" in page
        assert "nothing on this card is yours" in page
        # the user's OWN state stays honest: no fabricated zero headline, and the
        # topbar freshness says there is no data yet — the sample never overrides it
        assert "$0.00" not in page
        assert "No data yet" in page

    def test_preview_and_hero_vanish_once_a_real_audit_exists(self, app: FastAPI) -> None:
        _seed_done_audit_with_finding(app)
        page = _page(app)
        # the first-run surface is gone — the preview never sits beside real figures
        assert "money hiding in your LLM spend" not in page
        assert "SAMPLE — NOT YOUR DATA" not in page
        # the live widget grid is back, showing the user's OWN finding
        assert 'id="w-savings"' in page
        assert _rendered(help_registry.detector_plain("d2_missing_cache")) in page

    def test_preview_failure_degrades_to_the_hero_never_500(
        self, app: FastAPI, monkeypatch
    ) -> None:
        # The sample preview is non-critical: ANY failure building it (missing
        # fixtures, a fixture model off the rate card, a detector raising) must
        # degrade to the guided hero alone, never 500 the first-run dashboard
        # (cold/vv gate — the "never a 500" claim, now verified).
        def _boom(*_a: object, **_k: object) -> dict[str, object]:
            raise RuntimeError("sample engine exploded")

        monkeypatch.setattr(metrics, "first_run_preview", _boom)
        resp = TestClient(app).get("/dashboard", headers=HDR)
        assert resp.status_code == 200  # NOT a 500
        assert "money hiding in your LLM spend" in resp.text  # the guided hero still shows
        assert "SAMPLE — NOT YOUR DATA" not in resp.text  # only the preview card is dropped

    def test_sample_model_is_memoised(self, app: FastAPI) -> None:
        # One build per process — the same committed fixtures, deterministic; the
        # in-app preview must not re-run ingest→price→detect per first-run visit.
        from tokenops_cost_auditor.services.report import sample

        a = sample.sample_model(app.state.settings, app.state.pricing_table)
        b = sample.sample_model(app.state.settings, app.state.pricing_table)
        assert a is b
