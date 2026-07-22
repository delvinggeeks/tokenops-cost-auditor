"""T-WIZ-01..05 (PLAN-V15 V-D9 / R-MAGIC-CONNECT).

The wizard is the product's first minute. These tests hold it to the
ruling: plain words, no jargon, a live verdict, an immediate first pull,
and a provider outage that degrades instead of blocking.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.persistence.models import Source, Subscription, User
from tokenops_cost_auditor.services.connectors import validate
from tokenops_cost_auditor.web import help as help_registry

EMAIL = "owner@example.com"
HDR = {"X-User-Email": EMAIL}
# Honest necessary term "Admin key" is NOT jargon (it's the truth, verified
# against provider docs); the ban is for raw scope strings and endpoint URLs.
JARGON = re.compile(r"api\.openai|usage\.read|/v1/organization|sk-ant-admin01|bearer token", re.I)
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
        elif self.behaviour == "bad_key":
            self.status_code = 401
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

        # 403 = valid key, no admin permission → NO_SCOPE (honest Admin-key copy)
        no_scope = validate.validate_key("openai", "sk-limited", FakeHTTP("no_scope"))
        assert no_scope.status == validate.NO_SCOPE and no_scope.can_save is False
        assert "Admin key" in no_scope.detail
        assert "box to tick" not in no_scope.detail  # the stale screenshot copy is gone

        # 401 = bad/revoked key → BAD_KEY, NOT misdiagnosed as a permission gap
        # (readiness audit: reporting a typo'd key as "no permission" was false)
        bad = validate.validate_key("openai", "sk-typo", FakeHTTP("bad_key"))
        assert bad.status == validate.BAD_KEY and bad.can_save is False
        assert "authenticate" in bad.headline.lower() and "mistyped" in bad.detail.lower()

        down = validate.validate_key("openai", "sk-good", FakeHTTP("down"))
        assert down.status == validate.UNREACHABLE
        assert down.can_save is True, "R-WIZ-DEGRADE: an outage must not block"

        for verdict in (ok, no_scope, bad, down):
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
        assert "nothing else for you to do" in resp.text.lower()  # the ONE-line promise
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
                "key_kind",
                "who_can",
                "key_can",
                "we_do",
                "create_hint",
                "step2_title",
                "step2_body",
                "step3_title",
                "step3_body",
                "provider_name",
            } <= set(copy)
            page = TestClient(app).get(f"/sources/connect/{provider}", headers=HDR)
            assert page.status_code == 200
            assert copy["step1_title"] in page.text
            assert copy["key_kind"] in page.text
            assert copy["who_can"] in page.text
        with pytest.raises(KeyError):
            help_registry.wizard("does-not-exist")

    def test_04_names_the_key_honestly_without_raw_jargon(self, app: FastAPI) -> None:
        """T-WIZ-04 (revised, walkthrough 2026-07-22): the OLD copy hid that
        the usage API needs an org ADMIN key — verified against OpenAI +
        Anthropic docs, there is no usage-only key. Honesty now REQUIRES the
        term 'Admin key' (understating it fails enterprise review); the ban
        keeps out raw scope strings and endpoint URLs, not the honest word."""
        give_plan(app)
        for provider in ("openai", "anthropic"):
            text = visible(TestClient(app).get(f"/sources/connect/{provider}", headers=HDR).text)
            assert not JARGON.search(text), f"raw jargon leaked in the {provider} wizard"
            assert "Admin key" in text, "the key's real authority must be named"
            # the honesty pairing: what the key CAN do next to what we DO
            assert "organization" in text.lower() and "read" in text.lower()

    def test_wizard_states_what_we_cannot_see_and_the_key_authority(self, app: FastAPI) -> None:
        give_plan(app)
        page = TestClient(app).get("/sources/connect/openai", headers=HDR).text
        assert "never" in page and "prompts" in page
        assert "manage your organization" in page  # honest: the key IS powerful
        assert "Only an OpenAI organization Owner can create" in page  # who can
        assert "Upload a file instead" in page  # the enterprise escape hatch

    def test_anthropic_console_url_is_the_current_one(self, app: FastAPI) -> None:
        """The console.anthropic.com URL 301s to platform.claude.com now
        (verified live 2026-07-22); a wizard that sends users to a redirect
        reads as stale."""
        copy = help_registry.wizard("anthropic")
        assert copy["console_url"] == "https://platform.claude.com/settings/admin-keys"

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


class TestColdReviewRegressionsV9:
    """V-D9 cold-review (2026-07-23) — f.1..f.5."""

    def test_f1_a_user_at_their_limit_is_refused_before_we_call_the_provider(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Never spend a customer's provider quota on a request we already
        know we will refuse."""
        user_id = give_plan(app, "pro")
        with app.state.session_factory() as session:
            session.add(
                Source(
                    user_id=user_id,
                    provider="anthropic",
                    label="existing",
                    credentials_encrypted="x",
                )
            )
            session.commit()
        called: list[str] = []
        monkeypatch.setattr(
            validate,
            "validate_key",
            lambda *a, **k: called.append("called") or validate.VERDICTS[validate.OK],
        )
        resp = TestClient(app).post(
            "/sources/connect/openai/validate", headers=HDR, data={"api_key": "sk-x"}
        )
        assert resp.status_code == 403
        assert called == [], "the provider must not be contacted for a refused request"

    def test_f2_the_user_row_survives_a_rejected_key(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A brand-new user creating their account and pasting a bad key must
        still exist afterwards."""
        give_plan(app)
        with app.state.session_factory() as session:
            session.query(User).delete()
            session.commit()
        give_plan(app)  # re-create with a plan
        monkeypatch.setattr(
            validate, "validate_key", lambda *a, **k: validate.VERDICTS[validate.NO_SCOPE]
        )
        TestClient(app).post(
            "/sources/connect/openai/validate", headers=HDR, data={"api_key": "sk-bad"}
        )
        with app.state.session_factory() as session:
            assert session.execute(select(User).where(User.email == EMAIL)).scalar_one()

    def test_f3_a_double_submit_cannot_create_two_connections(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Double-click must not buy two connections and two first-pulls."""
        give_plan(app, "team")  # room for several, so only idempotency can stop it
        monkeypatch.setattr(
            validate, "validate_key", lambda *a, **k: validate.VERDICTS[validate.OK]
        )
        from tokenops_cost_auditor.web import routes_sources

        pulls: list[str] = []
        monkeypatch.setattr(
            routes_sources,
            "_kickoff_first_pull",
            lambda request, source_id: pulls.append(source_id),
        )
        client = TestClient(app)
        first = client.post(
            "/sources/connect/openai/validate", headers=HDR, data={"api_key": "sk-good"}
        )
        second = client.post(
            "/sources/connect/openai/validate", headers=HDR, data={"api_key": "sk-good"}
        )
        assert first.status_code == 200 and second.status_code == 409
        with app.state.session_factory() as session:
            sources = session.execute(select(Source)).scalars().all()
            assert len(sources) == 1
        assert len(pulls) == 1, "one connection, one first pull"

    def test_f4_the_sample_fixtures_ship_with_the_package(self) -> None:
        """/sample is public: it must not depend on the test tree, which is
        absent from an installed wheel."""
        from tokenops_cost_auditor.services.report import sample

        assert sample.FIXTURES.is_dir()
        assert "site-packages" not in str(sample.FIXTURES) or sample.FIXTURES.exists()
        for name in sample.SAMPLE_SOURCES:
            assert (sample.FIXTURES / name).exists(), name
        # and it lives inside the installed package, not beside it
        import tokenops_cost_auditor

        pkg_root = Path(tokenops_cost_auditor.__file__).parent
        assert pkg_root in sample.FIXTURES.parents

    def test_f5_the_sample_is_rendered_once_not_per_request(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A public unauthenticated page must not re-run the engine per hit."""
        from tokenops_cost_auditor.services.report import sample

        sample._RENDERED = None
        builds: list[int] = []
        real_build = sample.build_sample
        monkeypatch.setattr(
            sample,
            "build_sample",
            lambda s, t: (builds.append(1), real_build(s, t))[1],
        )
        client = TestClient(app)
        for _ in range(3):
            assert client.get("/sample").status_code == 200
        assert len(builds) == 1, f"engine ran {len(builds)} times for 3 requests"
        sample._RENDERED = None


class TestMultiSource:
    """R-MULTI-SOURCE (founder order 2026-07-23): a second ACCOUNT of the same
    provider connects fine up to the plan limit; the SAME key is blocked by
    fingerprint, with the existing connection named in plain words."""

    def test_two_accounts_same_provider_connect_with_distinct_labels(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        give_plan(app, "team")
        monkeypatch.setattr(
            validate, "validate_key", lambda *a, **k: validate.VERDICTS[validate.OK]
        )
        from tokenops_cost_auditor.web import routes_sources

        pulls: list[str] = []
        monkeypatch.setattr(
            routes_sources,
            "_kickoff_first_pull",
            lambda request, source_id: pulls.append(source_id),
        )
        client = TestClient(app)
        first = client.post(
            "/sources/connect/openai/validate", headers=HDR, data={"api_key": "sk-org-A"}
        )
        second = client.post(
            "/sources/connect/openai/validate", headers=HDR, data={"api_key": "sk-org-B"}
        )
        assert first.status_code == 200 and second.status_code == 200
        with app.state.session_factory() as session:
            sources = session.execute(select(Source)).scalars().all()
            assert len(sources) == 2
            assert {s.label for s in sources} == {"openai usage", "openai usage #2"}
            fps = {s.key_fingerprint for s in sources}
            assert None not in fps and len(fps) == 2, "distinct keys, distinct fingerprints"
        assert len(pulls) == 2, "each account gets its own first pull"

    def test_same_key_again_is_blocked_naming_the_existing_connection(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        give_plan(app, "team")
        monkeypatch.setattr(
            validate, "validate_key", lambda *a, **k: validate.VERDICTS[validate.OK]
        )
        from tokenops_cost_auditor.web import routes_sources

        monkeypatch.setattr(routes_sources, "_kickoff_first_pull", lambda request, source_id: None)
        client = TestClient(app)
        assert (
            client.post(
                "/sources/connect/openai/validate", headers=HDR, data={"api_key": "sk-org-A"}
            ).status_code
            == 200
        )
        again = client.post(
            "/sources/connect/openai/validate", headers=HDR, data={"api_key": "sk-org-A"}
        )
        assert again.status_code == 409
        assert "openai usage" in again.json()["detail"]

    def test_revoke_then_reconnect_never_reuses_a_label(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cold-review f.4: /explore keeps revoked accounts selectable by
        label, so a reconnect must mint a fresh suffix, not a duplicate."""
        give_plan(app, "team")
        monkeypatch.setattr(
            validate, "validate_key", lambda *a, **k: validate.VERDICTS[validate.OK]
        )
        from tokenops_cost_auditor.web import routes_sources

        monkeypatch.setattr(routes_sources, "_kickoff_first_pull", lambda request, source_id: None)
        client = TestClient(app)
        assert (
            client.post(
                "/sources/connect/openai/validate", headers=HDR, data={"api_key": "sk-org-A"}
            ).status_code
            == 200
        )
        with app.state.session_factory() as session:
            first = session.execute(select(Source)).scalars().one()
            first_label, first_id = first.label, first.id
        assert client.post(f"/sources/{first_id}/revoke", headers=HDR).status_code in (200, 303)
        assert (
            client.post(
                "/sources/connect/openai/validate", headers=HDR, data={"api_key": "sk-org-B"}
            ).status_code
            == 200
        )
        with app.state.session_factory() as session:
            labels = {s.label for s in session.execute(select(Source)).scalars().all()}
        assert first_label == "openai usage"
        assert labels == {"openai usage", "openai usage #2"}
