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

    def test_clause_structure_matches(self) -> None:
        """Every bold clause heading on a web legal page appears in its docs mirror."""
        for name in ("terms", "privacy", "dpa"):
            web = re.sub(r"\s+", " ", (TEMPLATES / f"{name}.html").read_text(encoding="utf-8"))
            docs = re.sub(r"\s+", " ", (DOCS / f"legal/{name}.md").read_text(encoding="utf-8"))
            for clause in strong_clauses(web):
                assert clause in bold_clauses(docs), (
                    f"legal drift: clause {clause!r} on web {name} page missing from "
                    f"docs-site/legal/{name}.md (MP-9 single-sourcing)"
                )

    def test_price_matches_terms(self) -> None:
        web = (TEMPLATES / "terms.html").read_text(encoding="utf-8")
        docs = (DOCS / "legal/terms.md").read_text(encoding="utf-8")
        assert "$500 / ₹20,000" in web and "$500 / ₹20,000" in docs


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
