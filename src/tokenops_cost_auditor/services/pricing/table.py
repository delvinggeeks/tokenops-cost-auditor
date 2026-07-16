"""Versioned, data-driven pricing table (FR-05; four rates per founder ruling R-Q4).

Zero network imports (T-NFR-01). Rates are USD per 1M tokens.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

DEFAULT_DATA = Path(__file__).parent / "data" / "prices.yaml"


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
    # (provider, model) -> entries sorted ascending by effective_from
    _entries: dict[tuple[str, str], tuple[Rate, ...]]

    @classmethod
    def load(cls, path: Path = DEFAULT_DATA) -> PricingTable:
        raw = yaml.safe_load(path.read_text())
        entries: dict[tuple[str, str], tuple[Rate, ...]] = {}
        for provider, pdata in raw["providers"].items():
            for model, rate_list in pdata["models"].items():
                rates = []
                for item in rate_list:
                    input_rate = float(item["input"])
                    rates.append(
                        Rate(
                            input=input_rate,
                            output=float(item["output"]),
                            cache_read=float(item.get("cache_read", input_rate)),
                            cache_write=float(item.get("cache_write", input_rate)),
                            effective_from=item["effective_from"],
                        )
                    )
                rates.sort(key=lambda r: r.effective_from)
                entries[(provider.lower(), model.lower())] = tuple(rates)
        return cls(version=str(raw["version"]), _entries=entries)

    def rate(self, provider: str, model: str, on_date: date) -> Rate:
        """Latest entry with effective_from <= on_date. Model matching: exact,
        then longest key that prefixes the model id (handles dated snapshots
        like claude-haiku-4-5-20251001)."""
        provider = provider.lower()
        model = model.lower()
        rates = self._entries.get((provider, model))
        if rates is None:
            candidates = [
                key_model
                for (key_provider, key_model) in self._entries
                if key_provider == provider and model.startswith(key_model)
            ]
            if not candidates:
                raise PricingGapError(provider, model, on_date)
            rates = self._entries[(provider, max(candidates, key=len))]

        applicable = [r for r in rates if r.effective_from <= on_date]
        if not applicable:
            raise PricingGapError(provider, model, on_date)
        return applicable[-1]
