"""Versioned, data-driven pricing table (FR-05; four rates per founder ruling R-Q4).

Zero network imports (T-NFR-01). Rates are USD per 1M tokens.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

DEFAULT_DATA = Path(__file__).parent / "data" / "prices.yaml"
# Machine-managed overlay (R-LIVE-PRICING): the autonomous pricing sync writes
# auto-fetched, gate-validated, effective-dated rows here — NEVER into the
# hand-commented base file. Merged append-only with the base at load time; each
# (provider, model) history is base rows + overlay rows sorted by effective_from,
# so an audit still prices deterministically at the rate in effect on its date.
# Absent overlay => identical behaviour to base-only (backward compatible).
# Reading a second local YAML keeps services/pricing network-free (T-NFR-01).
#
# PRICING_OVERLAY_PATH points this at a PERSISTENT volume in prod
# (/data/reports/.ops/...): the package dir is inside the container's ephemeral
# filesystem, so a deploy/recreate would otherwise wipe every auto-priced rate
# until the next cover run (founder incident 2026-07-22). Unset (dev/tests) =>
# the package dir, unchanged.
_OVERLAY_ENV = os.environ.get("PRICING_OVERLAY_PATH")
AUTO_DATA = (
    Path(_OVERLAY_ENV) if _OVERLAY_ENV else Path(__file__).parent / "data" / "prices.auto.yaml"
)


class PricingGapError(Exception):
    """Model (or date) not covered by the table. The audit continues; the report
    lists unpriced models (docs/03-LLD.md §8)."""

    def __init__(self, provider: str, model: str, on_date: date) -> None:
        self.provider = provider
        self.model = model
        self.on_date = on_date
        super().__init__(f"no rate for {provider}/{model} on {on_date.isoformat()}")


@dataclass(frozen=True)
class Rate:
    """USD per 1M tokens. cache_write defaults to the input rate (zero write
    premium) when a provider does not bill cache writes separately (R-Q4)."""

    input: float
    output: float
    cache_read: float
    cache_write: float
    effective_from: date


@dataclass(frozen=True)
class PricingTable:
    version: str
    last_verified: date | None
    # (provider, model) -> entries sorted ascending by effective_from
    _entries: dict[tuple[str, str], tuple[Rate, ...]]

    @classmethod
    def load(cls, path: Path = DEFAULT_DATA, overlay: Path | None = AUTO_DATA) -> PricingTable:
        raw = yaml.safe_load(path.read_text())
        # (provider, model) -> mutable list of Rate, base first then overlay.
        acc: dict[tuple[str, str], list[Rate]] = {}
        last_verified = raw.get("last_verified")
        cls._ingest(raw, acc)
        # Merge the machine-managed overlay if present (R-LIVE-PRICING). Its rows
        # are appended to each model's history and the whole list re-sorted by
        # effective_from below, so overlay + base interleave correctly by date.
        if overlay is not None and overlay.exists():
            over_raw = yaml.safe_load(overlay.read_text()) or {}
            # A human base row ALWAYS wins a same-date tie: the overlay may only
            # ADD later-dated rates, never override a rate a human set for that
            # exact date (money-math safety — cold-review f.1). Auto rows still
            # supersede via a strictly-later effective_from (the freshness intent).
            protected = {(key, r.effective_from) for key, rates in acc.items() for r in rates}
            cls._ingest(over_raw, acc, protect=protected)
            over_verified = over_raw.get("last_verified")
            # Freshest verification date wins (daily auto-sync keeps this current).
            if over_verified is not None and (
                last_verified is None or over_verified > last_verified
            ):
                last_verified = over_verified
        entries = {
            key: tuple(sorted(rates, key=lambda r: r.effective_from)) for key, rates in acc.items()
        }
        return cls(
            version=str(raw["version"]),
            last_verified=last_verified,
            _entries=entries,
        )

    @staticmethod
    def _ingest(
        raw: dict[str, Any],
        acc: dict[tuple[str, str], list[Rate]],
        protect: set[tuple[tuple[str, str], date]] | None = None,
    ) -> None:
        """Fold one rate-card document's rows into the accumulator. Shared by the
        base file and the overlay so both honour identical schema + defaults.
        A row whose (key, effective_from) is in `protect` is dropped — used to
        stop an overlay row from overriding a same-date base row."""
        for provider, pdata in (raw.get("providers") or {}).items():
            for model, rate_list in (pdata.get("models") or {}).items():
                key = (provider.lower(), model.lower())
                bucket = acc.setdefault(key, [])
                for item in rate_list:
                    if protect is not None and (key, item["effective_from"]) in protect:
                        continue
                    input_rate = float(item["input"])
                    bucket.append(
                        Rate(
                            input=input_rate,
                            output=float(item["output"]),
                            cache_read=float(item.get("cache_read", input_rate)),
                            cache_write=float(item.get("cache_write", input_rate)),
                            effective_from=item["effective_from"],
                        )
                    )

    def rate(self, provider: str, model: str, on_date: date) -> Rate:
        """Latest entry with effective_from <= on_date. Model matching: exact,
        else key + dated-snapshot suffix ('-2...'), longest key wins — handles
        claude-haiku-4-5-20251001 without letting an unlisted sibling like
        gpt-5.4-turbo silently take gpt-5.4's rates (boundary rule; see NOTES)."""
        provider = provider.lower()
        model = model.lower()
        rates = self._entries.get((provider, model))
        if rates is None:
            # "-2" assumes 2000s-era date suffixes (e.g. -20251001). A non-date
            # sibling id starting "-2" would false-match; accepted residual risk,
            # revisit before year 3000 (G3 cold-reviewer f.5).
            candidates = [
                key_model
                for (key_provider, key_model) in self._entries
                if key_provider == provider and model.startswith(key_model + "-2")
            ]
            if not candidates:
                raise PricingGapError(provider, model, on_date)
            rates = self._entries[(provider, max(candidates, key=len))]

        applicable = [r for r in rates if r.effective_from <= on_date]
        if not applicable:
            raise PricingGapError(provider, model, on_date)
        return applicable[-1]
