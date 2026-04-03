"""Revenue dashboard — unified view of all revenue streams."""
from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def revenue_dashboard(request: Request):
    repo = get_repo()
    summary = repo.get_revenue_summary()
    by_edition = repo.get_revenue_by_edition()
    tier_breakdown = repo.get_tier_breakdown()
    subscriber_count = repo.get_subscriber_count()
    return HTMLResponse(render("revenue_dashboard.html",
        summary=summary, by_edition=by_edition,
        tier_breakdown=tier_breakdown, subscriber_count=subscriber_count))
