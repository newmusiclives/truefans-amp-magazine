"""Affiliate program management routes."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def affiliates_page(request: Request):
    repo = get_repo()
    programs = repo.get_affiliate_programs()
    categories = {}
    for p in programs:
        cat = p.get("category", "general")
        categories.setdefault(cat, []).append(p)
    return HTMLResponse(render("affiliates.html", categories=categories, programs=programs))


@router.get("/redirect/{slug}")
async def affiliate_redirect(slug: str):
    from fastapi.responses import RedirectResponse
    repo = get_repo()
    program = repo.get_affiliate_by_slug(slug)
    if not program:
        return RedirectResponse("/affiliates/", status_code=302)
    repo.record_affiliate_click(program["id"])
    return RedirectResponse(program["affiliate_url"], status_code=302)
