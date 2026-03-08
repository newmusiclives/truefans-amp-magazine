"""Schedule management routes — multi-frequency, edition-aware publishing."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from weeklyamp.content.sections import build_week_section_plan
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


@router.get("/", response_class=HTMLResponse)
async def schedule_page():
    repo = get_repo()
    cfg = get_config()
    schedules = repo.get_send_schedules()
    sections = repo.get_active_sections()
    editions = repo.get_editions()
    upcoming = repo.get_upcoming_issues(limit=12)

    return render("schedule.html",
        schedules=schedules,
        sections=sections,
        editions=editions,
        upcoming=upcoming,
        days=DAYS,
        config=cfg,
    )


@router.post("/save-day", response_class=HTMLResponse)
async def save_day(request: Request):
    form = await request.form()
    day_of_week = form.get("day_of_week", "")
    edition_slug = form.get("edition_slug", "")
    label = form.get("label", "")
    # Checkboxes send multiple values for the same name
    slugs = form.getlist("section_slugs")

    # If no sections manually picked, auto-fill from edition's section list
    if not slugs and edition_slug:
        repo = get_repo()
        edition_sections = repo.get_edition_sections(edition_slug)
        slugs = [s["slug"] for s in edition_sections]

    section_slugs = ", ".join(slugs) if slugs else ""

    repo = get_repo()
    repo.upsert_send_schedule(day_of_week, label, section_slugs, edition_slug)

    schedules = repo.get_send_schedules()
    sections = repo.get_active_sections()
    editions = repo.get_editions()
    return render("partials/schedule_table.html",
        schedules=schedules, sections=sections, editions=editions, days=DAYS)


@router.post("/remove-day/{day}", response_class=HTMLResponse)
async def remove_day(day: str, request: Request):
    form = await request.form()
    edition_slug = form.get("edition_slug", "")

    repo = get_repo()
    repo.delete_send_schedule(day, edition_slug)

    schedules = repo.get_send_schedules()
    sections = repo.get_active_sections()
    editions = repo.get_editions()
    return render("partials/schedule_table.html",
        schedules=schedules, sections=sections, editions=editions, days=DAYS)


@router.post("/create-week-issues", response_class=HTMLResponse)
async def create_week_issues(week_id: str = Form("")):
    repo = get_repo()
    schedules = repo.get_send_schedules()
    editions = repo.get_editions()

    if not week_id:
        today = datetime.now()
        week_id = today.strftime("%Y-W%W")

    # Check existing issues for this week
    existing = repo.get_issues_for_week(week_id)
    existing_keys = {(e["send_day"], e.get("edition_slug", "")) for e in existing}

    created = 0
    for sched in schedules:
        day = sched["day_of_week"]
        ed_slug = sched.get("edition_slug", "")
        if (day, ed_slug) in existing_keys:
            continue

        # Build a descriptive title
        ed_label = ed_slug.replace("_", " ").title() if ed_slug else "General"
        title = f"{ed_label} Edition — {day.title()} — {week_id}"

        num = repo.get_next_issue_number()
        repo.create_issue_with_schedule(
            issue_number=num,
            title=title,
            week_id=week_id,
            send_day=day,
            issue_template=sched.get("section_slugs", ""),
            edition_slug=ed_slug,
        )
        created += 1

    upcoming = repo.get_upcoming_issues(limit=12)
    message = f"Created {created} issues for week {week_id}" if created else f"Issues for {week_id} already exist"
    level = "success" if created else "info"
    return render("partials/schedule_table.html",
        schedules=schedules, sections=repo.get_active_sections(),
        editions=editions, days=DAYS, upcoming=upcoming,
        message=message, level=level)


@router.post("/auto-plan-week", response_class=HTMLResponse)
async def auto_plan_week():
    """Apply category rotation to fill gaps in the week's schedule."""
    repo = get_repo()
    schedules = repo.get_send_schedules()

    plan = build_week_section_plan(repo, schedules)

    updated = 0
    for day, slugs in plan.items():
        new_slugs = ", ".join(slugs)
        label = ""
        edition_slug = ""
        for s in schedules:
            if s["day_of_week"] == day:
                label = s.get("label", "")
                edition_slug = s.get("edition_slug", "")
                break
        repo.upsert_send_schedule(day, label, new_slugs, edition_slug)
        updated += 1

    schedules = repo.get_send_schedules()
    sections = repo.get_active_sections()
    editions = repo.get_editions()
    message = f"Auto-planned {updated} days with category rotation coverage"
    return render("partials/schedule_table.html",
        schedules=schedules, sections=sections, editions=editions, days=DAYS,
        message=message, level="success")
