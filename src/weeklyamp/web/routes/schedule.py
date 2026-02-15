"""Schedule management routes — multi-frequency publishing."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


@router.get("/", response_class=HTMLResponse)
async def schedule_page():
    repo = get_repo()
    cfg = get_config()
    schedules = repo.get_send_schedules()
    sections = repo.get_active_sections()
    upcoming = repo.get_upcoming_issues(limit=8)

    return render("schedule.html",
        schedules=schedules,
        sections=sections,
        upcoming=upcoming,
        days=DAYS,
        config=cfg,
    )


@router.post("/save-day", response_class=HTMLResponse)
async def save_day(
    day_of_week: str = Form(...),
    label: str = Form(""),
    section_slugs: str = Form(""),
):
    repo = get_repo()
    repo.upsert_send_schedule(day_of_week, label, section_slugs)

    schedules = repo.get_send_schedules()
    sections = repo.get_active_sections()
    return render("partials/schedule_table.html",
        schedules=schedules, sections=sections, days=DAYS)


@router.post("/remove-day/{day}", response_class=HTMLResponse)
async def remove_day(day: str):
    repo = get_repo()
    repo.delete_send_schedule(day)

    schedules = repo.get_send_schedules()
    sections = repo.get_active_sections()
    return render("partials/schedule_table.html",
        schedules=schedules, sections=sections, days=DAYS)


@router.post("/create-week-issues", response_class=HTMLResponse)
async def create_week_issues(week_id: str = Form("")):
    repo = get_repo()
    schedules = repo.get_send_schedules()

    if not week_id:
        # Use current ISO week
        today = datetime.now()
        week_id = today.strftime("%Y-W%W")

    # Check if issues already exist for this week
    existing = repo.get_issues_for_week(week_id)
    existing_days = {e["send_day"] for e in existing}

    created = 0
    for sched in schedules:
        day = sched["day_of_week"]
        if day in existing_days:
            continue
        num = repo.get_next_issue_number()
        repo.create_issue_with_schedule(
            issue_number=num,
            title=f"{sched.get('label', day.title())} — {week_id}",
            week_id=week_id,
            send_day=day,
            issue_template=sched.get("section_slugs", ""),
        )
        created += 1

    upcoming = repo.get_upcoming_issues(limit=8)
    message = f"Created {created} issues for week {week_id}" if created else f"Issues for {week_id} already exist"
    level = "success" if created else "info"
    return render("partials/schedule_table.html",
        schedules=schedules, sections=repo.get_active_sections(),
        days=DAYS, upcoming=upcoming, message=message, level=level)
