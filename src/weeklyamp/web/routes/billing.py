"""Billing routes — pricing page, checkout, webhook, manage."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request):
    repo = get_repo()
    config = get_config()
    tiers = repo.get_tiers()
    import json
    for tier in tiers:
        tier["features"] = json.loads(tier.get("features_json", "[]"))
    return HTMLResponse(render("pricing.html", tiers=tiers, config=config))


@router.post("/billing/checkout", response_class=HTMLResponse)
async def create_checkout(request: Request, tier_slug: str = Form(...), email: str = Form("")):
    config = get_config()
    if not config.paid_tiers.enabled:
        return HTMLResponse('<div class="alert alert-warning">Paid tiers are not yet active.</div>')
    from weeklyamp.billing.stripe_client import StripeClient
    client = StripeClient(config.paid_tiers)
    url = client.create_checkout_session(
        price_id=tier_slug, subscriber_email=email,
        success_url=f"{config.site_domain}/billing/success",
        cancel_url=f"{config.site_domain}/pricing",
    )
    if url:
        return RedirectResponse(url, status_code=303)
    return HTMLResponse('<div class="alert alert-danger">Checkout unavailable. Please try again later.</div>')


@router.post("/billing/webhook")
async def stripe_webhook(request: Request):
    config = get_config()
    from weeklyamp.billing.stripe_client import StripeClient
    client = StripeClient(config.paid_tiers)
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    event = client.handle_webhook(payload, sig)
    if not event:
        return JSONResponse({"error": "Invalid webhook"}, status_code=400)

    repo = get_repo()
    event_type = event["type"]
    data = event["data"]

    if event_type == "customer.subscription.created":
        pass  # Handle new subscription
    elif event_type == "customer.subscription.updated":
        repo.update_billing_status(
            data.get("id", ""),
            data.get("status", "active"),
            data.get("current_period_end", ""),
        )
    elif event_type == "customer.subscription.deleted":
        repo.update_billing_status(data.get("id", ""), "cancelled")

    return JSONResponse({"received": True})


@router.get("/billing/manage", response_class=HTMLResponse)
async def billing_manage(request: Request):
    config = get_config()
    return HTMLResponse(render("billing_manage.html", config=config))
