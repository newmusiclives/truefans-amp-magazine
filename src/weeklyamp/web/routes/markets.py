"""Market sub-edition management."""
from __future__ import annotations
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def markets_page(request: Request):
    repo = get_repo()
    editions = repo.get_editions()
    markets = repo.get_edition_markets()
    by_edition = {}
    for m in markets:
        by_edition.setdefault(m["edition_slug"], []).append(m)
    return HTMLResponse(render("markets.html", editions=editions, by_edition=by_edition))

@router.post("/create", response_class=HTMLResponse)
async def create_market(request: Request, edition_slug: str = Form(...), market_slug: str = Form(...), market_name: str = Form(...), description: str = Form("")):
    repo = get_repo()
    repo.create_edition_market(edition_slug, market_slug, market_name, description)
    return HTMLResponse('<div class="alert alert-success">Market created.</div>')

@router.post("/{market_id}/toggle", response_class=HTMLResponse)
async def toggle_market(market_id: int, request: Request):
    repo = get_repo()
    repo.toggle_edition_market(market_id)
    return HTMLResponse('<div class="alert alert-success">Market toggled.</div>')
