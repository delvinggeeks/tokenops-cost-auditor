"""R-DESIGN-TOKENS-2 §1 — role tokens are the only place a colour may live.

The rule is worth enforcing mechanically because it fails silently: one
hardcoded hue in a component looks fine today and is invisible until a mood
swap paints half a screen correctly and the other half not at all. A grep is
cheap; discovering it during a theme rollout is not.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).parents[1]
STATIC = REPO / "src/tokenops_cost_auditor/web/static"
TEMPLATES = REPO / "src/tokenops_cost_auditor/web/templates"

HEX = re.compile(r"#[0-9A-Fa-f]{3,8}\b")

# Surfaces that predate the token map and are scheduled onto it by name. Each
# exemption cites the milestone that removes it, so "temporary" stays checkable
# rather than becoming permanent by forgetting.
EXEMPT = {
    "base.html": "landing shell — replaced at R-LANDING-2",
    "_report_style.html": "report/PDF styles — WP-REPORT-VISUAL, its own gated milestone",
}


def token_block_and_body(css: str) -> tuple[str, str]:
    """Split a stylesheet into its declaration block(s) and everything else."""
    end = css.rindex("}", 0, css.index("/* ====", css.index(":root")))
    return css[: end + 1], css[end + 1 :]


class TestNoRawColoursOutsideTheTokenBlock:
    def test_wa_design_css_body_is_hex_free(self) -> None:
        css = (STATIC / "wa-design.css").read_text(encoding="utf-8")
        _, body = token_block_and_body(css)
        found = HEX.findall(body)
        assert not found, (
            f"raw colours outside the role-token block in wa-design.css: {sorted(set(found))}. "
            f"Add a role token instead — a hardcoded hue survives a mood swap and "
            f"repaints half a screen (R-DESIGN-TOKENS-2 §1)."
        )

    def test_wa_public_css_is_hex_free(self) -> None:
        css = (STATIC / "wa-public.css").read_text(encoding="utf-8")
        found = HEX.findall(css)
        assert not found, f"raw colours in wa-public.css: {sorted(set(found))}"

    def test_templates_are_hex_free_except_named_exemptions(self) -> None:
        offenders: dict[str, list[str]] = {}
        for path in TEMPLATES.rglob("*.html"):
            if path.name in EXEMPT:
                continue
            found = HEX.findall(path.read_text(encoding="utf-8"))
            if found:
                offenders[path.relative_to(TEMPLATES).as_posix()] = sorted(set(found))
        assert not offenders, (
            f"raw colours in templates: {offenders}. Use a role token, or add a "
            f"dated exemption naming the milestone that removes it."
        )

    def test_exemptions_still_exist_and_still_need_exempting(self) -> None:
        """An exemption for a file that no longer has colours is stale, and a
        stale exemption is how a real violation later slips through unnoticed."""
        for name, why in EXEMPT.items():
            matches = list(TEMPLATES.rglob(name))
            assert matches, f"exemption for a file that no longer exists: {name} ({why})"
            assert HEX.search(matches[0].read_text(encoding="utf-8")), (
                f"{name} no longer contains raw colours — drop its exemption ({why})"
            )


class TestRoleTokensExist:
    ROLES = (
        "--ground",
        "--surface",
        "--surface-raised",
        "--ink",
        "--ink-soft",
        "--rule",
        "--rule-strong",
        "--accent",
        "--on-accent",
        "--money",
        "--verified",
        "--estimate",
        "--waste",
        "--lift-1",
        "--lift-2",
        "--lift-3",
    )

    def test_every_role_is_defined(self) -> None:
        css = (STATIC / "wa-design.css").read_text(encoding="utf-8")
        missing = [r for r in self.ROLES if f"{r}:" not in css]
        assert not missing, f"role tokens missing from the map: {missing}"

    def test_a_second_mood_would_be_a_value_swap_only(self) -> None:
        """§2: theming is a data-mood attribute swapping VALUES. The selector
        has to already accept a mood or 'Night Audit' becomes a refactor
        instead of a value sheet."""
        css = (STATIC / "wa-design.css").read_text(encoding="utf-8")
        assert '[data-mood="ledger"]' in css, (
            "the token block must be selectable by mood, or promoting Night Audit "
            "means touching components rather than adding values"
        )

    def test_neumorphic_depth_is_not_adopted(self) -> None:
        """A recorded, deliberate divergence from the family language: emboss
        softens numeral edges and money legibility outranks family consistency.

        Checks the CSS SIGNATURE of emboss — a shadow carrying a paired inset
        (one light, one dark) — not the word, which legitimately appears in the
        rationale comment above the tokens. Our --inner-edge is a single inset
        highlight, which is a crisp edge rather than a soft bevel.
        """
        css = (STATIC / "wa-design.css").read_text(encoding="utf-8")
        for line in css.splitlines():
            if "--lift" in line or "--inner-edge" in line:
                assert line.count("inset") <= 1, (
                    f"paired inset shadow (emboss) reintroduced: {line.strip()!r}. "
                    f"Not adopted, deliberately — re-argue it, do not add it by habit."
                )
