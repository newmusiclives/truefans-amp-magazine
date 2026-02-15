"""Subscriber routes."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from weeklyamp.delivery.subscribers import sync_subscribers
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def subscribers_page():
    cfg = get_config()
    repo = get_repo()
    active = repo.get_subscriber_count()
    subs = repo.get_subscribers("active")
    issue = repo.get_current_issue()
    engagement = repo.get_engagement(issue["id"]) if issue else None
    has_beehiiv = bool(cfg.beehiiv.api_key and cfg.beehiiv.publication_id)

    return render("subscribers.html",
        active=active,
        subscribers=subs,
        engagement=engagement,
        issue=issue,
        has_beehiiv=has_beehiiv,
    )


@router.post("/sync", response_class=HTMLResponse)
async def sync():
    cfg = get_config()
    repo = get_repo()

    if not cfg.beehiiv.api_key:
        return render("partials/alert.html", message="Beehiiv not configured.", level="error")

    try:
        result = sync_subscribers(repo, cfg.beehiiv)
        return render("partials/alert.html",
            message=f"Synced {result['synced']} subscribers ({result['new']} new, {result['total']} total).",
            level="success")
    except Exception as exc:
        return render("partials/alert.html", message=f"Sync failed: {exc}", level="error")
