"""Growth metrics and social posts routes."""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from fastapi import Request

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
    config = get_config()
    subscriber_count = repo.get_subscriber_count()

    try:
        from datetime import date
        repo.save_growth_metric(
            metric_date=date.today().isoformat(),
            total_subscribers=subscriber_count,
        )
        return render("partials/alert.html",
            message=f"Metrics synced. {subscriber_count} subscribers.",
            level="success")
    except Exception as e:
        return render("partials/alert.html",
            message=f"Sync failed: {e}", level="error")


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
        return render("partials/alert.html",
            message=f"Generated social posts for issue #{issue_id}.",
            level="success")
    except Exception as e:
        return render("partials/alert.html",
            message=f"Failed: {e}", level="error")


@router.post("/social/publish/{post_id}", response_class=HTMLResponse)
async def publish_post(post_id: int, request: Request):
    repo = get_repo()
    from weeklyamp.delivery.social import publish_social_post
    result = publish_social_post(repo, post_id)
    if result["status"] == "posted":
        return HTMLResponse(f'<span class="badge badge-success">Posted</span>')
    return HTMLResponse(f'<span class="badge badge-danger">Failed: {result.get("message", "")}</span>')

@router.post("/social/publish-all", response_class=HTMLResponse)
async def publish_all(request: Request):
    repo = get_repo()
    from weeklyamp.delivery.social import publish_all_pending
    results = publish_all_pending(repo)
    return HTMLResponse(f'<div class="alert alert-success">Posted: {results["posted"]}, Failed: {results["failed"]}, Skipped: {results["skipped"]}</div>')


@router.get("/report", response_class=HTMLResponse)
async def weekly_report(request: Request):
    repo = get_repo()
    config = get_config()
    from weeklyamp.content.weekly_report import generate_weekly_report

    report_html = generate_weekly_report(repo, config)
    return HTMLResponse(render("weekly_report.html", report_html=report_html))


@router.post("/report/send", response_class=HTMLResponse)
async def send_report_email(request: Request):
    repo = get_repo()
    config = get_config()
    from weeklyamp.content.weekly_report import send_weekly_report_email
    success = send_weekly_report_email(repo, config)
    if success:
        return HTMLResponse('<div class="alert alert-success">Report sent to admin email.</div>')
    return HTMLResponse('<div class="alert alert-warning">Email not configured or send failed. Check SMTP settings.</div>')
