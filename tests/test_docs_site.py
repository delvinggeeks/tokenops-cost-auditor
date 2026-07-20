"""D-DOCS tests — legal single-sourcing (MP-9) and docs-site invariants.

The web pages under templates/legal/ are the binding copies; docs-site/legal/
mirrors them. These tests fail when the two drift on the clauses that matter,
and pin the docs-site stats policy (docs/09 §6: attributed figures only).
"""

import re
from pathlib import Path

REPO = Path(__file__).parents[1]
DOCS = REPO / "docs-site"
TEMPLATES = REPO / "src/tokenops_cost_auditor/web/templates/legal"

FR23 = "analyzed then deleted; nothing retained beyond 7 days; never used for training"


def bold_clauses(markdown_text: str) -> list[str]:
    return re.findall(r"\*\*([^*]+)\*\*", markdown_text)


def strong_clauses(html_text: str) -> list[str]:
    return re.findall(r"<strong>([^<]+)</strong>", html_text)


class TestMP9LegalSingleSourcing:
    def test_privacy_fr23_verbatim_in_both(self) -> None:
        web = (TEMPLATES / "privacy.html").read_text(encoding="utf-8")
        docs = (DOCS / "legal/privacy.md").read_text(encoding="utf-8")
        # the web page uses typographic quotes around the same string
        assert FR23 in web.replace("“", '"').replace("”", '"').replace("\n", " ").replace(
            "  ", " "
        ) or FR23 in re.sub(r"\s+", " ", web)
        assert FR23 in re.sub(r"\s+", " ", docs)

    def test_fr23_verbatim_in_terms_too(self) -> None:
        """Terms PARAPHRASED the data promise — "nothing IS retained… YOUR DATA
        IS never used" — while privacy.html and every other surface quoted the
        canonical string. A binding document restating a published promise in
        its own words is the same defect class as the Terms page quoting a price
        we do not charge, and no test covered it (v4 ux gate f.4)."""
        for path in (
            TEMPLATES / "terms.html",
            DOCS / "legal/terms.md",
        ):
            text = re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))
            assert FR23 in text, f"{path}: FR-23 must appear verbatim, not paraphrased"

    def test_clause_structure_matches(self) -> None:
        """Every bold clause heading on a web legal page appears in its docs mirror."""
        for name in ("terms", "privacy", "dpa"):
            web = re.sub(r"\s+", " ", (TEMPLATES / f"{name}.html").read_text(encoding="utf-8"))
            docs = re.sub(r"\s+", " ", (DOCS / f"legal/{name}.md").read_text(encoding="utf-8"))
            found = strong_clauses(web)
            # Non-vacuity: this loop asserts nothing if the template stops using
            # <strong> for clause headings, so the v4 shell rebuild could have
            # silently disabled the guard rather than failing it.
            assert len(found) >= 5, (
                f"{name}: found only {len(found)} clause headings — the MP-9 guard "
                f"is inspecting <strong> and would pass vacuously if the markup moved"
            )
            for clause in found:
                assert clause in bold_clauses(docs), (
                    f"legal drift: clause {clause!r} on web {name} page missing from "
                    f"docs-site/legal/{name}.md (MP-9 single-sourcing)"
                )

    def test_price_matches_terms(self) -> None:
        """Both legal copies must quote the price the CONFIG charges.

        This test used to pin the literal '$500 / ₹20,000' in both files. That
        passed happily while the shipped config rendered ₹45,000 at checkout —
        the test was pinning the two mirrors to each other and to a rate we do
        not charge, so it certified agreement on a wrong number. It now derives
        the expected string from the one price config, which is the only
        version of this check that can catch drift (V-D10).
        """
        from tokenops_cost_auditor.config import Settings
        from tokenops_cost_auditor.services.payments import plans

        expected = plans.one_shot_display(Settings())  # e.g. "$500 · ₹45,000"
        web = (TEMPLATES / "terms.html").read_text(encoding="utf-8")
        docs = (DOCS / "legal/terms.md").read_text(encoding="utf-8")
        # The web page renders the price from config; the static docs mirror
        # cannot, so it carries the literal and must be updated when it moves.
        assert "{{ one_shot }}" in web, "terms.html must render the price from the price config"
        assert expected in docs, (
            f"docs-site/legal/terms.md quotes a price the config does not charge; expected "
            f"{expected!r}. Update the mirror in the same commit as any price change (MP-9)."
        )


class TestDocsSiteStatsPolicy:
    def test_only_attributed_stats_no_banned_figures(self) -> None:
        """docs/09 §6: 79/31/98 must carry attribution; 40-60% and 73% are banned."""
        for page in DOCS.rglob("*.md"):
            text = page.read_text(encoding="utf-8")
            assert "40-60%" not in text and "40\u201360%" not in text, page  # en-dash variant
            assert "73%" not in text, page
            if "79%" in text or "98%" in text:
                assert "DoiT" in text or "State of FinOps" in text, (
                    f"{page}: market stat used without attribution (docs/09 §6)"
                )

    def test_fr23_verbatim_on_home(self) -> None:
        assert FR23 in (DOCS / "index.md").read_text(encoding="utf-8")

    def test_measurement_pending_never_carries_numbers(self) -> None:
        """Every MP admonition must not contain a dollar/timing figure (invented
        numbers = FAIL per DOCS-PLAN)."""
        for page in DOCS.rglob("*.md"):
            text = page.read_text(encoding="utf-8")
            for block in re.findall(
                r'!!! warning "MEASUREMENT-PENDING[^"]*"\n((?:    .*\n?)+)', text
            ):
                assert not re.search(r"\$\d|\d+ ?minutes", block), (
                    f"{page}: MEASUREMENT-PENDING block contains a number"
                )
