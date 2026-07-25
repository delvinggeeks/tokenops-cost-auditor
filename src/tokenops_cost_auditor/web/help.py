"""Help registry loader (PLAN-V15 V-D4g; R-PERSONA + R-CLARITY).

ONE source for widget popovers, Guide pages, section purpose lines and the
docs-site pages that mirror them — popovers and docs cannot drift.

Threshold values inside `why` are {placeholders} filled from live Settings
at render time: tuning a detector threshold updates the help text with no
edit here (T-HELP-06). A hard-coded number in a `why` string is a test
failure, not a style opinion.

R-PERSONA jargon law: `plain` is the only phrasing allowed at headline
depth; `technical` belongs to depth (c).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from tokenops_cost_auditor.config import Settings

REGISTRY_PATH = Path(__file__).parent / "help_registry.yaml"
# Fixed order of depth (c) on every finding (R-CLARITY §1).
DEPTH_C_ORDER = ("why", "evidence", "fix", "verify", "methodology")


@dataclass(frozen=True)
class DetectorHelp:
    key: str
    plain: str  # headline depth — never a detector id
    summary: str  # plain-English "what this means", common-man; leads the finding
    technical: str  # depth (c) only
    why: str  # thresholds already rendered from Settings
    fix: str
    verify: str
    methodology_url: str


@lru_cache
def _raw() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    return data


def widget(key: str) -> dict[str, str]:
    """Widget title, 'what this tells you' line and the "?" popover triple."""
    entry = _raw()["widgets"].get(key)
    if entry is None:
        raise KeyError(f"help registry has no widget '{key}'")
    return dict(entry)


def purpose(destination: str) -> str:
    """One plain sentence of 'what you do here' (R-CLARITY §3)."""
    entry = _raw()["destinations"].get(destination)
    if entry is None:
        raise KeyError(f"help registry has no destination '{destination}'")
    return str(entry["purpose"])


def detector(key: str, settings: Settings) -> DetectorHelp:
    """Detector help with thresholds rendered from LIVE settings."""
    entry = _raw()["detectors"].get(key)
    if entry is None:
        raise KeyError(f"help registry has no detector '{key}'")
    return DetectorHelp(
        key=key,
        plain=entry["plain"],
        summary=entry["summary"],
        technical=entry["technical"],
        why=_render_thresholds(str(entry["why"]), settings),
        fix=entry["fix"],
        verify=entry["verify"],
        methodology_url=entry["methodology_url"],
    )


def detector_summary(key: str) -> str:
    """The plain-English 'what this means' for a finding (no thresholds, so no
    Settings needed). Common-man phrasing that LEADS the finding wherever it is
    read — findings list, drawer, preview (founder walkthrough 2026-07-25)."""
    entry = _raw()["detectors"].get(key)
    return str(entry["summary"]) if entry else ""


def detector_plain(key: str) -> str:
    """Headline-depth phrasing only (no thresholds, so no Settings needed).
    Templates use this wherever a finding is named above depth (c)."""
    entry = _raw()["detectors"].get(key)
    return str(entry["plain"]) if entry else key


def _render_thresholds(text: str, settings: Settings) -> str:
    """Fill {placeholders} from live Settings. A malformed or unknown
    placeholder must never take a page down (V-D4 cold-review f.6): the raw
    text is returned instead, and T-HELP-05/06 catch it in CI."""
    try:
        return text.format(**_threshold_values(settings))
    except KeyError, IndexError, ValueError:
        return text


def wizard(provider: str) -> dict[str, str]:
    """Connect-wizard copy. Same registry as everything else, so the jargon
    guard and T-HELP coverage apply (R-MAGIC-CONNECT §3)."""
    entry = _raw()["wizard"].get(provider)
    if entry is None:
        raise KeyError(f"help registry has no wizard copy for '{provider}'")
    return dict(entry)


def wizard_providers() -> list[str]:
    return list(_raw()["wizard"])


def guide_page(slug: str) -> dict[str, str]:
    entry = _raw()["guide_pages"].get(slug)
    if entry is not None:
        return dict(entry)
    # R-SYSTEM-TEST journey fix (2026-07-23): widget "learn more" links can
    # name slugs with no hand-written guide page — seven shipped as 404s on
    # the dashboard. Those slugs now render FROM the widget's own registry
    # entry (V-D4g single-source law: popovers and pages cannot drift), so a
    # link the app emits is a page the app serves, by construction.
    for w in _raw()["widgets"].values():
        if str(w.get("link", "")).rstrip("/").endswith("/" + slug):
            body = " ".join(str(w[k]) for k in ("what", "where", "do") if w.get(k))
            return {"title": str(w["title"]), "audience": "Both", "body": body}
    raise KeyError(f"help registry has no guide page '{slug}'")


def guide_index() -> list[dict[str, str]]:
    """Hand-written pages PLUS every widget-synthesized guide slug
    (R-REACHABILITY, 2026-07-23: /guide/benchmarks existed but its only
    inbound link sat on a dormant widget — a declared page must be
    reachable from the index, always)."""
    pages = [{"slug": s, **p} for s, p in _raw()["guide_pages"].items()]
    listed = {p["slug"] for p in pages}
    for w in _raw()["widgets"].values():
        link = str(w.get("link", ""))
        if link.startswith("/guide/"):
            slug = link.removeprefix("/guide/")
            if slug not in listed:
                listed.add(slug)
                pages.append({"slug": slug, "title": str(w["title"]), "audience": "Both"})
    return pages


def detector_keys() -> list[str]:
    return list(_raw()["detectors"])


def _threshold_values(settings: Settings) -> dict[str, object]:
    """Every placeholder a `why` string may use. Sourced from Settings so
    help text and detector behaviour can never disagree."""
    return {
        "d1_short_completion_t": settings.d1_short_completion_t,
        "d2_cache_min_repeats": settings.d2_cache_min_repeats,
        "d2_cache_min_prompt_tokens": settings.d2_cache_min_prompt_tokens,
        "d2_suffix_haircut": settings.d2_suffix_haircut,
        "d3_bloat_mult": settings.d3_bloat_mult,
        "d4_dup_min": settings.d4_dup_min,
        "d4_window_s": settings.d4_window_s,
        "d5_max_ratio": settings.d5_max_ratio,
        "d6_loop_min": settings.d6_loop_min,
        "d6_small_completion_t": settings.d6_small_completion_t,
        "d6_run_window_s": settings.d6_run_window_s,
        "d6_batch_sz": settings.d6_batch_sz,
        # rendered as a percentage so the help text reads naturally ("50%")
        "d8_concentration_min_share_pct": f"{settings.d8_concentration_min_share * 100:.0f}%",
        "d9_min_cache_write_tokens": settings.d9_min_cache_write_tokens,
        "d10_min_days": settings.d10_min_days,
        "d10_z_threshold": settings.d10_z_threshold,
        "d10_spike_mult": settings.d10_spike_mult,
    }
