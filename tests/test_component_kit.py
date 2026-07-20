"""R-DESIGN-TOKENS-2 §3/§4 — the kit exists, screens compose it, and the three
signatures survive a re-skin.

Why these are tests and not a style guide: a kit only pays for itself if
divergence is *caught*. One screen hand-rolling a table is invisible in review
and fatal at the next redesign, because the mood swap stops being free.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

REPO = Path(__file__).parents[1]
TEMPLATES = REPO / "src/tokenops_cost_auditor/web/templates"
KIT = TEMPLATES / "kit/_kit.html"
CSS = REPO / "src/tokenops_cost_auditor/web/static/wa-design.css"


def kit_text() -> str:
    return KIT.read_text(encoding="utf-8")


def macros() -> set[str]:
    return set(re.findall(r"{%\s*macro\s+([a-z_0-9]+)\(", kit_text()))


class TestTheKitIsComplete:
    REQUIRED: ClassVar[set[str]] = {
        "button",
        "surface_open",
        "surface_close",
        "stat",
        "savings_hero",
        "pipeline_ribbon",
        "table_open",
        "table_close",
        "drawer",
        "drawer_toggle",
        "finding_row",
        "finding_detail",
        "finding_summary",
        "alert_row",
        "source_card",
        "wizard_steps",
        "help_popover",
        "tour_spot",
        "field",
        "empty_state",
        "error_state",
        "computing_label",
        "skeleton",
    }

    def test_every_named_component_exists(self) -> None:
        missing = self.REQUIRED - macros()
        assert not missing, f"component kit is missing: {sorted(missing)}"

    def test_finding_card_has_all_three_renderers(self) -> None:
        """§3 calls FindingCard 'the atom, 3 renderers'. One component so a
        finding cannot say different things in a row, a drawer and a report."""
        assert {"finding_row", "finding_detail", "finding_summary"} <= macros()

    def test_field_covers_every_primitive_type(self) -> None:
        text = kit_text()
        for kind in ("money", "int", "enum", "bool", "file"):
            assert kind in text, f"field primitive missing a {kind!r} branch"


class TestMoneyNeverShimmers:
    """§3 + R-LOOK-FINAL 3c. A pulsing placeholder where a dollar figure
    belongs reads as a number still settling, and an audit product cannot
    afford a customer believing a figure moved when it was merely loading.
    """

    def test_an_explicit_computing_state_exists_instead(self) -> None:
        assert "computing_label" in macros()
        assert "computing" in CSS.read_text(encoding="utf-8")

    def test_the_skeleton_css_never_targets_money(self) -> None:
        css = CSS.read_text(encoding="utf-8")
        for line in css.splitlines():
            if ".skel" in line or ".skeleton" in line:
                assert "money" not in line, f"skeleton styling reaches money: {line.strip()!r}"

    def test_no_shimmer_animation_ships_at_all(self) -> None:
        """A shimmer keyframe existing anywhere is an invitation to use it.

        Matches on @keyframes NAMES and on animation applied to skeleton
        selectors — not on the word, which appears in the rationale comments
        explaining why we do not do this."""
        css = CSS.read_text(encoding="utf-8")
        names = [n.lower() for n in re.findall(r"@keyframes\s+([A-Za-z0-9_-]+)", css)]
        banned = [n for n in names if "shimmer" in n or "skeleton" in n]
        assert not banned, f"shimmer/skeleton keyframes ship: {banned}"
        for line in css.splitlines():
            if ".skel" in line:
                assert "animation" not in line, f"skeleton is animated: {line.strip()!r}"

    def test_the_money_class_carries_no_shadow(self) -> None:
        """R-LOOK-FINAL 1b: dollars never sit inside soft shadows."""
        css = CSS.read_text(encoding="utf-8")
        starts = [m.start() for m in re.finditer(r"^\.money \{", css, re.M)]
        assert len(starts) == 1, (
            f".money is declared {len(starts)} times — a stale duplicate cascades "
            f"its own font onto every figure (this is how money kept rendering in "
            f"the superseded serif after R-LOOK-FINAL)"
        )
        block = css[starts[0] : css.index("}", starts[0])]
        assert "box-shadow: none" in block, ".money must explicitly refuse depth"


class TestTheThreeSignatures:
    """§4 — pipeline ribbon, accountant's double rule, Applied→headline
    money-flow. They are brand, not theme: a re-skin may restyle them and may
    never drop them."""

    def test_pipeline_ribbon_exists_in_kit_and_css(self) -> None:
        assert "pipeline_ribbon" in macros()
        assert ".ribbon" in CSS.read_text(encoding="utf-8")

    def test_the_double_rule_is_a_real_double_rule(self) -> None:
        """Not a styling detail — the accountant's convention for a verified
        total. A single hairline would silently demote it."""
        css = CSS.read_text(encoding="utf-8")
        starts = [m.start() for m in re.finditer(r"^\.total-rule \{", css, re.M)]
        assert len(starts) == 1, f".total-rule declared {len(starts)} times"
        block = css[starts[0] : css.index("}", starts[0])]
        assert "double" in block, "the double rule must actually be a double border"
        assert "--rule-strong" in block, "it must use the strong rule role, not --rule"

    def test_savings_hero_pairs_the_total_with_the_rule(self) -> None:
        """The rule belongs UNDER the verified total. Shipping the hero without
        it would drop a signature while looking fine."""
        text = kit_text()
        hero = text[text.index("macro savings_hero") : text.index("macro pipeline_ribbon")]
        assert "money-hero" in hero and "total-rule" in hero


class TestScreensComposeTheKit:
    def test_app_screens_do_not_hand_roll_tables(self) -> None:
        """A bespoke <table> on a screen is the exact divergence §3 forbids.
        Kit-composed screens import the macros instead."""
        # §3 binds NEW screens. These predate the kit and are queued to migrate;
        # the list may only ever shrink, which the test below enforces.
        pre_kit = {
            "app/billing.html",
            "app/settings.html",
            "app/sources.html",
            "app/_finding_drawer.html",
            "app/findings.html",
            "app/alerts.html",
            "app/widgets/_top_findings.html",
        }
        offenders = []
        for path in (TEMPLATES / "app").rglob("*.html"):
            rel = path.relative_to(TEMPLATES).as_posix()
            if rel in pre_kit:
                continue
            text = path.read_text(encoding="utf-8")
            if "<table" in text and "kit/_kit.html" not in text:
                offenders.append(rel)
        assert not offenders, (
            f"screens hand-rolling tables instead of composing the kit: {offenders}. "
            f"Import kit/_kit.html and use table_open/table_close, or the next "
            f"mood swap stops being free for these screens."
        )

    def test_the_migration_allowlist_only_shrinks(self) -> None:
        """The ratchet. Without it the allowlist is just permission, and every
        pre-kit screen stays pre-kit forever — which is exactly how a component
        kit ends up as documentation nobody follows.

        An entry that no longer hand-rolls a table has migrated: delete it from
        the list. An entry naming a file that no longer exists is stale. Either
        way the list must not carry names it no longer earns.
        """
        pre_kit = {
            "app/billing.html",
            "app/settings.html",
            "app/sources.html",
            "app/_finding_drawer.html",
            "app/findings.html",
            "app/alerts.html",
            "app/widgets/_top_findings.html",
        }
        stale = []
        for rel in sorted(pre_kit):
            path = TEMPLATES / rel
            if not path.exists():
                stale.append(f"{rel} (file gone)")
                continue
            text = path.read_text(encoding="utf-8")
            if "<table" not in text or "kit/_kit.html" in text:
                stale.append(f"{rel} (migrated — remove it from the allowlist)")
        assert not stale, "pre-kit allowlist entries that no longer apply: " + ", ".join(stale)
