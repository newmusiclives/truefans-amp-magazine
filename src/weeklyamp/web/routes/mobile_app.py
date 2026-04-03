"""Mobile app waitlist landing page."""
from __future__ import annotations
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()

@router.get("/mobile-app", response_class=HTMLResponse)
async def mobile_app_page(request: Request):
    repo = get_repo()
    count = repo.get_mobile_waitlist_count()
    return HTMLResponse(render("mobile_app.html", waitlist_count=count))

@router.post("/mobile-app/waitlist", response_class=HTMLResponse)
async def mobile_waitlist(request: Request, email: str = Form(...), platform: str = Form("both")):
    repo = get_repo()
    repo.create_mobile_waitlist(email, platform)
    return HTMLResponse('<div style="padding:24px;text-align:center;color:#10b981;font-size:18px;font-weight:600;">You\'re on the list! We\'ll notify you when the app launches.</div>')
