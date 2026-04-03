"""Artist newsletter waitlist and admin routes."""
from __future__ import annotations
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()

@router.get("/artist-newsletters", response_class=HTMLResponse)
async def landing_page(request: Request):
    config = get_config()
    return HTMLResponse(render("artist_newsletters_landing.html", config=config))

@router.post("/artist-newsletters/waitlist", response_class=HTMLResponse)
async def waitlist_signup(request: Request, artist_name: str = Form(...), email: str = Form(...), website: str = Form(""), genre: str = Form(""), fan_count: str = Form(""), message: str = Form("")):
    repo = get_repo()
    repo.create_artist_newsletter_waitlist(artist_name, email, website, genre=genre, fan_count=fan_count, message=message)
    return HTMLResponse('<div style="padding:24px;text-align:center;color:#10b981;font-size:18px;font-weight:600;">You\'re on the list! We\'ll be in touch soon.</div>')

@router.get("/admin/artist-newsletters", response_class=HTMLResponse)
async def admin_page(request: Request):
    repo = get_repo()
    waitlist = repo.get_artist_newsletter_waitlist()
    return HTMLResponse(render("admin_artist_newsletters.html", waitlist=waitlist))

@router.post("/admin/artist-newsletters/{entry_id}/status", response_class=HTMLResponse)
async def update_status(entry_id: int, request: Request, status: str = Form(...)):
    repo = get_repo()
    repo.update_waitlist_status(entry_id, status)
    return HTMLResponse(f'<span class="badge badge-info">{status}</span>')
