"""Advertiser self-serve portal — login, dashboard, campaign management."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/advertiser/login", response_class=HTMLResponse)
async def advertiser_login_page(request: Request):
    config = get_config()
    return HTMLResponse(render("advertiser_login.html", config=config))


@router.post("/advertiser/login", response_class=HTMLResponse)
async def advertiser_login(request: Request, email: str = Form(...), password: str = Form(...)):
    repo = get_repo()
    account = repo.get_advertiser_by_email(email)
    if not account:
        return HTMLResponse(render("advertiser_login.html", error="Invalid credentials", config=get_config()))
    from weeklyamp.web.security import verify_password
    if not verify_password(password, account.get("password_hash", "")):
        return HTMLResponse(render("advertiser_login.html", error="Invalid credentials", config=get_config()))
    # For demo: pass advertiser_id via query param (production would use session)
    campaigns = repo.get_advertiser_campaigns(account["id"])
    config = get_config()
    return HTMLResponse(render("advertiser_dashboard.html", account=account, campaigns=campaigns, config=config))


@router.get("/advertiser/dashboard", response_class=HTMLResponse)
async def advertiser_dashboard(request: Request, advertiser_id: int = 0):
    repo = get_repo()
    config = get_config()
    campaigns = repo.get_advertiser_campaigns(advertiser_id) if advertiser_id else []
    return HTMLResponse(render("advertiser_dashboard.html", account={}, campaigns=campaigns, config=config))


@router.post("/advertiser/campaign/create", response_class=HTMLResponse)
async def create_campaign(
    request: Request,
    advertiser_id: int = Form(...),
    name: str = Form(...),
    edition_slug: str = Form(""),
    position: str = Form("mid"),
    headline: str = Form(""),
    body_html: str = Form(""),
    cta_url: str = Form(""),
    cta_text: str = Form("Learn More"),
    budget_cents: int = Form(0),
):
    repo = get_repo()
    campaign_id = repo.create_advertiser_campaign(
        advertiser_id=advertiser_id, name=name, edition_slug=edition_slug,
        position=position, headline=headline, body_html=body_html,
        cta_url=cta_url, cta_text=cta_text, budget_cents=budget_cents,
    )
    return HTMLResponse(f'<div class="alert alert-success">Campaign created (ID: {campaign_id}). It will be reviewed by our team.</div>')


@router.post("/advertiser/campaign/{campaign_id}/submit", response_class=HTMLResponse)
async def submit_campaign(campaign_id: int, request: Request):
    repo = get_repo()
    repo.update_campaign_status(campaign_id, "submitted")
    return HTMLResponse('<div class="alert alert-success">Campaign submitted for review!</div>')


@router.get("/advertiser/rates", response_class=HTMLResponse)
async def rate_card(request: Request):
    config = get_config()
    return HTMLResponse(render("advertiser_dashboard.html", account={}, campaigns=[], config=config, show_rates=True))
