"""D7 tests — T-REP-02 (PDF), T-REP-04 (methodology), T-REP-05..06 (signed URLs),
T-REP-08 (PDF pricing provenance) per docs/05 §3."""

import time
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_runner import seed_audit
from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.services.ingest import load
from tokenops_cost_auditor.services.pricing.coster import apply
from tokenops_cost_auditor.services.pricing.table import PricingTable
from tokenops_cost_auditor.services.report.model import ReportModel
from tokenops_cost_auditor.services.report.render_json import render_json
from tokenops_cost_auditor.services.report.render_pdf import render_pdf, render_report_html
from tokenops_cost_auditor.services.report.signer import (
    SignedUrlError,
    sign_report_url,
    verify_report_url,
)
from tokenops_cost_auditor.services.rules.base import DetectorContext
from tokenops_cost_auditor.services.rules.findings import observed_days
from tokenops_cost_auditor.services.rules.registry import run_all

FIXTURES = Path(__file__).parent / "fixtures"
TABLE = PricingTable.load()


@pytest.fixture(scope="module")
def waste_report() -> ReportModel:
    frame, _ = load(FIXTURES / "waste_pack_anthropic.jsonl")
    priced, unpriced = apply(TABLE, frame)
    ctx = DetectorContext(Settings(_env_file=None), TABLE, observed_days(priced))
    findings = run_all(priced, ctx)
    return ReportModel.build("test-audit-01", priced, findings, unpriced, TABLE)


class TestTREP02Pdf:
    def test_pdf_renders_nonempty_with_summary(
        self, waste_report: ReportModel, tmp_path: Path
    ) -> None:
        """PDF bytes are valid and non-trivial; the savings % and exec summary are
        asserted on the RENDERED HTML fed to weasyprint (text extraction from PDF
        would need a new dependency; the HTML is the exact content source)."""
        html = render_report_html(waste_report, template="pdf/report.html")
        assert f"{waste_report.savings_pct:.1f}%" in html  # exec-summary savings %
        assert f"${waste_report.monthly_savings_usd:.2f}" in html
        assert "estimated monthly savings" in html
        pdf_path = render_pdf(waste_report, tmp_path / "report.pdf")
        data = pdf_path.read_bytes()
        assert data.startswith(b"%PDF")
        assert len(data) > 5000  # non-empty, multi-section document

    def test_findings_ordered_by_impact_in_html(self, waste_report: ReportModel) -> None:
        html = render_report_html(waste_report, template="report.html")
        positions = [html.index(f.id) for f in waste_report.findings]
        assert positions == sorted(positions)  # FR-14 ranking preserved in render


class TestTREP04Methodology:
    def test_methodology_and_data_handling_present(self, waste_report: ReportModel) -> None:
        html = render_report_html(waste_report, template="pdf/report.html")
        assert "Methodology" in html
        assert "no AI model calls" in html
        assert "FLOORS" in html  # R-GOLDEN-C3 disclosure
        assert "0.7 haircut" in html and "20% suffix haircut" in html  # R-Q4/R-Q5
        assert "Data handling" in html
        assert "never used for training" in html

    def test_trep08_pricing_provenance_in_pdf_html(self, waste_report: ReportModel) -> None:
        html = render_report_html(waste_report, template="pdf/report.html")
        assert waste_report.pricing_version in html  # FR-28
        assert "human-verified 2026-07-17" in html
        assert "0 unpriced models" in html


class TestTREP0506SignedUrls:
    SECRET = "test-secret"

    def test_valid_roundtrip(self) -> None:
        token = sign_report_url(self.SECRET, "audit-xyz")
        assert verify_report_url(self.SECRET, token, max_age_days=30) == "audit-xyz"

    def test_tampered_rejected(self) -> None:
        token = sign_report_url(self.SECRET, "audit-xyz")
        bad = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
        with pytest.raises(SignedUrlError, match="invalid report link"):
            verify_report_url(self.SECRET, bad, max_age_days=30)

    def test_expired_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        token = sign_report_url(self.SECRET, "audit-xyz")
        real_time = time.time()
        monkeypatch.setattr(time, "time", lambda: real_time + 31 * 86400)
        with pytest.raises(SignedUrlError, match="expired"):
            verify_report_url(self.SECRET, token, max_age_days=30)

    def test_wrong_secret_rejected(self) -> None:
        token = sign_report_url(self.SECRET, "audit-xyz")
        with pytest.raises(SignedUrlError):
            verify_report_url("other-secret", token, max_age_days=30)


class TestWebReportRoute:
    def test_full_flow_serves_html_and_pdf(
        self, app: FastAPI, client: TestClient, settings
    ) -> None:
        audit_id = seed_audit(app, "waste_pack_anthropic.jsonl", email="web@example.com")
        app.state.runner.run(audit_id)
        token = sign_report_url(settings.secret_key, audit_id)
        page = client.get(f"/r/{token}")
        assert page.status_code == 200
        assert "estimated monthly savings" in page.text
        pdf = client.get(f"/r/{token}/pdf")
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.content.startswith(b"%PDF")

    def test_bad_token_404(self, client: TestClient) -> None:
        assert client.get("/r/not-a-real-token").status_code == 404


class TestD11RenderCap:
    """UAT-1 dogfood fix: unbounded findings lists must not reach WeasyPrint.
    JSON keeps every finding; web/PDF show top render_cap with an explicit note."""

    @pytest.fixture
    def big_report(self, waste_report: ReportModel) -> ReportModel:
        f0 = waste_report.findings[0]
        many = tuple(
            replace(f0, id=f"D9X-{i:03d}", monthly_cost_impact_usd=float(1000 - i))
            for i in range(60)
        )
        return replace(waste_report, findings=many)

    def test_html_capped_with_explicit_note(self, big_report: ReportModel) -> None:
        html = render_report_html(big_report, template="report.html")
        assert "Showing the top 50 of 60 findings" in html
        assert html.count('class="finding ') == 50  # cards capped
        assert "D9X-049" in html and "D9X-059" not in html  # ranked cut, not random

    def test_json_always_complete(self, big_report: ReportModel, tmp_path: Path) -> None:
        import json as jsonlib

        path = tmp_path / "report.json"
        render_json(big_report, path)
        data = jsonlib.loads(path.read_text(encoding="utf-8"))
        assert len(data["findings"]) == 60
        assert "render_cap" not in data  # presentation constant never serialized

    def test_uncapped_report_has_no_note(self, waste_report: ReportModel) -> None:
        html = render_report_html(waste_report, template="report.html")
        assert "Showing the top" not in html


class TestD11SavingsCap:
    """UAT-1 dogfood fix: overlapping waste classes must never produce a
    savings total above spend (228% claim / negative projection defect)."""

    def test_headline_capped_at_monthly_spend(self, waste_report: ReportModel) -> None:
        from tokenops_cost_auditor.services.ingest import load as load_fixture

        frame, _ = load_fixture(FIXTURES / "waste_pack_anthropic.jsonl")
        priced, unpriced = apply(TABLE, frame)
        huge = [
            replace(
                waste_report.findings[0],
                id=f"DX-{i}",
                monthly_cost_impact_usd=waste_report.monthly_spend_usd,  # each ~= spend
            )
            for i in range(3)
        ]
        report = ReportModel.build("cap-test", priced, huge, unpriced, TABLE)
        assert report.monthly_savings_usd <= report.monthly_spend_usd
        assert report.monthly_optimized_usd >= 0.0
        assert report.savings_pct <= 100.0
        assert "capped at your observed monthly spend" in report.methodology


class TestTREP09EquivSpend:
    """FR-30 (R-EQUIV-SPEND): subscription-plan traffic gets the verbatim
    API-equivalent framing in header + methodology; metered traffic does not."""

    EQUIV = "Figures are API-equivalent token value; actual billing depends on your plan."

    def test_claude_code_export_sets_flag_note_and_methodology(self, tmp_path: Path) -> None:
        import json

        export = tmp_path / "cc_export.jsonl"
        lines = [
            {
                "ts": 1750000000 + i * 60,
                "endpoint": "claude-code",  # exporter-stamped (FR-24)
                "tag": "sess-1",
                "response": {
                    "id": f"msg_{i}",
                    "type": "message",
                    "model": "claude-sonnet-5",
                    "usage": {"input_tokens": 1200, "output_tokens": 80},
                },
            }
            for i in range(3)
        ]
        export.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
        frame, _ = load(export)
        priced, unpriced = apply(TABLE, frame)
        ctx = DetectorContext(Settings(_env_file=None), TABLE, observed_days(priced))
        report = ReportModel.build("equiv-test", priced, run_all(priced, ctx), unpriced, TABLE)
        assert report.equiv_spend is True
        assert self.EQUIV in report.methodology
        html = render_report_html(report, template="report.html")
        assert self.EQUIV in html  # header note (FR-30)

    def test_metered_traffic_has_no_note(self, waste_report: ReportModel) -> None:
        assert waste_report.equiv_spend is False
        assert self.EQUIV not in waste_report.methodology
        html = render_report_html(waste_report, template="report.html")
        assert self.EQUIV not in html
