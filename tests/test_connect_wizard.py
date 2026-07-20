"""T-WIZ-01..05 (PLAN-V15 V-D9 / R-MAGIC-CONNECT).

The wizard is the product's first minute. These tests hold it to the
ruling: plain words, no jargon, a live verdict, an immediate first pull,
and a provider outage that degrades instead of blocking.
"""

from __future__ import annotations

import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.persistence.models import Source, Subscription, User
from tokenops_cost_auditor.services.connectors import validate
from tokenops_cost_auditor.web import help as help_registry

EMAIL = "owner@example.com"
HDR = {"X-User-Email": EMAIL}
JARGON = re.compile(r"org admin key|admin key|api\.openai|usage\.read|scope[s]?\b", re.I)
TAGS = re.compile(r"<[^>]+>")


def visible(html: str) -> str:
    return TAGS.sub(" ", html)


def give_plan(app: FastAPI, plan: str = "pro") -> str:
    with app.state.session_factory() as session:
        user = session.execute(select(User).where(User.email == EMAIL)).scalar_one_or_none()
        if user is None:
            user = User(email=EMAIL)
            session.add(user)
            session.flush()
        session.add(Subscription(user_id=user.id, provider="stripe", plan=plan))
        session.commit()
        return user.id


class FakeHTTP:
    """Stands in for the provider during validation."""

    def __init__(self, behaviour: str) -> None:
        self.behaviour = behaviour
        self.status_code = 200

    def get(self, url: str, params: dict, headers: dict) -> FakeHTTP:
        if self.behaviour == "no_scope":
            self.status_code = 403
        elif self.behaviour == "down":
            raise RuntimeError("connection refused")
        return self

    def json(self) -> dict:
        return {"data": [], "has_more": False}

    def raise_for_status(self) -> None:
        return None


class TestValidationVerdicts:
    def test_01_three_verdicts_in_plain_words_without_leaking_the_key(self) -> None:
        """T-WIZ-01: a readable key, one without the permission, and an
        unreachable provider — each a plain-words answer."""
        ok = validate.validate_key("openai", "sk-good", FakeHTTP("ok"))
        assert ok.status == validate.OK and ok.can_save is True
        assert "read-only" in ok.detail.lower()
        assert "never see your prompts" in ok.detail.lower()

        no_scope = validate.validate_key("openai", "sk-limited", FakeHTTP("no_scope"))
        assert no_scope.status == validate.NO_SCOPE and no_scope.can_save is False

        down = validate.validate_key("openai", "sk-good", FakeHTTP("down"))
        assert down.status == validate.UNREACHABLE
        assert down.can_save is True, "R-WIZ-DEGRADE: an outage must not block"

        for verdict in (ok, no_scope, down):
            assert "sk-" not in verdict.headline + verdict.detail

    def test_05_degrade_path_saves_the_key_and_offers_a_retry(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """T-WIZ-05: provider unreachable → key saved, plain-words state,
        retry affordance, never a hang or a dead end."""
        give_plan(app)
        monkeypatch.setattr(
            validate, "validate_key", lambda *a, **k: validate.VERDICTS[validate.UNREACHABLE]
        )
        resp = TestClient(app).post(
            "/sources/connect/openai/validate", headers=HDR, data={"api_key": "sk-x"}
        )
        assert resp.status_code == 200
        assert "reach your provider" in resp.text  # apostrophe is HTML-escaped
        assert "check it again on the first pull" in resp.text
        assert "Try again" in resp.text
        with app.state.session_factory() as session:
            saved = session.execute(select(Source)).scalars().all()
            assert len(saved) == 1 and saved[0].credentials_encrypted is not None

    def test_no_scope_saves_nothing(self, app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
        give_plan(app)
        monkeypatch.setattr(
            validate, "validate_key", lambda *a, **k: validate.VERDICTS[validate.NO_SCOPE]
        )
        resp = TestClient(app).post(
            "/sources/connect/openai/validate", headers=HDR, data={"api_key": "sk-x"}
        )
        assert "read usage reports" in resp.text  # apostrophe is HTML-escaped
        assert "Nothing was saved" in resp.text
        with app.state.session_factory() as session:
            assert session.execute(select(Source)).scalars().all() == []


class TestInstantFirstPull:
    def test_02_connecting_kicks_off_a_pull_without_waiting_for_the_tick(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """T-WIZ-02: the magic moment is THIS session, not tomorrow."""
        give_plan(app)
        started: list[str] = []
        monkeypatch.setattr(
            validate, "validate_key", lambda *a, **k: validate.VERDICTS[validate.OK]
        )
        from tokenops_cost_auditor.web import routes_sources

        monkeypatch.setattr(
            routes_sources,
            "_kickoff_first_pull",
            lambda request, source_id: started.append(source_id),
        )
        resp = TestClient(app).post(
            "/sources/connect/openai/validate", headers=HDR, data={"api_key": "sk-good"}
        )
        assert resp.status_code == 200
        assert "Go to my dashboard" in resp.text
        assert "in a minute or two, not tomorrow" in resp.text
        assert len(started) == 1, "the first pull must start immediately"

    def test_a_failing_first_pull_never_breaks_the_connect(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The scheduled tick remains the guarantee, so a bad first pull is
        invisible to the customer."""
        give_plan(app)
        monkeypatch.setattr(
            validate, "validate_key", lambda *a, **k: validate.VERDICTS[validate.OK]
        )
        from tokenops_cost_auditor.services.connectors import pull

        monkeypatch.setattr(
            pull, "run_pull", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        resp = TestClient(app).post(
            "/sources/connect/openai/validate", headers=HDR, data={"api_key": "sk-good"}
        )
        assert resp.status_code == 200 and "Connected" in resp.text


class TestWizardCopy:
    def test_03_every_string_comes_from_the_help_registry(self, app: FastAPI) -> None:
        """T-WIZ-03: wizard copy lives in the registry like everything else."""
        give_plan(app)  # Free allows no connections, so the page would be the gate
        for provider in help_registry.wizard_providers():
            copy = help_registry.wizard(provider)
            assert {
                "step1_title",
                "step1_body",
                "console_url",
                "permission_hint",
                "step2_title",
                "step2_body",
                "step3_title",
                "step3_body",
                "provider_name",
            } <= set(copy)
            page = TestClient(app).get(f"/sources/connect/{provider}", headers=HDR)
            assert page.status_code == 200
            assert copy["step1_title"] in page.text
            assert copy["permission_hint"] in page.text
        with pytest.raises(KeyError):
            help_registry.wizard("does-not-exist")

    def test_04_no_jargon_reaches_the_customer(self, app: FastAPI) -> None:
        """T-WIZ-04: 'a read-only key to your usage reports', never
        'org admin key' or a raw scope name."""
        give_plan(app)
        for provider in ("openai", "anthropic"):
            text = visible(TestClient(app).get(f"/sources/connect/{provider}", headers=HDR).text)
            assert not JARGON.search(text), f"jargon leaked in the {provider} wizard"
            assert "read-only" in text.lower()

    def test_wizard_states_what_we_cannot_see(self, app: FastAPI) -> None:
        give_plan(app)
        page = TestClient(app).get("/sources/connect/openai", headers=HDR).text
        assert "never see" in page and "prompts" in page
        assert "Upload a file instead" in page  # the no-connection escape hatch

    def test_unknown_provider_is_404(self, app: FastAPI) -> None:
        assert TestClient(app).get("/sources/connect/acme", headers=HDR).status_code == 404
        assert (
            TestClient(app)
            .post("/sources/connect/acme/validate", headers=HDR, data={"api_key": "x"})
            .status_code
            == 404
        )


class TestWizardPlanGate:
    def test_at_limit_explains_instead_of_failing_at_the_end(self, app: FastAPI) -> None:
        user_id = give_plan(app, "pro")
        with app.state.session_factory() as session:
            session.add(
                Source(
                    user_id=user_id, provider="openai", label="existing", credentials_encrypted="x"
                )
            )
            session.commit()
        page = TestClient(app).get("/sources/connect/openai", headers=HDR).text
        assert "already in use" in page
        assert "Compare plans" in page
        assert "Check and connect" not in page, "do not invite a paste that must fail"
