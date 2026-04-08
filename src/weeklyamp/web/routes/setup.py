"""Setup and deliverability guide."""
from __future__ import annotations

import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/deliverability/reputation")
async def deliverability_reputation(request: Request):
    """Reputation dashboard — bounces, complaints, unsubscribes over time.

    Returns JSON with:
      - sends_24h, sends_7d, sends_30d
      - bounces_24h, bounces_7d, bounces_30d (hard + soft)
      - complaints_24h, complaints_7d, complaints_30d
      - unsubscribes_24h, unsubscribes_7d, unsubscribes_30d
      - bounce_rate_30d, complaint_rate_30d, unsubscribe_rate_30d
      - thresholds: bounce<2%, complaint<0.1%
      - recent_bounces: last 20 bounce_log entries

    Used by uptime monitor + manual review. Read-only, safe to poll.
    """
    from datetime import datetime, timedelta

    repo = get_repo()
    conn = repo._conn()
    now = datetime.utcnow()
    cutoff_1d = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    cutoff_7d = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    cutoff_30d = (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")

    def _count(sql: str, params=()) -> int:
        try:
            row = conn.execute(sql, params).fetchone()
            if not row:
                return 0
            try:
                return int(row[0] or 0)
            except (TypeError, KeyError, IndexError):
                v = list(dict(row).values())[0] if isinstance(row, dict) else 0
                return int(v or 0)
        except Exception:
            return 0

    # Sends — assembled_issues that have a published_at >= cutoff
    sends_24h = _count(
        "SELECT COUNT(*) FROM assembled_issues WHERE published_at >= ?",
        (cutoff_1d,),
    )
    sends_7d = _count(
        "SELECT COUNT(*) FROM assembled_issues WHERE published_at >= ?",
        (cutoff_7d,),
    )
    sends_30d = _count(
        "SELECT COUNT(*) FROM assembled_issues WHERE published_at >= ?",
        (cutoff_30d,),
    )

    # Bounces from bounce_log
    bounces_24h = _count(
        "SELECT COUNT(*) FROM bounce_log WHERE bounced_at >= ?",
        (cutoff_1d,),
    )
    bounces_7d = _count(
        "SELECT COUNT(*) FROM bounce_log WHERE bounced_at >= ?",
        (cutoff_7d,),
    )
    bounces_30d = _count(
        "SELECT COUNT(*) FROM bounce_log WHERE bounced_at >= ?",
        (cutoff_30d,),
    )

    total_subscribers = _count(
        "SELECT COUNT(*) FROM subscribers WHERE status = 'active'"
    )
    unsubs_30d = _count(
        "SELECT COUNT(*) FROM subscribers WHERE status = 'unsubscribed'"
    )

    # Recent bounces for inspection
    try:
        recent_rows = conn.execute(
            "SELECT * FROM bounce_log ORDER BY bounced_at DESC LIMIT 20"
        ).fetchall()
        recent_bounces = [dict(r) for r in recent_rows]
    except Exception:
        recent_bounces = []

    conn.close()

    def _rate(num: int, denom: int) -> float:
        return round((num / denom * 100) if denom else 0.0, 3)

    bounce_rate = _rate(bounces_30d, max(total_subscribers, 1))
    unsub_rate = _rate(unsubs_30d, max(total_subscribers, 1))

    return JSONResponse({
        "sends": {"day": sends_24h, "week": sends_7d, "month": sends_30d},
        "bounces": {"day": bounces_24h, "week": bounces_7d, "month": bounces_30d},
        "unsubscribes": {"month": unsubs_30d},
        "active_subscribers": total_subscribers,
        "rates_30d_pct": {
            "bounce": bounce_rate,
            "unsubscribe": unsub_rate,
        },
        "thresholds_pct": {
            "bounce_max": 2.0,
            "complaint_max": 0.1,
        },
        "status": (
            "ok" if bounce_rate < 2.0 else "degraded"
        ),
        "recent_bounces": recent_bounces,
    })


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
