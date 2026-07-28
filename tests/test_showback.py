"""Showback CSV serializer (FR-38, docs/03-LLD.md §9.5, T-F5) — golden bytes
for a fixed artifact dict, honest empty-allocation state, and byte-for-byte
verbatim figures (no re-rounding). Pure serialization over a dict, so no
runner/pipeline fixtures are needed — the journey-level check that a REAL
artifact round-trips lives in tests/test_breakdown.py."""

from __future__ import annotations

from tokenops_cost_auditor.services.dashboard import showback

HEADER = "dimension,name,calls,monthly_usd,share,pct_attributed_caveat"

ARTIFACT: dict[str, object] = {
    "monthly_spend_usd": 150.5,
    "by_model": [
        {
            "name": "claude-opus-4-8",
            "calls": 10,
            "monthly_usd": 100.123456,
            "share": 0.6651234,
            "cache_hit_rate": 0.1,
            "out_in_ratio": 0.2,
            "cost_per_1k_out": 0.5,
        },
        {
            "name": "gpt-5.6-luna",
            "calls": 5,
            "monthly_usd": 50.376544,
            "share": 0.3348766,
            "cache_hit_rate": 0.0,
            "out_in_ratio": 0.1,
            "cost_per_1k_out": 0.3,
        },
    ],
    "by_route": [
        {
            "name": "chat",
            "calls": 12,
            "monthly_usd": 120.4,
            "share": 0.8,
            "cache_hit_rate": 0.05,
            "out_in_ratio": 0.15,
            "cost_per_1k_out": 0.4,
        },
        {
            "name": "(untagged)",
            "calls": 3,
            "monthly_usd": 30.1,
            "share": 0.2,
            "cache_hit_rate": 0.0,
            "out_in_ratio": 0.1,
            "cost_per_1k_out": 0.2,
        },
    ],
    "pct_priced": 1.0,
    "pct_attributed": 0.42,
}


class TestShowbackSerializer:
    def test_header_is_the_lld_9_5_verbatim_columns(self) -> None:
        assert showback.to_csv(ARTIFACT).startswith(HEADER + "\r\n")

    def test_golden_bytes_exact(self) -> None:
        expected = (
            HEADER + "\r\n"
            "model,claude-opus-4-8,10,100.123456,0.6651234,42% of spend carries a route tag\r\n"
            "model,gpt-5.6-luna,5,50.376544,0.3348766,42% of spend carries a route tag\r\n"
            "route,chat,12,120.4,0.8,42% of spend carries a route tag\r\n"
            "route,(untagged),3,30.1,0.2,42% of spend carries a route tag\r\n"
        )
        assert showback.to_csv(ARTIFACT) == expected

    def test_figures_are_verbatim_not_re_rounded(self) -> None:
        csv_text = showback.to_csv(ARTIFACT)
        # money/share figures keep every decimal the artifact pinned — no
        # rounding to 2dp, no truncation (FR-38 "byte-for-byte" acceptance)
        assert "100.123456" in csv_text
        assert "0.6651234" in csv_text

    def test_dimension_and_model_before_route_ordering(self) -> None:
        rows = showback.to_csv(ARTIFACT).splitlines()[1:]
        dims = [r.split(",")[0] for r in rows]
        assert dims == ["model", "model", "route", "route"]

    def test_empty_allocation_is_header_plus_honest_comment_only(self) -> None:
        empty = {"by_model": [], "by_route": [], "pct_attributed": 0.0}
        lines = showback.to_csv(empty).splitlines()
        assert lines == [HEADER, lines[1]]
        assert lines[1].startswith("#")

    def test_missing_slice_keys_degrade_to_the_empty_state_not_a_crash(self) -> None:
        lines = showback.to_csv({}).splitlines()
        assert lines[0] == HEADER
        assert lines[1].startswith("#")

    def test_caveat_reflects_pct_attributed_on_every_row(self) -> None:
        artifact = {**ARTIFACT, "pct_attributed": 0.07}
        rows = showback.to_csv(artifact).splitlines()[1:]
        assert all(row.endswith("7% of spend carries a route tag") for row in rows)
