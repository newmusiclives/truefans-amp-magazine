"""Interactive pricing and revenue calculator."""
from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def pricing_calculator(request: Request):
    config = get_config()
    repo = get_repo()
    subscriber_count = repo.get_subscriber_count()
    editions = repo.get_editions()
    licensees = []
    try:
        licensees = repo.get_licensees(status="active")
    except Exception:
        pass
    return HTMLResponse(render("pricing_calculator.html",
        config=config, subscriber_count=subscriber_count,
        editions=editions, licensee_count=len(licensees)))
