"""Deterministic fixture generator (docs/05 §2). Seeded RNG; committed outputs are
canonical — regenerate ONLY when the fixture spec changes, and commit the diff.

Usage: uv run python tests/fixtures/gen_fixtures.py [outdir]
Generates: F1 openai_small.jsonl (500 clean) · F2 anthropic_small.jsonl (500 clean)
· F3 mixed_dirty.jsonl (500 rows, exactly 8% invalid — FR-03 path) · F4 generic.csv
· claude_code_session.jsonl (FR-24 exporter fixture).
"""

from __future__ import annotations

import json
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

SEED = 20260717
BASE_TS = datetime(2026, 6, 1, 8, 0, 0, tzinfo=UTC)

OPENAI_MODELS = ["gpt-5.6-terra", "gpt-5.4-mini", "gpt-5.4-nano"]
ANTHROPIC_MODELS = ["claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5"]
TAGS = ["chat-api", "summarizer", "extraction", "support-bot"]


def _openai_line(rng: random.Random, i: int) -> dict[str, object]:
    ts = BASE_TS + timedelta(seconds=i * 37)
    prompt = rng.randint(200, 6000)
    cached = rng.choice([0, 0, 0, rng.randint(0, prompt // 2)])
    return {
        "request_id": f"oai-{i:05d}",
        "ts": ts.isoformat(),
        "endpoint": "/v1/chat/completions",
        "tag": rng.choice(TAGS),
        "latency_ms": round(rng.uniform(180, 4200), 1),
        "team": rng.choice(["growth", "platform"]),  # unknown field -> raw_extra
        "request": {
            "max_tokens": rng.choice([1024, 4096, 8192]),
            "messages": [
                {"role": "system", "content": f"You are assistant profile {i % 7}."},
                {"role": "user", "content": f"Task {i}: summarize item {rng.randint(1, 99)}"},
            ],
        },
        "response": {
            "id": f"chatcmpl-{i:05d}",
            "object": "chat.completion",
            "created": int(ts.timestamp()),
            "model": rng.choice(OPENAI_MODELS),
            "usage": {
                "prompt_tokens": prompt,
                "completion_tokens": rng.randint(20, 900),
                "total_tokens": 0,
                "prompt_tokens_details": {"cached_tokens": cached},
            },
        },
    }


def _anthropic_line(rng: random.Random, i: int) -> dict[str, object]:
    ts = BASE_TS + timedelta(seconds=i * 41)
    base_input = rng.randint(150, 5000)
    cache_read = rng.choice([0, 0, rng.randint(0, 3000)])
    cache_write = rng.choice([0, 0, 0, rng.randint(0, 1500)])
    return {
        "request_id": f"ant-{i:05d}",
        "ts": ts.isoformat(),
        "endpoint": "/v1/messages",
        "tag": rng.choice(TAGS),
        "latency_ms": round(rng.uniform(200, 5100), 1),
        "env": rng.choice(["prod", "staging"]),  # unknown field -> raw_extra
        "request": {
            "max_tokens": rng.choice([1024, 2048, 8192]),
            "system": f"System profile {i % 5}.",
            "messages": [{"role": "user", "content": f"Request {i}: classify record {i * 3}"}],
        },
        "response": {
            "id": f"msg_{i:05d}",
            "type": "message",
            "role": "assistant",
            "model": rng.choice(ANTHROPIC_MODELS),
            "usage": {
                "input_tokens": base_input,
                "cache_creation_input_tokens": cache_write,
                "cache_read_input_tokens": cache_read,
                "output_tokens": rng.randint(15, 1100),
            },
        },
    }


def _dirty_lines(rng: random.Random, n: int, bad: int) -> list[str]:
    """n rows total; exactly `bad` invalid with mixed error kinds (F3 exercises the
    FR-03 row-error path). Single provider: format detection is per-file, so a
    multi-provider JSONL is a format error, not a row-error case."""
    bad_idx = set(rng.sample(range(n), bad))
    lines: list[str] = []
    for i in range(n):
        if i in bad_idx:
            kind = i % 4
            if kind == 0:
                lines.append("{not valid json%%")
            elif kind == 1:
                lines.append(json.dumps(["a", "list", "not", "object"]))
            elif kind == 2:  # missing usage -> missing prompt_tokens
                lines.append(
                    json.dumps(
                        {
                            "response": {
                                "id": f"bad-{i}",
                                "object": "chat.completion",
                                "created": int(BASE_TS.timestamp()),
                                "model": "gpt-5.2",
                            }
                        }
                    )
                )
            else:  # invalid timestamp
                row = _openai_line(rng, i)
                row["ts"] = "not-a-date"
                resp = row["response"]
                assert isinstance(resp, dict)
                resp["created"] = None
                lines.append(json.dumps(row))
        else:
            lines.append(json.dumps(_openai_line(rng, i)))
    return lines


def _csv_lines(rng: random.Random, n: int) -> list[str]:
    header = (
        "ts,provider,model,prompt_tokens,completion_tokens,cached_tokens,"
        "latency_ms,endpoint,request_id,tag,declared_max_tokens,cost_center"
    )
    rows = [header]
    for i in range(n):
        ts = (BASE_TS + timedelta(seconds=i * 53)).isoformat()
        provider = rng.choice(["openai", "anthropic"])
        model = rng.choice(OPENAI_MODELS if provider == "openai" else ANTHROPIC_MODELS)
        rows.append(
            f"{ts},{provider},{model},{rng.randint(100, 4000)},{rng.randint(10, 800)},"
            f"{rng.choice([0, 0, 512])},{round(rng.uniform(150, 3000), 1)},/v1/chat,"
            f"csv-{i:04d},{rng.choice(TAGS)},{rng.choice(['', '4096'])},cc-{i % 3}"
        )
    return rows


def _claude_code_session(rng: random.Random, n_msgs: int) -> list[str]:
    """Synthetic Claude Code transcript: user/assistant/progress lines; only
    assistant lines carry usage. Content strings present (exporter must DROP them)."""
    lines: list[str] = []
    session = "0a1b2c3d-sess-fixture"
    for i in range(n_msgs):
        ts = (BASE_TS + timedelta(seconds=i * 9)).isoformat()
        lines.append(
            json.dumps(
                {
                    "type": "user",
                    "sessionId": session,
                    "timestamp": ts,
                    "message": {"role": "user", "content": f"SECRET-USER-PROMPT-{i}"},
                }
            )
        )
        lines.append(
            json.dumps(
                {
                    "type": "assistant",
                    "sessionId": session,
                    "timestamp": (BASE_TS + timedelta(seconds=i * 9 + 4)).isoformat(),
                    "message": {
                        "id": f"msg_cc_{i:04d}",
                        "type": "message",
                        "role": "assistant",
                        "model": "claude-opus-4-8",
                        "content": [{"type": "text", "text": f"SECRET-ASSISTANT-REPLY-{i}"}],
                        "usage": {
                            "input_tokens": rng.randint(400, 9000),
                            "cache_creation_input_tokens": rng.choice([0, rng.randint(100, 2000)]),
                            "cache_read_input_tokens": rng.choice([0, rng.randint(500, 8000)]),
                            "output_tokens": rng.randint(30, 700),
                        },
                    },
                }
            )
        )
        if i % 5 == 0:
            lines.append(json.dumps({"type": "progress", "sessionId": session, "timestamp": ts}))
    return lines


def main(outdir: Path) -> None:
    rng = random.Random(SEED)
    outdir.mkdir(parents=True, exist_ok=True)

    (outdir / "openai_small.jsonl").write_text(
        "\n".join(json.dumps(_openai_line(rng, i)) for i in range(500)) + "\n"
    )
    (outdir / "anthropic_small.jsonl").write_text(
        "\n".join(json.dumps(_anthropic_line(rng, i)) for i in range(500)) + "\n"
    )
    (outdir / "mixed_dirty.jsonl").write_text("\n".join(_dirty_lines(rng, 500, 40)) + "\n")
    (outdir / "generic.csv").write_text("\n".join(_csv_lines(rng, 300)) + "\n")
    (outdir / "claude_code_session.jsonl").write_text(
        "\n".join(_claude_code_session(rng, 40)) + "\n"
    )
    print(f"fixtures written to {outdir}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent)
