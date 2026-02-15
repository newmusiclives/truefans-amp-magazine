"""Dashboard route — main overview page."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard():
    cfg = get_config()
    repo = get_repo()
    issue = repo.get_current_issue()
    sections = repo.get_active_sections()
    counts = repo.get_table_counts()

    drafts = []
    draft_map = {}
    if issue:
        drafts = repo.get_drafts_for_issue(issue["id"])
        draft_map = {d["section_slug"]: d for d in drafts}

    approved = sum(1 for d in drafts if d["status"] == "approved")
    pending = sum(1 for d in drafts if d["status"] == "pending")
    rejected = sum(1 for d in drafts if d["status"] == "rejected")

    # Sponsor stats for current issue
    sponsor_stats = None
    if issue:
        blocks = repo.get_sponsor_blocks_for_issue(issue["id"])
        bookings = repo.get_bookings_for_issue(issue["id"])
        booked = len(blocks) + len(bookings)
        sponsor_stats = {
            "booked": booked,
            "open": max(0, cfg.sponsor_slots.max_per_issue - booked),
        }

    # Upcoming sends (multi-frequency)
    upcoming_sends = repo.get_upcoming_issues(limit=5)

    return render("dashboard.html",
        config=cfg,
        issue=issue,
        sections=sections,
        draft_map=draft_map,
        counts=counts,
        stats={"approved": approved, "pending": pending, "rejected": rejected, "total": len(sections)},
        sponsor_stats=sponsor_stats,
        upcoming_sends=upcoming_sends if len(upcoming_sends) > 1 else [],
    )
