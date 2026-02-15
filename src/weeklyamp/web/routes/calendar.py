"""Editorial calendar routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Form
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
