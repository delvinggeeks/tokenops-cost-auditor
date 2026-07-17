"""Web report page behind a signed, expiring URL (FR-15; docs/03-LLD.md §5: GET /r/{signed}).

Web page, deliberately NOT under /api/v1 (FR-25 scopes only API routes).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse

from tokenops_cost_auditor.services.report.signer import SignedUrlError, verify_report_url

router = APIRouter(tags=["report"])


@router.get("/r/{token}", response_class=HTMLResponse)
def web_report(request: Request, token: str) -> HTMLResponse:
    settings = request.app.state.settings
    try:
        audit_id = verify_report_url(settings.secret_key, token, settings.report_url_expiry_days)
    except SignedUrlError as exc:
        return HTMLResponse(status_code=404, content=f"<h1>404</h1><p>{exc}</p>")

    html_path = Path(settings.report_dir) / audit_id / "report.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse(status_code=404, content="<h1>404</h1><p>report not found</p>")


@router.get("/r/{token}/pdf", response_model=None)
def report_pdf(request: Request, token: str) -> FileResponse | HTMLResponse:
    settings = request.app.state.settings
    try:
        audit_id = verify_report_url(settings.secret_key, token, settings.report_url_expiry_days)
    except SignedUrlError as exc:
        return HTMLResponse(status_code=404, content=f"<h1>404</h1><p>{exc}</p>")
    pdf_path = Path(settings.report_dir) / audit_id / "report.pdf"
    if pdf_path.exists():
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=f"tokenops-cost-audit-{audit_id[:8]}.pdf",
        )
    return HTMLResponse(status_code=404, content="<h1>404</h1><p>report not found</p>")
