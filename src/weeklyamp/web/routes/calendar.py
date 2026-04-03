"""Editorial calendar routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def calendar_page():
    repo = get_repo()
    calendar = repo.get_calendar(limit=20)
    upcoming_issues = repo.get_upcoming_issues(limit=10)
    return render("editorial_calendar.html",
        calendar=calendar, upcoming_issues=upcoming_issues,
    )


@router.post("/plan", response_class=HTMLResponse)
async def plan_issue(
    issue_id: int = Form(0),
    planned_date: str = Form(""),
    theme: str = Form(""),
    notes: str = Form(""),
    section_slugs: str = Form(""),
):
    repo = get_repo()
    try:
        section_assignments = json.dumps(
            [s.strip() for s in section_slugs.split(",") if s.strip()]
        ) if section_slugs else "{}"

        repo.create_calendar_entry(
            issue_id=issue_id if issue_id else None,
            planned_date=planned_date,
            theme=theme,
            notes=notes,
            section_assignments=section_assignments,
            status="planned",
        )
        message = "Calendar entry created."
        level = "success"
    except Exception as e:
        message = f"Failed: {e}"
        level = "error"

    calendar = repo.get_calendar(limit=20)
    upcoming_issues = repo.get_upcoming_issues(limit=10)
    return render("editorial_calendar.html",
        calendar=calendar, upcoming_issues=upcoming_issues,
        message=message, level=level,
    )


@router.post("/{entry_id}/assign", response_class=HTMLResponse)
async def assign_to_calendar(
    entry_id: int,
    section_slugs: str = Form(""),
    agent_assignments: str = Form(""),
    status: str = Form("planned"),
):
    repo = get_repo()
    try:
        updates = {"status": status}
        if section_slugs:
            updates["section_assignments"] = json.dumps(
                [s.strip() for s in section_slugs.split(",") if s.strip()]
            )
        if agent_assignments:
            updates["agent_assignments"] = agent_assignments
        repo.update_calendar_entry(entry_id, **updates)
        message = "Calendar entry updated."
        level = "success"
    except Exception as e:
        message = f"Failed: {e}"
        level = "error"

    calendar = repo.get_calendar(limit=20)
    upcoming_issues = repo.get_upcoming_issues(limit=10)
    return render("editorial_calendar.html",
        calendar=calendar, upcoming_issues=upcoming_issues,
        message=message, level=level,
    )


@router.post("/auto-plan", response_class=HTMLResponse)
async def auto_plan_week(request: Request, target_week: str = Form("")):
    """AI-assisted planning — generates suggested content plan for next week."""
    repo = get_repo()
    config = get_config()

    from datetime import datetime, timedelta
    if not target_week:
        today = datetime.now()
        next_monday = today + timedelta(days=(7 - today.weekday()))
        target_week = next_monday.strftime("%Y-W%W")

    # Get top research content for inspiration
    research = repo.get_unused_content(limit=20)
    editions = repo.get_editions()
    sections_all = repo.get_all_sections()

    # Build plan summary
    plan_entries = []
    for ed in editions:
        ed_sections = [s for s in sections_all if s.get("slug") in (ed.get("section_slugs", "") or "").split(",")]
        for day_idx, day in enumerate(["monday", "wednesday", "saturday"]):
            day_sections = ed_sections[day_idx*5:(day_idx+1)*5] if len(ed_sections) >= 15 else ed_sections[:5]
            plan_entries.append({
                "edition": ed["name"],
                "edition_slug": ed["slug"],
                "day": day,
                "sections": [s.get("display_name", s.get("slug", "")) for s in day_sections],
                "research_available": len([r for r in research if any(s.get("slug", "") in (r.get("matched_sections", "") or "") for s in day_sections)]),
            })

    return HTMLResponse(render("calendar_plan.html", plan=plan_entries, target_week=target_week))
