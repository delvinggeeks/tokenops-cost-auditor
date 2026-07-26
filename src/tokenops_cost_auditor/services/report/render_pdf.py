"""Branded PDF rendering via weasyprint on templates/pdf/report.html (FR-14, ADR-4).

Render-only: the template consumes ReportModel fields verbatim (T-REP-01).
render_report_html() is shared with the web report page (FR-15) so both artifacts
can never diverge (same body partial).
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from tokenops_cost_auditor.services.report.model import ReportModel
from tokenops_cost_auditor.services.rules import detector_copy

TEMPLATES_DIR = Path(__file__).parents[2] / "web" / "templates"

_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
)


def render_report_html(report: ReportModel, template: str = "pdf/report.html") -> str:
    # §3 #3: `dcopy` is the SAME services-layer detector copy the in-app findings use,
    # so the report's plain headline + summary match /findings word for word.
    return _env.get_template(template).render(report=report, dcopy=detector_copy)


def render_pdf(report: ReportModel, path: Path) -> Path:
    # imported lazily: weasyprint pulls system libraries (pango/harfbuzz) that the
    # API worker needs only when a PDF is actually rendered
    from weasyprint import HTML

    path.parent.mkdir(parents=True, exist_ok=True)
    html = render_report_html(report, template="pdf/report.html")
    HTML(string=html).write_pdf(str(path))
    return path
