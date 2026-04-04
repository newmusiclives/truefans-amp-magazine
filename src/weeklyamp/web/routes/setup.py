"""Setup and deliverability guide."""
from __future__ import annotations

import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def setup_page(request: Request):
    config = get_config()
    # Check what's configured
    checks = {
        "smtp": bool(config.email.smtp_host and config.email.smtp_user),
        "admin_password": bool(os.environ.get("WEEKLYAMP_ADMIN_PASSWORD") or os.environ.get("WEEKLYAMP_ADMIN_HASH")),
        "secret_key": bool(os.environ.get("WEEKLYAMP_SECRET_KEY")),
        "tracking_domain": bool(config.tracking.tracking_domain) if hasattr(config, 'tracking') else False,
        "stripe": bool(config.paid_tiers.stripe_secret_key) if hasattr(config, 'paid_tiers') else False,
        "site_domain": config.site_domain != "https://truefansnewsletters.com",
    }
    return HTMLResponse(render("setup.html", checks=checks, config=config))
