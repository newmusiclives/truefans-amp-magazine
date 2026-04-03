"""Market sub-edition management."""
from __future__ import annotations
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()

CITY_SLUGS = frozenset({
    "nashville", "los-angeles", "new-york", "atlanta", "london",
    "austin", "miami", "chicago", "detroit", "memphis", "seattle",
    "toronto", "berlin", "lagos", "tokyo", "seoul", "paris",
    "sao-paulo", "mumbai", "kingston",
})


@router.get("/", response_class=HTMLResponse)
async def markets_page(request: Request):
    repo = get_repo()
    editions = repo.get_editions()
    markets = repo.get_edition_markets()
    genre_by_edition = {}
    city_by_edition = {}
    for m in markets:
        ed = m["edition_slug"]
        if m["market_slug"] in CITY_SLUGS:
            city_by_edition.setdefault(ed, []).append(m)
        else:
            genre_by_edition.setdefault(ed, []).append(m)
    return HTMLResponse(render("markets.html",
        editions=editions, genre_by_edition=genre_by_edition, city_by_edition=city_by_edition))

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
