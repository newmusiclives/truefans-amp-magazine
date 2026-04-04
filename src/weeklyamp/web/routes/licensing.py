"""Licensing management — city edition franchise administration."""
from __future__ import annotations
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def licensing_page(request: Request):
    repo = get_repo()
    config = get_config()
    licensees = repo.get_licensees()
    markets = repo.get_edition_markets()
    return HTMLResponse(render("licensing.html", licensees=licensees, markets=markets, config=config))

@router.get("/{licensee_id}", response_class=HTMLResponse)
async def licensee_detail(licensee_id: int, request: Request):
    repo = get_repo()
    config = get_config()
    licensee = repo.get_licensee(licensee_id)
    if not licensee:
        return HTMLResponse("Licensee not found", status_code=404)
    revenue = repo.get_license_revenue(licensee_id)
    return HTMLResponse(render("licensee_detail.html", licensee=licensee, revenue=revenue, config=config))

@router.post("/create", response_class=HTMLResponse)
async def create_licensee(request: Request, company_name: str = Form(...), contact_name: str = Form(...), email: str = Form(...), password: str = Form(...), city_market_slug: str = Form(""), edition_slugs: str = Form("fan,artist,industry")):
    repo = get_repo()
    config = get_config()
    from weeklyamp.web.security import hash_password
    pw_hash = hash_password(password)
    fee = config.licensing.default_monthly_fee_cents
    share = config.licensing.default_revenue_share_pct
    licensee_id = repo.create_licensee(company_name, contact_name, email, pw_hash, city_market_slug, edition_slugs, "monthly", fee, share)
    return HTMLResponse(f'<div class="alert alert-success">Licensee created (ID: {licensee_id}). Status: pending approval.</div>')

@router.post("/{licensee_id}/status", response_class=HTMLResponse)
async def update_status(licensee_id: int, request: Request, status: str = Form(...)):
    repo = get_repo()
    repo.update_licensee_status(licensee_id, status)
    return HTMLResponse(f'<span class="badge badge-info">{status}</span>')
