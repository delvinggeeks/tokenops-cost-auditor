"""R-DESIGN-TOKENS-2 §5 — authority lives on the server.

(a) capabilities the plan lacks are OMITTED from the payload, (b) plan-locked
features render as honest upsells, (c) money-affecting actions ask first with
the consequence stated in words, (d) endpoints re-check authority server-side.

Why tests: every one of these fails silently. A form that renders for a plan
nothing watches looks finished; a data-confirm attribute with no handler looks
wired; a POST the UI hides but the server accepts is one curl away from being
found. Cross-user scoping is pinned in test_dashboard (test_05) and plan caps
on connect in test_sources_routes — not repeated here.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.persistence.models import AlertRule, Subscription, User
from tokenops_cost_auditor.web import i18n

TEMPLATES = Path(__file__).parents[1] / "src/tokenops_cost_auditor/web/templates"

# An ask may reference the catalogue (one consequence, one source) — resolve it
# to the words a customer actually reads before judging those words.
T_REF = re.compile(r"^\{\{\s*t\(\s*['\"]([a-z0-9_.]+)['\"]\s*\)\s*\}\}$")


def resolve_ask(raw: str) -> str:
    m = T_REF.match(raw.strip())
    return i18n.t(m.group(1)) if m else raw


EMAIL = "law@example.com"
HDR = {"X-User-Email": EMAIL}


def grant(app: FastAPI, plan: str) -> None:
    with app.state.session_factory() as session:
        user = session.execute(select(User).where(User.email == EMAIL)).scalar_one_or_none()
        if user is None:
            user = User(email=EMAIL)
            session.add(user)
            session.flush()
        session.add(Subscription(user_id=user.id, provider="stripe", plan=plan))
        session.commit()


class TestCapabilitiesAreOmittedNotDisabled:
    """§5a — the payload, not CSS, is where a missing capability lives."""

    def test_free_alerts_page_has_no_rules_form(self, app: FastAPI) -> None:
        page = TestClient(app).get("/alerts", headers=HDR)
        assert page.status_code == 200
        assert "_enabled" not in page.text, "rule inputs shipped to a plan nothing watches"
        assert "Save alert settings" not in page.text
        # honest upsell in its place: what unlocks it, what it costs, both currencies
        assert "/billing" in page.text
        assert "$" in page.text and "₹" in page.text
        # their own data is not withheld — history stays
        assert "Recent alerts" in page.text

    def test_paid_alerts_page_has_the_form(self, app: FastAPI) -> None:
        grant(app, "pro")
        page = TestClient(app).get("/alerts", headers=HDR)
        assert "Save alert settings" in page.text
        assert "waste_above_target_enabled" in page.text

    def test_free_dashboard_widget_never_claims_watching(self, app: FastAPI) -> None:
        """Even with leftover saved rules, 'armed · checked hourly' would be a
        false statement for a plan dispatch skips."""
        client = TestClient(app)
        client.get("/dashboard", headers=HDR)  # creates the user
        with app.state.session_factory() as session:
            user = session.execute(select(User).where(User.email == EMAIL)).scalar_one()
            session.add(
                AlertRule(user_id=user.id, rule="waste_above_target", threshold=25.0, enabled=True)
            )
            session.commit()
        page = client.get("/dashboard/w/alerts", headers=HDR).text
        assert "checked hourly" not in page
        assert "armed</div>" not in page
        assert "nothing is watched on this plan" in page


class TestTheServerReChecksWhatTheUiHides:
    """§5d — the form not rendering is honesty, not authority. This is."""

    def test_free_alerts_post_is_refused_and_stores_nothing(self, app: FastAPI) -> None:
        resp = TestClient(app).post(
            "/alerts",
            headers=HDR,
            data={"waste_above_target_enabled": "1", "waste_above_target_threshold": "20"},
            follow_redirects=False,
        )
        assert resp.status_code == 403
        with app.state.session_factory() as session:
            assert session.execute(select(AlertRule)).scalars().all() == []

    def test_paid_alerts_post_still_works(self, app: FastAPI) -> None:
        grant(app, "pro")
        resp = TestClient(app).post(
            "/alerts",
            headers=HDR,
            data={"waste_above_target_enabled": "1", "waste_above_target_threshold": "20"},
            follow_redirects=False,
        )
        assert resp.status_code == 303


class TestExplicitConfirmWithTheConsequenceInWords:
    """§5c — one mechanism, and every ask states what will happen, never a
    bare 'Are you sure?'."""

    def shell(self) -> str:
        return (TEMPLATES / "app/_shell.html").read_text(encoding="utf-8")

    def test_the_shell_wires_both_transports(self) -> None:
        """data-confirm without a handler is a promise the UI silently drops.
        htmx requests and native form posts each need their listener."""
        shell = self.shell()
        assert "htmx:confirm" in shell
        assert 'addEventListener("submit"' in shell
        assert "data-confirm" in shell

    def test_the_applied_verdict_asks_and_names_the_headline(self) -> None:
        """The one verdict that feeds the verified headline (savings.py R1).
        It appears on TWO surfaces — the drawer and the top-findings widget —
        and both must carry the SAME ask from the SAME catalogue key."""
        for name in ("app/_finding_drawer.html", "app/widgets/_top_findings.html"):
            text = (TEMPLATES / name).read_text(encoding="utf-8")
            confirm = re.search(r'data-confirm="([^"]+)"', text)
            assert confirm, f"{name}: the Applied button lost its explicit-confirm"
            assert "app.confirm.applied" in confirm.group(1), (
                f"{name}: the ask must come from the shared catalogue key — "
                f"a second wording of the same consequence is drift"
            )
        assert "headline" in i18n.t("app.confirm.applied"), (
            "the consequence must name where the money goes"
        )
        # verdicts that move no money must NOT ask — confirm fatigue teaches
        # people to click through the one ask that matters
        drawer = (TEMPLATES / "app/_finding_drawer.html").read_text(encoding="utf-8")
        dismissed = drawer[drawer.index('value="dismissed"') : drawer.index('value="not_relevant"')]
        assert "data-confirm" not in dismissed

    def test_every_revoke_states_the_deletion(self) -> None:
        for name in ("app/sources.html", "app/settings.html"):
            text = (TEMPLATES / name).read_text(encoding="utf-8")
            forms = re.findall(r'action="/sources/[^"]*/revoke"[^>]*', text)
            assert forms, f"{name}: revoke form not found"
            for form in forms:
                assert "data-confirm" in form, f"{name}: revoke without an ask"
            asks = re.findall(r'revoke"[^>]*data-confirm="([^"]+)"', text)
            for raw in asks:
                ask = resolve_ask(raw)
                assert "delete" in ask.lower() and "key" in ask.lower(), (
                    f"{name}: the ask must state the consequence — the key is deleted"
                )

    def test_every_applied_control_anywhere_carries_the_ask(self) -> None:
        """Sweep, not a file list (cold-review note): the shell handler skips
        buttons without data-confirm SILENTLY — correct for Dismissed, fatal
        for a future Applied button someone adds without the ask. Any control
        that casts the applied verdict, on any surface, present or future,
        must carry data-confirm."""
        offenders = []
        for path in TEMPLATES.rglob("*.html"):
            text = path.read_text(encoding="utf-8")
            # a submit button named verdict/applied, or a hidden verdict=applied
            # input whose form's submit button is the actual control
            for m in re.finditer(r"<(button|form|input)[^>]*value=\"applied\"[^>]*>", text):
                scope_start = max(0, m.start() - 600)
                scope = text[scope_start : m.end() + 600]
                if "data-confirm" not in scope:
                    offenders.append(f"{path.relative_to(TEMPLATES).as_posix()}:{m.group(0)[:60]}")
        assert not offenders, f"applied-verdict controls without the ask: {offenders}"

    def test_no_second_confirm_mechanism_survives(self) -> None:
        """Inline onsubmit=confirm was the pre-kit way. Two mechanisms means
        the next surface picks one at random and the audit here goes stale."""
        offenders = [
            p.relative_to(TEMPLATES).as_posix()
            for p in TEMPLATES.rglob("*.html")
            if "onsubmit" in p.read_text(encoding="utf-8")
        ]
        assert offenders == [], f"inline onsubmit confirms outlived data-confirm: {offenders}"

    def test_every_ask_is_a_sentence_not_a_flinch(self) -> None:
        """'Are you sure?' transfers no information. Each ask must be long
        enough to be stating a consequence."""
        for path in TEMPLATES.rglob("*.html"):
            for raw in re.findall(r'data-confirm="([^"]+)"', path.read_text(encoding="utf-8")):
                if raw == "{{ confirm }}":
                    continue  # the kit macro's passthrough, not an ask
                ask = resolve_ask(raw)
                assert "{{" not in ask, f"{path.name}: unresolvable ask {raw!r}"
                words = ask.split()
                assert len(words) >= 8, f"{path.name}: {ask!r} asks without stating the consequence"
