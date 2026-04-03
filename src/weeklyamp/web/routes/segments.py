"""Subscriber segmentation dashboard."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def segments_page(request: Request):
    repo = get_repo()
    summary = repo.get_subscriber_segments_summary()
    cohorts = repo.get_cohort_retention(months=6)
    at_risk = repo.get_at_risk_subscribers()
    return HTMLResponse(render("segments.html", summary=summary, cohorts=cohorts, at_risk=at_risk))
