"""R-LANDING-2 gate criterion (founder amendment 2026-07-25): measured
budgets ARE the gate evidence — JS<15KB, CSS<25KB, total transfer<300KB,
hero image<120KB. Enforced in the suite so a later asset can't quietly blow
the budget between gate runs.

Transfer = what actually crosses the wire: gzip for text (Caddy compresses),
file size for already-compressed images.
"""

from __future__ import annotations

import gzip
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO = Path(__file__).parents[1]
STATIC = REPO / "src/tokenops_cost_auditor/web/static"

KB = 1024


def gz(data: bytes) -> int:
    return len(gzip.compress(data, 6))


def landing_assets(app: FastAPI) -> tuple[str, dict[str, Path]]:
    html = TestClient(app).get("/").text
    paths: dict[str, Path] = {}
    for url in re.findall(r'(?:src|href)="(/static/[^"]+)"', html):
        paths[url] = STATIC / url.removeprefix("/static/")
    return html, paths


class TestTheBudgetsHold:
    def test_every_referenced_asset_exists(self, app: FastAPI) -> None:
        _, assets = landing_assets(app)
        missing = [u for u, p in assets.items() if not p.exists()]
        assert not missing, f"landing references assets that do not exist: {missing}"

    def test_js_under_15kb(self, app: FastAPI) -> None:
        _, assets = landing_assets(app)
        js = [p for p in assets.values() if p.suffix == ".js"]
        assert js, "the landing motion script is not referenced"
        total = sum(p.stat().st_size for p in js)
        assert total < 15 * KB, f"landing JS {total}B breaks the 15KB budget"

    def test_css_transfer_under_25kb(self, app: FastAPI) -> None:
        _, assets = landing_assets(app)
        css = [p for p in assets.values() if p.suffix == ".css"]
        assert css, "no stylesheets referenced?"
        total = sum(gz(p.read_bytes()) for p in css)
        assert total < 25 * KB, f"CSS transfer {total}B (gzip) breaks the 25KB budget"

    def test_hero_under_120kb(self) -> None:
        hero = STATIC / "land/hero-dashboard-sample.webp"
        assert hero.exists()
        assert hero.stat().st_size < 120 * KB, f"hero {hero.stat().st_size}B breaks 120KB"

    def test_total_transfer_under_300kb(self, app: FastAPI) -> None:
        html, assets = landing_assets(app)
        total = gz(html.encode())
        for p in assets.values():
            data = p.read_bytes()
            total += gz(data) if p.suffix in (".css", ".js") else len(data)
        assert total < 300 * KB, f"landing total transfer {total}B breaks the 300KB budget"

    def test_the_screenshots_declare_themselves_sample_data(self, app: FastAPI) -> None:
        """Every product screenshot's alt text says sample data, and the tour
        section says it in visible copy — unlabeled numbers would be a lie."""
        html, _ = landing_assets(app)
        for alt in re.findall(r'<img[^>]+alt="([^"]+)"', html):
            assert "sample data" in alt.lower(), f"screenshot alt without the label: {alt!r}"
        assert "labeled sample data" in html
