"""S-1 tests — the Python SDK.

The load-bearing pins: FR-22 BY CONSTRUCTION (a record built from a
text-carrying response contains no text), X-01 OBSERVE-ONLY (the wrapper
returns the real result unmodified and never raises/blocks the caller even
when our side is broken), the anthropic cache composition, the bounded
observe-only batcher, DSN parsing, and the end-to-end journey (SDK-built
records → /api/v1/ingest → an audit lands).
"""

from __future__ import annotations

import re
from types import SimpleNamespace as NS
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

import tokenops_cost_auditor.sdk as toca
from tokenops_cost_auditor.persistence.models import Audit, Subscription, User
from tokenops_cost_auditor.sdk import _parse_dsn
from tokenops_cost_auditor.sdk.batcher import Batcher
from tokenops_cost_auditor.sdk.extract import extract_anthropic, extract_openai
from tokenops_cost_auditor.sdk.instrument import _wrap, install_openai

EMAIL = "sdk-user@example.com"
HDR = {"X-User-Email": EMAIL}


# --- fake provider responses that DELIBERATELY carry text ---------------
def openai_response() -> Any:
    return NS(
        model="gpt-5.4",
        # text fields the SDK must never touch:
        choices=[NS(message=NS(content="SECRET COMPLETION TEXT"))],
        usage=NS(
            prompt_tokens=3084,
            completion_tokens=47,
            prompt_tokens_details=NS(cached_tokens=1000),
        ),
    )


def anthropic_response() -> Any:
    return NS(
        model="claude-sonnet-5",
        content=[NS(text="SECRET ANSWER TEXT")],
        usage=NS(
            input_tokens=40000,
            output_tokens=2000,
            cache_read_input_tokens=50000,
            cache_creation_input_tokens=10000,
        ),
    )


class TestFR22ByConstruction:
    def test_01_openai_record_has_counts_never_text(self) -> None:
        rec = extract_openai(openai_response(), latency_s=0.8)
        assert rec is not None
        assert rec["prompt_tokens"] == 3084 and rec["completion_tokens"] == 47
        assert rec["cached_tokens"] == 1000 and rec["provider"] == "openai"
        assert "SECRET" not in str(rec)  # the whole record, stringified

    def test_02_anthropic_composition_and_no_text(self) -> None:
        rec = extract_anthropic(anthropic_response(), latency_s=1.2)
        assert rec is not None
        # prompt = input + cache_read + cache_creation (anthropic semantics)
        assert rec["prompt_tokens"] == 40000 + 50000 + 10000
        assert rec["cached_tokens"] == 50000 and rec["cache_write_tokens"] == 10000
        assert rec["completion_tokens"] == 2000
        assert "SECRET" not in str(rec)

    def test_03_only_allowlisted_fields_emitted(self) -> None:
        allowed = {
            "ts",
            "provider",
            "model",
            "prompt_tokens",
            "completion_tokens",
            "cached_tokens",
            "cache_write_tokens",
            "latency_ms",
            "endpoint",
            "request_id",
            "tag",
            "declared_max_tokens",
            "prefix_hash",
        }
        for rec in (
            extract_openai(openai_response(), 0.1),
            extract_anthropic(anthropic_response(), 0.1),
        ):
            assert rec is not None and set(rec) <= allowed

    def test_04_no_usage_yields_no_record(self) -> None:
        assert extract_openai(NS(model="x", choices=[]), 0.1) is None


class FakeCompletions:
    """Stands in for openai's Completions class."""

    def create(self, **kwargs: Any) -> Any:
        return openai_response()


class TestObserveOnly:
    def test_05_wrapper_returns_real_result_unmodified(self) -> None:
        recorded: list[dict] = []
        obj = FakeCompletions()
        assert _wrap(FakeCompletions, "create", extract_openai, recorded.append)
        resp = obj.create(messages=[{"role": "user", "content": "hi"}])
        assert resp.model == "gpt-5.4"  # the real response, unaltered
        assert recorded and recorded[0]["prompt_tokens"] == 3084

    def test_06_broken_recorder_never_breaks_the_call(self) -> None:
        def boom(_rec: dict) -> None:
            raise RuntimeError("our SDK is broken")

        class C:
            def create(self, **kwargs: Any) -> Any:
                return openai_response()

        assert _wrap(C, "create", extract_openai, boom)
        # the customer's call still returns normally despite our recorder raising
        result = C().create()
        assert result.model == "gpt-5.4" and result.usage.completion_tokens == 47

    def test_07_double_wrap_is_idempotent(self) -> None:
        class C:
            def create(self) -> Any:
                return openai_response()

        assert _wrap(C, "create", extract_openai, lambda r: None) is True
        assert _wrap(C, "create", extract_openai, lambda r: None) is False  # already wrapped


class FakeHTTP:
    """Captures batches the batcher POSTs, no network."""

    def __init__(self) -> None:
        self.batches: list[list[dict]] = []

    def install(self, monkeypatch: Any) -> None:
        import json as _json
        import urllib.request

        def fake_urlopen(req: Any, timeout: float = 0) -> Any:
            body = _json.loads(req.data)
            self.batches.append(body["records"])

            class R:
                def read(self_inner) -> bytes:
                    return b"{}"

                def __enter__(self_inner) -> Any:
                    return self_inner

                def __exit__(self_inner, *a: Any) -> None:
                    return None

            return R()

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


class TestBatcher:
    def test_08_bounded_queue_drops_never_blocks(self, monkeypatch: Any) -> None:
        http = FakeHTTP()
        http.install(monkeypatch)
        b = Batcher("https://h", "ik_k", flush_interval=999, batch_size=999, max_queue=3)
        for _ in range(10):
            b.record({"provider": "openai", "model": "m", "prompt_tokens": 1})
        assert b.dropped == 7  # 10 offered, buffer of 3 — 7 shed, no exception
        b.close()

    def test_09_flush_ships_with_idempotency_key(self, monkeypatch: Any) -> None:
        captured: dict[str, Any] = {}
        import urllib.request

        def fake_urlopen(req: Any, timeout: float = 0) -> Any:
            captured["key"] = req.headers.get("Idempotency-key") or req.headers.get(
                "Idempotency-Key"
            )
            captured["auth"] = req.headers.get("Authorization")

            class R:
                def read(self) -> bytes:
                    return b"{}"

                def __enter__(self) -> Any:
                    return self

                def __exit__(self, *a: Any) -> None:
                    return None

            return R()

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        b = Batcher("https://h", "ik_k", flush_interval=999)
        b.record({"provider": "openai", "model": "m", "prompt_tokens": 1})
        b.flush()
        assert captured["auth"] == "Bearer ik_k" and captured["key"]  # FR-26 key present
        b.close()

    def test_10_ship_failure_is_swallowed(self, monkeypatch: Any) -> None:
        import urllib.request

        def boom(req: Any, timeout: float = 0) -> Any:
            raise OSError("network down")

        monkeypatch.setattr(urllib.request, "urlopen", boom)
        b = Batcher("https://h", "ik_k", flush_interval=999)
        b.record({"provider": "openai", "model": "m", "prompt_tokens": 1})
        b.flush()  # must not raise
        assert b.dropped == 1 and b.shipped == 0
        b.close()


class TestDsnAndInit:
    def test_11_dsn_parse(self) -> None:
        assert _parse_dsn("https://ik_abc@tokenops-cost-auditor.com") == (
            "https://tokenops-cost-auditor.com",
            "ik_abc",
        )
        assert _parse_dsn("https://no-user-host.com") is None
        assert _parse_dsn("not a url") is None

    def test_12_init_inert_without_dsn(self, monkeypatch: Any) -> None:
        monkeypatch.delenv("TOKENOPS_COST_AUDITOR_DSN", raising=False)
        toca._reset_for_tests()
        assert toca.init() is False
        toca.record({"provider": "openai", "model": "m", "prompt_tokens": 1})  # no-op, no raise


class TestEndToEnd:
    def test_13_sdk_records_land_as_an_audit(self, app: FastAPI) -> None:
        """The S-1 DoD: records the SDK BUILDS from real provider responses,
        posted to the S-0 endpoint, become a done audit — no export step."""
        with app.state.session_factory() as session:
            user = User(email=EMAIL)
            session.add(user)
            session.flush()
            session.add(Subscription(user_id=user.id, provider="stripe", plan="pro"))
            session.commit()
        client = TestClient(app)
        minted = client.post("/sources/sdk/key", data={"label": "sdk"}, headers=HDR)
        token = re.search(r"Bearer (ik_[A-Za-z0-9_\-]+)", minted.text).group(1)  # type: ignore[union-attr]
        # build records the way the SDK does, from text-carrying responses
        records = [extract_openai(openai_response(), 0.5)] + [
            extract_anthropic(anthropic_response(), 0.6) for _ in range(4)
        ]
        resp = client.post(
            "/api/v1/ingest",
            json={"records": records},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201, resp.text  # the door accepted SDK-built records
        with app.state.session_factory() as session:
            audit = session.get(Audit, resp.json()["audit_id"])
            assert audit is not None and audit.status == "done" and audit.paid_via == "sdk"


class TestInstrumentInstallers:
    def test_14_installers_noop_when_lib_absent(self) -> None:
        # openai/anthropic are not installed in the test env — installers must
        # return False cleanly, never raise.
        assert install_openai(lambda r: None) is False
