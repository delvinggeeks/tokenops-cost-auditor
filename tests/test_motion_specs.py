"""R-MOTION-SPEC — design/MOTION-SPECS.md is a gate artifact, so it has to be
kept honest by something other than good intentions.

A spec sheet that nobody checks drifts from the code within a milestone, and
then the ux gate is reviewing fiction. These tests bind the two together.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).parents[1]
SPECS = REPO / "design/MOTION-SPECS.md"
STATIC = REPO / "src/tokenops_cost_auditor/web/static"
STYLESHEETS = ("wa-design.css", "wa-public.css")


def stylesheet_text() -> dict[str, str]:
    return {n: (STATIC / n).read_text(encoding="utf-8") for n in STYLESHEETS}


class TestEveryEffectIsSpecified:
    def test_every_keyframe_animation_is_on_the_spec_sheet(self) -> None:
        """An @keyframes that nobody wrote a spec for is motion that never
        passed the 'does this serve comprehension?' question."""
        spec = SPECS.read_text(encoding="utf-8")
        undocumented = []
        for name, css in stylesheet_text().items():
            for kf in re.findall(r"@keyframes\s+([A-Za-z0-9_-]+)", css):
                # the sheet may name the effect or the keyframe; accept either
                if kf not in spec and kf.replace("-", " ") not in spec.lower():
                    undocumented.append(f"{name}:@keyframes {kf}")
        assert not undocumented, (
            f"motion in the code with no entry in design/MOTION-SPECS.md: {undocumented}. "
            f"Specify trigger/behavior/duration/reduced-motion/tokens, or delete the effect."
        )

    def test_the_spec_sheet_is_not_empty_of_effects(self) -> None:
        """Guard against the sheet being gutted to make the check above pass."""
        spec = SPECS.read_text(encoding="utf-8")
        rows = re.findall(r"^\|\s*[ABC]\d+\s*\|", spec, re.M)
        assert len(rows) >= 10, f"only {len(rows)} specified effects — sheet looks gutted"


class TestReducedMotionIsEnforcedOnce:
    def test_the_global_block_exists_and_uses_important(self) -> None:
        """The block is `*` + `!important` on purpose: that is what lets a new
        stylesheet (wa-public.css, and whatever comes next) inherit the
        protection instead of each shipping its own copy and one of them
        eventually forgetting."""
        css = stylesheet_text()["wa-design.css"]
        block = re.search(r"@media \(prefers-reduced-motion: reduce\)\s*\{(.+?)\n\}", css, re.S)
        assert block, "wa-design.css must carry the global reduced-motion block"
        body = block.group(1)
        assert "*" in body
        assert "animation: none !important" in body
        assert "transition: none !important" in body

    def test_the_countup_resolves_to_its_final_value(self) -> None:
        """The one effect where 'no animation' is not enough: without this the
        hero number would render 0 for reduced-motion users — the single most
        important figure on the page, wrong."""
        css = stylesheet_text()["wa-design.css"]
        block = re.search(r"@media \(prefers-reduced-motion: reduce\)\s*\{(.+?)\n\}", css, re.S)
        assert block and "--n: var(--target)" in block.group(1)

    def test_new_stylesheets_do_not_duplicate_the_block(self) -> None:
        """One definition, one place (R-MOTION-SPEC: tokens only, no copies)."""
        assert "prefers-reduced-motion" not in stylesheet_text()["wa-public.css"], (
            "wa-public.css must inherit the global block from wa-design.css, not "
            "carry a second copy that can drift out of step"
        )
