"""Growth metrics and social posts routes."""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from weeklyamp.agents.orchestrator import AgentOrchestrator
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def growth_page():
    repo = get_repo()
    metrics = repo.get_growth_metrics(limit=30)
    trend = repo.get_growth_trend(days=30)
    subscriber_count = repo.get_subscriber_count()
    return render("growth.html",
        metrics=metrics, trend=trend,
        subscriber_count=subscriber_count,
    )


@router.post("/sync", response_class=HTMLResponse)
async def sync_metrics():
    repo = get_repo()
    # Pull from Beehiiv if configured
    config = get_config()
    subscriber_count = repo.get_subscriber_count()

    try:
        from datetime import date
        repo.save_growth_metric(
            metric_date=date.today().isoformat(),
            total_subscribers=subscriber_count,
        )
        message = f"Metrics synced. {subscriber_count} subscribers."
        level = "success"
    except Exception as e:
        message = f"Sync failed: {e}"
        level = "error"

    metrics = repo.get_growth_metrics(limit=30)
    trend = repo.get_growth_trend(days=30)
    return render("growth.html",
        metrics=metrics, trend=trend,
        subscriber_count=subscriber_count,
        message=message, level=level,
    )


@router.get("/social", response_class=HTMLResponse)
async def social_page():
    repo = get_repo()
    posts = repo.get_social_posts(limit=50)
    return render("growth_social.html", posts=posts)


@router.post("/social/generate", response_class=HTMLResponse)
async def generate_social(issue_id: int = Form(...)):
    repo = get_repo()
    config = get_config()
    orchestrator = AgentOrchestrator(repo, config)

    try:
        result = orchestrator.trigger_agent(
            "growth", "draft_social_posts", issue_id=issue_id,
        )
        message = f"Generated social posts for issue #{issue_id}."
        level = "success"
    except Exception as e:
        message = f"Failed: {e}"
        level = "error"

    posts = repo.get_social_posts(limit=50)
    return render("growth_social.html", posts=posts,
        message=message, level=level)
