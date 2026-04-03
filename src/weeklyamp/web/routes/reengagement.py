"""Re-engagement admin routes."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def reengagement_page(request: Request):
    repo = get_repo()
    config = get_config()
    from weeklyamp.content.reengagement import ReengagementManager

    mgr = ReengagementManager(repo, config.reengagement)
    inactive = mgr.find_inactive_subscribers()
    stats = mgr.get_stats()
    return HTMLResponse(
        render(
            "reengagement.html",
            inactive=inactive,
            stats=stats,
            config=config,
        )
    )


@router.post("/create-campaign", response_class=HTMLResponse)
async def create_campaign(
    request: Request, campaign_type: str = Form("winback")
):
    repo = get_repo()
    config = get_config()
    from weeklyamp.content.reengagement import ReengagementManager

    mgr = ReengagementManager(repo, config.reengagement)
    inactive = mgr.find_inactive_subscribers()
    sub_ids = [s["id"] for s in inactive[:50]]
    if sub_ids:
        mgr.create_campaign(sub_ids, campaign_type)
    return HTMLResponse(
        f'<div class="alert alert-success">Campaign created for {len(sub_ids)} subscribers.</div>'
    )


@router.post("/suppress", response_class=HTMLResponse)
async def suppress_inactive(request: Request):
    repo = get_repo()
    config = get_config()
    from weeklyamp.content.reengagement import ReengagementManager

    mgr = ReengagementManager(repo, config.reengagement)
    count = mgr.auto_suppress_inactive()
    return HTMLResponse(
        f'<div class="alert alert-success">{count} subscribers suppressed.</div>'
    )
