"""Billing routes — pricing, checkout, webhook, manage, cancel, coupons.

All payments processed via Manifest Financial.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request):
    repo = get_repo()
    config = get_config()
    tiers = repo.get_tiers()
    for tier in tiers:
        tier["features"] = json.loads(tier.get("features_json", "[]"))
    return HTMLResponse(render("pricing.html", tiers=tiers, config=config))


@router.post("/billing/checkout", response_class=HTMLResponse)
async def create_checkout(request: Request, tier_slug: str = Form(...), email: str = Form("")):
    config = get_config()
    if not config.paid_tiers.enabled:
        return HTMLResponse('<div class="alert alert-warning">Paid tiers are not yet active.</div>')

    from weeklyamp.billing.stripe_client import PaymentClient
    client = PaymentClient(config.paid_tiers)
    url = client.create_checkout_session(
        price_id=tier_slug,
        customer_email=email,
        success_url=f"{config.site_domain}/billing/success",
        cancel_url=f"{config.site_domain}/pricing",
        metadata={"tier_slug": tier_slug, "email": email},
    )
    if url:
        return RedirectResponse(url, status_code=303)
    return HTMLResponse('<div class="alert alert-danger">Checkout unavailable. Please try again later.</div>')


@router.get("/billing/success", response_class=HTMLResponse)
async def billing_success(request: Request):
    config = get_config()
    return HTMLResponse(render("billing_success.html", config=config))


@router.post("/billing/webhook")
async def manifest_webhook(request: Request):
    """Handle Manifest Financial webhook events."""
    config = get_config()
    from weeklyamp.billing.stripe_client import PaymentClient
    client = PaymentClient(config.paid_tiers)
    payload = await request.body()
    sig = request.headers.get("x-manifest-signature", "")
    event = client.handle_webhook(payload, sig)
    if not event:
        return JSONResponse({"error": "Invalid webhook"}, status_code=400)

    repo = get_repo()
    event_type = event["type"]
    data = event["data"]

    if event_type in ("subscription.created", "subscription.activated"):
        # New subscription — create billing record
        subscriber_email = data.get("customer_email", "")
        tier_slug = data.get("metadata", {}).get("tier_slug", "pro")
        tier = repo.get_tier_by_slug(tier_slug)
        subscriber = repo.get_subscriber_by_email(subscriber_email)
        if subscriber and tier:
            repo.create_billing_record(
                subscriber_id=subscriber["id"],
                tier_id=tier["id"],
                payment_customer_id=data.get("customer_id", ""),
                payment_subscription_id=data.get("subscription_id", data.get("id", "")),
                payment_provider="manifest",
            )
    elif event_type in ("subscription.updated", "subscription.renewed"):
        repo.update_billing_status(
            data.get("subscription_id", data.get("id", "")),
            data.get("status", "active"),
            data.get("current_period_end", ""),
        )
    elif event_type in ("subscription.cancelled", "subscription.deleted"):
        repo.update_billing_status(
            data.get("subscription_id", data.get("id", "")),
            "cancelled",
        )
    elif event_type == "subscription.past_due":
        sub_id = data.get("subscription_id", data.get("id", ""))
        repo.update_billing_status(sub_id, "past_due")
        repo.update_dunning_state(sub_id, "grace")
    elif event_type in ("invoice.paid", "payment.succeeded"):
        # Clear dunning state on successful payment
        sub_id = data.get("subscription_id", "")
        if sub_id:
            repo.update_dunning_state(sub_id, "")
            repo.update_billing_status(sub_id, "active")

    return JSONResponse({"received": True})


@router.post("/billing/cancel")
async def cancel_subscription(request: Request):
    """Cancel the current subscriber's subscription."""
    config = get_config()
    if not config.paid_tiers.enabled:
        return JSONResponse({"error": "Billing not active"}, status_code=400)

    session = getattr(request.state, "session", None) or {}
    subscriber_id = session.get("subscriber_id")
    if not subscriber_id:
        return JSONResponse({"error": "Not logged in"}, status_code=401)

    repo = get_repo()
    billing = repo.get_billing_for_subscriber(int(subscriber_id))
    if not billing or billing.get("status") != "active":
        return JSONResponse({"error": "No active subscription"}, status_code=400)

    from weeklyamp.billing.stripe_client import PaymentClient
    client = PaymentClient(config.paid_tiers)
    success = client.cancel_subscription(billing.get("payment_subscription_id", ""))
    if success:
        return JSONResponse({"status": "cancelled_at_period_end"})
    return JSONResponse({"error": "Cancellation failed"}, status_code=500)


@router.post("/billing/portal")
async def billing_portal(request: Request):
    """Redirect subscriber to Manifest Financial billing portal."""
    config = get_config()
    if not config.paid_tiers.enabled:
        return JSONResponse({"error": "Billing not active"}, status_code=400)

    session = getattr(request.state, "session", None) or {}
    subscriber_id = session.get("subscriber_id")
    if not subscriber_id:
        return JSONResponse({"error": "Not logged in"}, status_code=401)

    repo = get_repo()
    billing = repo.get_billing_for_subscriber(int(subscriber_id))
    if not billing:
        return RedirectResponse("/pricing", status_code=303)

    from weeklyamp.billing.stripe_client import PaymentClient
    client = PaymentClient(config.paid_tiers)
    url = client.create_billing_portal_session(
        billing.get("payment_customer_id", ""),
        f"{config.site_domain}/billing/manage",
    )
    if url:
        return RedirectResponse(url, status_code=303)
    return RedirectResponse("/billing/manage", status_code=303)


@router.post("/billing/apply-coupon")
async def apply_coupon(request: Request, coupon_code: str = Form(...)):
    """Apply a coupon code to the subscriber's active subscription."""
    config = get_config()
    if not config.paid_tiers.enabled:
        return HTMLResponse('<div class="alert alert-warning">Billing not active.</div>')

    repo = get_repo()
    coupon = repo.get_coupon_by_code(coupon_code.strip().upper())
    if not coupon:
        return HTMLResponse('<div class="alert alert-danger">Invalid coupon code.</div>')
    if coupon.get("max_uses") and coupon["current_uses"] >= coupon["max_uses"]:
        return HTMLResponse('<div class="alert alert-danger">Coupon has been fully redeemed.</div>')

    session = getattr(request.state, "session", None) or {}
    subscriber_id = session.get("subscriber_id")
    if not subscriber_id:
        return HTMLResponse('<div class="alert alert-danger">Login required.</div>')

    billing = repo.get_billing_for_subscriber(int(subscriber_id))
    if not billing or billing.get("status") != "active":
        return HTMLResponse('<div class="alert alert-danger">No active subscription to apply coupon to.</div>')

    from weeklyamp.billing.stripe_client import PaymentClient
    client = PaymentClient(config.paid_tiers)
    success = client.apply_coupon(billing.get("payment_subscription_id", ""), coupon_code)
    if success:
        repo.redeem_coupon(coupon["id"], subscriber_id=int(subscriber_id), discount_applied_cents=coupon["discount_value"])
        return HTMLResponse('<div class="alert alert-success">Coupon applied successfully!</div>')
    return HTMLResponse('<div class="alert alert-danger">Failed to apply coupon. Please try again.</div>')


@router.get("/billing/manage", response_class=HTMLResponse)
async def billing_manage(request: Request):
    config = get_config()
    return HTMLResponse(render("billing_manage.html", config=config))
