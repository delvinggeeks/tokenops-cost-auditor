"""R-DESIGN-TOKENS-2 §6 — UI strings are translation keys; en ships alone.

The catalogue is a value sheet like a mood: components reference keys, a
locale supplies values. These tests keep the two sides from drifting — a key
used but undefined renders as its own raw name in production (deliberate:
visible and greppable, never a 500), so the suite is where that must die.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI

from tokenops_cost_auditor.web import i18n

REPO = Path(__file__).parents[1]
TEMPLATES = REPO / "src/tokenops_cost_auditor/web/templates"
LOCALES = REPO / "src/tokenops_cost_auditor/web/locales"

USED = re.compile(r"""\bt\(\s*['"]([a-z0-9_.]+)['"]""")


def keys_used_in_templates() -> dict[str, list[str]]:
    used: dict[str, list[str]] = {}
    for path in TEMPLATES.rglob("*.html"):
        for key in USED.findall(path.read_text(encoding="utf-8")):
            used.setdefault(key, []).append(path.relative_to(TEMPLATES).as_posix())
    return used


class TestTheCatalogueAndTheTemplatesAgree:
    def test_every_key_used_resolves(self) -> None:
        catalogue = i18n.catalogue()
        missing = {k: v for k, v in keys_used_in_templates().items() if k not in catalogue}
        assert not missing, (
            f"template keys with no en entry (would render as raw key names): {missing}"
        )

    def test_no_orphan_keys_accumulate(self) -> None:
        """A key nothing references is copy nobody reviews. When a second
        locale arrives, orphans get translated for free — as dead weight."""
        used = keys_used_in_templates()
        orphans = [k for k in i18n.catalogue() if k not in used]
        assert not orphans, f"catalogue keys no template references: {orphans}"

    def test_interpolated_keys_format_cleanly(self) -> None:
        """Every {placeholder} in a value must be a real format field — a
        stray brace raises at render time, inside a request."""
        for key, value in i18n.catalogue().items():
            fields = [f for _, f, _, _ in __import__("string").Formatter().parse(value) if f]
            kwargs = {f: "x" for f in fields}
            assert i18n.t(key, **kwargs), f"{key}: {value!r} does not format"


class TestTheLayerItself:
    def test_english_ships_alone_and_deliberately(self) -> None:
        """A second locale is a full reviewed value sheet (BACKLOG: Indic
        locales), never a partial merge that leaves a screen half-translated."""
        assert sorted(p.name for p in LOCALES.glob("*.json")) == ["en.json"]

    def test_a_missing_key_is_visible_not_a_500(self) -> None:
        assert i18n.t("kit.no.such.key") == "kit.no.such.key"

    def test_the_template_env_carries_t(self, app: FastAPI) -> None:
        assert app.state.jinja.globals.get("t") is i18n.t

    def test_kit_macros_render_catalogue_strings(self, app: FastAPI) -> None:
        """Jinja imports drop the calling context; only env GLOBALS reach an
        imported macro. Until a real screen composes the kit, this is the one
        place that proves t() resolves inside it rather than 500ing."""
        tpl = app.state.jinja.from_string(
            '{% import "kit/_kit.html" as kit %}'
            '{{ kit.savings_hero("$12", computing=True) }}{{ kit.tour_spot(2, "T", "B", 5) }}'
        )
        out = tpl.render()
        assert "Recomputing your verified total" in out
        assert "Step 2 of 5" in out

    def test_the_kit_bakes_no_english_chrome(self) -> None:
        """The strings that moved out stay out. Caller-supplied copy (labels,
        headlines) is the caller's problem at wiring; the kit's own chrome
        must come from the catalogue or a second locale re-skins half a kit."""
        kit = (TEMPLATES / "kit/_kit.html").read_text(encoding="utf-8")
        for gone in (
            "Verified savings",
            "Why we flagged this",
            "How you'll know it worked",
            ">Details<",
            ">Skip<",
            ">Next<",
            '"Try again"',
            'aria-label="Progress"',
            'aria-label="Audit pipeline"',
        ):
            assert gone not in kit, f"kit chrome string regressed to a literal: {gone!r}"
