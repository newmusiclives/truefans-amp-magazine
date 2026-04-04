"""Section analytics dashboard routes."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from weeklyamp.analytics.section_scoring import SectionScorer
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


def _get_scorer():
    cfg = get_config()
    repo = get_repo()
    return SectionScorer(repo, cfg.section_engagement), repo, cfg


@router.get("/", response_class=HTMLResponse)
async def section_analytics_dashboard():
    """Section performance dashboard."""
    scorer, repo, cfg = _get_scorer()
    dashboard = scorer.get_section_performance_dashboard()

    # Enrich with section display names
    sections_map = {}
    try:
        conn = repo._conn()
        rows = conn.execute("SELECT slug, display_name, description FROM section_definitions").fetchall()
        conn.close()
        sections_map = {r["slug"]: dict(r) for r in rows}
    except Exception:
        pass

    for item in dashboard:
        sec_info = sections_map.get(item["section_slug"], {})
        item["display_name"] = sec_info.get("display_name", item["section_slug"])
        item["description"] = sec_info.get("description", "")

    return render("section_analytics.html",
        dashboard=dashboard,
        enabled=cfg.section_engagement.enabled,
    )


@router.get("/{section_slug}", response_class=HTMLResponse)
async def section_analytics_detail(section_slug: str):
    """Per-section detail page."""
    scorer, repo, cfg = _get_scorer()

    # Get section info
    section = repo.get_section(section_slug)
    section_name = section["display_name"] if section else section_slug
    section_desc = section.get("description", "") if section else ""

    # Per-issue breakdown
    per_issue = repo.get_section_performance(section_slug, limit=50)

    # Enrich with issue info
    for item in per_issue:
        issue = repo.get_issue(item["issue_id"])
        if issue:
            item["issue_number"] = issue.get("issue_number", "?")
            item["issue_title"] = issue.get("title", "")
            item["edition_slug"] = issue.get("edition_slug", "")

    # Genre tags
    genres = repo.get_section_genres(section_slug)

    return render("section_analytics_detail.html",
        section_slug=section_slug,
        section_name=section_name,
        section_desc=section_desc,
        per_issue=per_issue,
        genres=genres,
        enabled=cfg.section_engagement.enabled,
    )


@router.post("/recompute", response_class=HTMLResponse)
async def recompute_scores():
    """Trigger score recomputation for recent issues."""
    scorer, repo, cfg = _get_scorer()

    try:
        conn = repo._conn()
        rows = conn.execute(
            "SELECT id FROM issues ORDER BY issue_number DESC LIMIT 10"
        ).fetchall()
        conn.close()

        total = 0
        for r in rows:
            stats = scorer.compute_section_scores(r["id"])
            total += len(stats)

        message = f"Recomputed scores for {len(rows)} issues ({total} section scores)"
        level = "success"
    except Exception as exc:
        message = f"Recomputation failed: {exc}"
        level = "error"

    dashboard = scorer.get_section_performance_dashboard()

    sections_map = {}
    try:
        conn = repo._conn()
        srows = conn.execute("SELECT slug, display_name, description FROM section_definitions").fetchall()
        conn.close()
        sections_map = {r["slug"]: dict(r) for r in srows}
    except Exception:
        pass

    for item in dashboard:
        sec_info = sections_map.get(item["section_slug"], {})
        item["display_name"] = sec_info.get("display_name", item["section_slug"])
        item["description"] = sec_info.get("description", "")

    return render("section_analytics.html",
        dashboard=dashboard,
        enabled=cfg.section_engagement.enabled,
        message=message,
        level=level,
    )


@router.get("/personalization", response_class=HTMLResponse)
async def personalization_settings():
    """Content personalization settings and segment overview."""
    repo = get_repo()
    config = get_config()
    from weeklyamp.content.assembly import get_subscriber_segments
    segments = get_subscriber_segments(repo)
    segment_summary = {k: len(v) for k, v in segments.items()}
    return HTMLResponse(render("personalization.html", segments=segment_summary, config=config))
