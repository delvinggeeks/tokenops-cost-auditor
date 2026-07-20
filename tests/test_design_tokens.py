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


def mood_tokens(mood: str) -> dict[str, str]:
    """Every --token: value declared for a mood's selector block."""
    css = (STATIC / "wa-design.css").read_text(encoding="utf-8")
    sel = ':root,\n[data-mood="sanchaya"]' if mood == "sanchaya" else f'[data-mood="{mood}"]'
    i = css.index(sel)
    body = css[i : css.index("\n}", i)]
    return {m[0]: m[1].strip() for m in re.findall(r"(--[a-z0-9-]+):([^;]+);", body)}


def rgb(value: str) -> tuple[int, int, int]:
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def _lin(c: int) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def luminance(value: str) -> float:
    r, g, b = rgb(value)
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(fg: str, bg: str) -> float:
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


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
        "--control-depth",
    )
    MOODS = ("sanchaya", "aura")

    def test_every_role_is_defined(self) -> None:
        css = (STATIC / "wa-design.css").read_text(encoding="utf-8")
        missing = [r for r in self.ROLES if f"{r}:" not in css]
        assert not missing, f"role tokens missing from the map: {missing}"

    def test_both_shipping_moods_are_selectable(self) -> None:
        css = (STATIC / "wa-design.css").read_text(encoding="utf-8")
        for mood in self.MOODS:
            assert f'[data-mood="{mood}"]' in css, f"mood {mood!r} not selectable"

    def test_moods_define_identical_token_names(self) -> None:
        """The symmetry IS the feature: same names, different values is what
        makes the topbar toggle free and a third mood a value sheet. A token
        present in one mood and missing in another paints half a screen."""
        for a, b in zip(self.MOODS, self.MOODS[1:], strict=False):
            ka, kb = set(mood_tokens(a)), set(mood_tokens(b))
            assert ka == kb, (
                f"token names diverge between {a} and {b}: "
                f"only in {a}: {sorted(ka - kb)} · only in {b}: {sorted(kb - ka)}"
            )


class TestDepthIsSplitByPurpose:
    """R-LOOK-FINAL 1a/1b — neumorphic depth on CONTROLS AND WIDGETS; data
    surfaces, tables, charts and every money figure stay flat-crisp.

    The reason is legibility, not taste: a bevel softens the edge of a numeral,
    and money is the one thing this product cannot afford to render ambiguously.
    """

    CONTROL_HINTS = (
        ".btn",
        "input",
        "select",
        "textarea",
        ".chip",
        ".stat",
        ".step",
        ".sidebar a",
        ".rail a",
        ".toggle",
        ".source-card",
        ".widget-head",
        ".nav",
        ".tab",
        "summary",
        "--control-depth",
    )
    DATA_HINTS = (
        ".ledger",
        "table",
        " td",
        " th",
        ".money",
        ".num",
        ".chart",
        ".evidence",
        ".total-rule",
    )

    def test_no_paired_inset_on_data_money_or_table_surfaces(self) -> None:
        css = (STATIC / "wa-design.css").read_text(encoding="utf-8")
        offenders = []
        for rule in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            selector, body = rule[0].strip(), rule[1]
            if "box-shadow" not in body or body.count("inset") < 2:
                continue
            if any(h in selector for h in self.CONTROL_HINTS):
                continue  # controls are EXEMPT — the family clause allows it
            if any(h in selector for h in self.DATA_HINTS):
                offenders.append(selector)
        assert not offenders, (
            f"paired-inset (neumorphic) depth on data/money/table surfaces: {offenders}. "
            f"A bevel eats the edge of a numeral; dollars stay flat-crisp "
            f"(R-LOOK-FINAL 1b). Controls and widget chrome are exempt."
        )

    def test_control_depth_exists_and_is_paired(self) -> None:
        """The converse: controls SHOULD carry it, or we have quietly shipped
        the austere look under a new name."""
        for mood in ("sanchaya", "aura"):
            val = mood_tokens(mood).get("--control-depth", "")
            assert val.count("inset") >= 2, f"{mood}: --control-depth is not paired-inset"


class TestContrastMeetsAA:
    """R-LOOK-FINAL 3a — AA in EVERY mood, computed rather than eyeballed.

    A dark mood is exactly where contrast quietly fails: the values look
    confident on a bright monitor and disappear on a dim one.
    """

    PAIRS = (
        ("--ink", "--ground", 4.5),
        ("--ink", "--surface", 4.5),
        ("--ink", "--surface-raised", 4.5),
        ("--ink-soft", "--surface", 4.5),
        ("--ink-soft", "--ground", 4.5),
        ("--on-accent", "--accent", 4.5),
        ("--money", "--surface", 4.5),
        ("--verified", "--verified-bg", 4.5),
        ("--estimate", "--estimate-bg", 4.5),
        ("--waste", "--waste-bg", 4.5),
    )

    def test_every_text_pair_meets_aa_in_every_mood(self) -> None:
        failures = []
        for mood in ("sanchaya", "aura"):
            tok = mood_tokens(mood)
            for fg, bg, minimum in self.PAIRS:
                if fg not in tok or bg not in tok:
                    continue
                ratio = contrast(tok[fg], tok[bg])
                if ratio < minimum:
                    failures.append(f"{mood}: {fg} on {bg} = {ratio:.2f}:1 (need {minimum})")
        assert not failures, "AA contrast failures:\n  " + "\n  ".join(failures)


class TestSemanticColourLaw:
    def test_meanings_never_remap_only_values(self) -> None:
        """verified=green, estimate=amber, waste=red in EVERY mood. Values move
        between moods; meanings do not. A mood that made 'waste' green would be
        a lie the tokens told for us."""
        for mood in ("sanchaya", "aura"):
            tok = mood_tokens(mood)
            v, e, w = (rgb(tok[k]) for k in ("--verified", "--estimate", "--waste"))
            assert v[1] > v[0], f"{mood}: --verified is not green-dominant {v}"
            assert w[0] > w[1], f"{mood}: --waste is not red-dominant {w}"
            assert e[0] > e[2] and e[1] > e[2], f"{mood}: --estimate is not amber {e}"
