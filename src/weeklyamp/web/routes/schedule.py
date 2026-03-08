"""Schedule management routes — 3 newsletters × 3 days = 9 issues per week."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()

SEND_DAYS = ["monday", "wednesday", "saturday"]
ALL_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _build_schedule_grid(repo) -> list[dict]:
    """Build a grid showing each edition × day with its schedule status."""
    editions = repo.get_editions()
    schedules = repo.get_send_schedules()

    # Index schedules by (edition_slug, day_of_week)
    sched_map = {}
    for s in schedules:
        key = (s.get("edition_slug", ""), s["day_of_week"])
        sched_map[key] = s

    grid = []
    for ed in editions:
        ed_entry = {
            "slug": ed["slug"],
            "name": ed["name"],
            "color": ed.get("color", "#6b7280"),
            "icon": ed.get("icon", ""),
            "tagline": ed.get("tagline", ""),
            "section_slugs": ed.get("section_slugs", ""),
            "days": [],
        }
        for day in SEND_DAYS:
            sched = sched_map.get((ed["slug"], day))
            ed_entry["days"].append({
                "day": day,
                "configured": sched is not None,
                "label": sched.get("label", "") if sched else "",
                "section_slugs": sched.get("section_slugs", "") if sched else "",
            })
        grid.append(ed_entry)
    return grid


@router.get("/", response_class=HTMLResponse)
async def schedule_page():
    repo = get_repo()
    cfg = get_config()
    editions = repo.get_editions()
    grid = _build_schedule_grid(repo)
    sections = repo.get_active_sections()
    upcoming = repo.get_upcoming_issues(limit=15)

    return render("schedule.html",
        grid=grid,
        editions=editions,
        sections=sections,
        upcoming=upcoming,
        send_days=SEND_DAYS,
        all_days=ALL_DAYS,
        config=cfg,
    )


@router.post("/save-day", response_class=HTMLResponse)
async def save_day(request: Request):
    form = await request.form()
    day_of_week = form.get("day_of_week", "")
    edition_slug = form.get("edition_slug", "")
    label = form.get("label", "")
    slugs = form.getlist("section_slugs")

    repo = get_repo()

    # If no sections manually picked, auto-fill from edition's section list
    if not slugs and edition_slug:
        edition_sections = repo.get_edition_sections(edition_slug)
        slugs = [s["slug"] for s in edition_sections]

    section_slugs = ", ".join(slugs) if slugs else ""
    repo.upsert_send_schedule(day_of_week, label, section_slugs, edition_slug)

    # Return updated grid
    grid = _build_schedule_grid(repo)
    editions = repo.get_editions()
    sections = repo.get_active_sections()
    return render("partials/schedule_grid.html",
        grid=grid, editions=editions, sections=sections, send_days=SEND_DAYS)


@router.post("/remove-day/{edition_slug}/{day}", response_class=HTMLResponse)
async def remove_day(edition_slug: str, day: str):
    repo = get_repo()
    repo.delete_send_schedule(day, edition_slug)

    grid = _build_schedule_grid(repo)
    editions = repo.get_editions()
    sections = repo.get_active_sections()
    return render("partials/schedule_grid.html",
        grid=grid, editions=editions, sections=sections, send_days=SEND_DAYS)


@router.post("/setup-all", response_class=HTMLResponse)
async def setup_all():
    """One-click setup: create all 9 schedule slots (3 editions × 3 days)."""
    repo = get_repo()
    editions = repo.get_editions()
    created = 0

    for ed in editions:
        edition_sections = repo.get_edition_sections(ed["slug"])
        section_slugs = ", ".join(s["slug"] for s in edition_sections)

        for day in SEND_DAYS:
            label = f"{ed['name']} — {day.title()}"
            repo.upsert_send_schedule(day, label, section_slugs, ed["slug"])
            created += 1

    grid = _build_schedule_grid(repo)
    sections = repo.get_active_sections()
    return render("partials/schedule_grid.html",
        grid=grid, editions=editions, sections=sections, send_days=SEND_DAYS,
        message=f"Set up {created} schedule slots (3 editions × 3 days)", level="success")


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

        # Find edition name
        ed_name = "General"
        for ed in editions:
            if ed["slug"] == ed_slug:
                ed_name = ed["name"]
                break

        title = f"{ed_name} — {day.title()} — {week_id}"
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

    upcoming = repo.get_upcoming_issues(limit=15)
    grid = _build_schedule_grid(repo)
    sections = repo.get_active_sections()
    message = f"Created {created} issues for week {week_id}" if created else f"Issues for {week_id} already exist"
    level = "success" if created else "info"
    return render("partials/schedule_grid.html",
        grid=grid, editions=editions, sections=sections, send_days=SEND_DAYS,
        upcoming=upcoming, message=message, level=level)
