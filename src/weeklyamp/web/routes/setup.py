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
        "manifest": bool(config.paid_tiers.manifest_api_key) if hasattr(config, 'paid_tiers') else False,
        "site_domain": config.site_domain != "https://truefansnewsletters.com",
    }
    return HTMLResponse(render("setup.html", checks=checks, config=config))


@router.get("/wizard", response_class=HTMLResponse)
async def setup_wizard(request: Request):
    repo = get_repo()
    config = get_config()

    # Check completion status of each step
    steps = [
        {
            "number": 1,
            "title": "Configure Editions",
            "description": "Your 3 editions (Fan, Artist, Industry) are pre-configured with 15 sections each.",
            "status": "complete",  # Always done since we seed editions
            "action_url": "/sections",
            "action_label": "Review Sections",
        },
        {
            "number": 2,
            "title": "Fetch Research Content",
            "description": "50 RSS sources are configured. Fetch the latest content to power your AI writers.",
            "status": "complete" if repo.get_unused_content(limit=1) else "pending",
            "action_url": "/research",
            "action_label": "Fetch Sources",
        },
        {
            "number": 3,
            "title": "Generate Your First Drafts",
            "description": "Let your AI writers create content from the research.",
            "action_url": "/drafts",
            "action_label": "Generate Drafts",
            "status": "complete" if repo.get_drafts_for_issue(1) else "pending",
        },
        {
            "number": 4,
            "title": "Review & Approve",
            "description": "Read through the AI-generated drafts and approve the best ones.",
            "action_url": "/review",
            "action_label": "Review Drafts",
            "status": "pending",
        },
        {
            "number": 5,
            "title": "Assemble & Preview",
            "description": "Combine approved drafts into a complete newsletter with sponsors and trivia.",
            "action_url": "/publish",
            "action_label": "Assemble Issue",
            "status": "pending",
        },
        {
            "number": 6,
            "title": "Get Subscribers",
            "description": "Share your subscribe links or import a CSV list.",
            "action_url": "/subscribers/import",
            "action_label": "Import Subscribers",
            "status": "complete" if repo.get_subscriber_count() > 0 else "pending",
        },
        {
            "number": 7,
            "title": "Configure Email",
            "description": "Set up SMTP credentials to start sending newsletters.",
            "action_url": "/admin/setup",
            "action_label": "Setup Email",
            "status": "complete" if config.email.smtp_host and config.email.smtp_user else "pending",
        },
        {
            "number": 8,
            "title": "Publish!",
            "description": "Send your first issue to subscribers.",
            "action_url": "/publish",
            "action_label": "Publish Issue",
            "status": "pending",
        },
    ]

    completed = sum(1 for s in steps if s["status"] == "complete")

    return HTMLResponse(render("setup_wizard.html", steps=steps, completed=completed, total=len(steps), config=config))
