"""Schedule management routes — 3 newsletters × 3 days = 9 issues per week."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

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


def _distribute_sections(sections: list[dict], num_days: int = 3) -> list[list[str]]:
    """Split a list of sections evenly across N days.

    Returns a list of N lists of section slugs, balanced by count.
    Example: 7 sections → [3, 2, 2] or 10 sections → [4, 3, 3].
    """
    slugs = [s["slug"] for s in sections]
    if not slugs:
        return [[] for _ in range(num_days)]

    buckets: list[list[str]] = [[] for _ in range(num_days)]
    for i, slug in enumerate(slugs):
        buckets[i % num_days].append(slug)
    return buckets


@router.post("/setup-all", response_class=HTMLResponse)
async def setup_all():
    """One-click setup: distribute sections across 3 days for each of 3 editions."""
    repo = get_repo()
    editions = repo.get_editions()
    created = 0

    for ed in editions:
        edition_sections = repo.get_edition_sections(ed["slug"])
        day_buckets = _distribute_sections(edition_sections, len(SEND_DAYS))

        for i, day in enumerate(SEND_DAYS):
            section_slugs = ", ".join(day_buckets[i])
            label = f"{ed['name']} — {day.title()}"
            repo.upsert_send_schedule(day, label, section_slugs, ed["slug"])
            created += 1

    grid = _build_schedule_grid(repo)
    sections = repo.get_active_sections()
    return render("partials/schedule_grid.html",
        grid=grid, editions=editions, sections=sections, send_days=SEND_DAYS,
        message=f"Set up {created} slots — sections distributed evenly across days", level="success")


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


# ---------------------------------------------------------------------------
# Edition Layout Editor — reorder sections, add/remove, dividers
# ---------------------------------------------------------------------------

def _build_edition_layout(repo, edition_slug: str) -> dict:
    """Build the full layout for an edition, including section details."""
    edition = repo.get_edition_by_slug(edition_slug)
    if not edition:
        return {}

    # Parse the ordered section slugs (may include __divider__ markers)
    raw_slugs = [s.strip() for s in edition.get("section_slugs", "").split(",") if s.strip()]

    all_sections = repo.get_active_sections()
    section_map = {s["slug"]: s for s in all_sections}

    items = []
    for slug in raw_slugs:
        if slug.startswith("__divider"):
            items.append({"type": "divider", "slug": slug, "display_name": "— Divider —"})
        else:
            sec = section_map.get(slug)
            if sec:
                items.append({
                    "type": "section",
                    "slug": slug,
                    "display_name": sec.get("display_name", slug),
                    "category": sec.get("category", ""),
                    "word_count_label": sec.get("word_count_label", "medium"),
                })

    # Sections available but not in this edition
    used_slugs = {s for s in raw_slugs if not s.startswith("__divider")}
    available = [s for s in all_sections if s["slug"] not in used_slugs]

    return {
        "edition": edition,
        "items": items,
        "available": available,
        "total_sections": len([i for i in items if i["type"] == "section"]),
    }


@router.get("/layout/{edition_slug}", response_class=HTMLResponse)
async def edition_layout(edition_slug: str):
    repo = get_repo()
    layout = _build_edition_layout(repo, edition_slug)
    if not layout:
        return render("partials/alert.html", message="Edition not found.", level="error")

    editions = repo.get_editions()
    return render("edition_layout.html", layout=layout, editions=editions)


@router.post("/layout/{edition_slug}/reorder", response_class=HTMLResponse)
async def reorder_sections(edition_slug: str, request: Request):
    """Save the reordered section list for an edition."""
    form = await request.form()
    # section_order is a hidden field with comma-separated slugs in new order
    section_order = form.get("section_order", "")

    repo = get_repo()
    repo.update_edition_sections(edition_slug, section_order)

    layout = _build_edition_layout(repo, edition_slug)
    return render("partials/edition_layout_body.html", layout=layout,
        message="Section order saved!", level="success")


@router.post("/layout/{edition_slug}/move/{slug}/{direction}", response_class=HTMLResponse)
async def move_section(edition_slug: str, slug: str, direction: str):
    """Move a section up or down in the edition's order."""
    repo = get_repo()
    edition = repo.get_edition_by_slug(edition_slug)
    if not edition:
        return render("partials/alert.html", message="Edition not found.", level="error")

    slugs = [s.strip() for s in edition.get("section_slugs", "").split(",") if s.strip()]
    if slug not in slugs:
        return render("partials/alert.html", message="Section not in edition.", level="error")

    idx = slugs.index(slug)
    if direction == "up" and idx > 0:
        slugs[idx], slugs[idx - 1] = slugs[idx - 1], slugs[idx]
    elif direction == "down" and idx < len(slugs) - 1:
        slugs[idx], slugs[idx + 1] = slugs[idx + 1], slugs[idx]

    repo.update_edition_sections(edition_slug, ",".join(slugs))
    layout = _build_edition_layout(repo, edition_slug)
    return render("partials/edition_layout_body.html", layout=layout)


@router.post("/layout/{edition_slug}/add-section", response_class=HTMLResponse)
async def add_section_to_edition(edition_slug: str, slug: str = Form(...)):
    """Add a section to the end of an edition's lineup."""
    repo = get_repo()
    edition = repo.get_edition_by_slug(edition_slug)
    if not edition:
        return render("partials/alert.html", message="Edition not found.", level="error")

    slugs = [s.strip() for s in edition.get("section_slugs", "").split(",") if s.strip()]
    if slug not in slugs:
        slugs.append(slug)
        repo.update_edition_sections(edition_slug, ",".join(slugs))

    layout = _build_edition_layout(repo, edition_slug)
    return render("partials/edition_layout_body.html", layout=layout,
        message=f"Added {slug}", level="success")


@router.post("/layout/{edition_slug}/remove-section/{slug}", response_class=HTMLResponse)
async def remove_section_from_edition(edition_slug: str, slug: str):
    """Remove a section from an edition's lineup."""
    repo = get_repo()
    edition = repo.get_edition_by_slug(edition_slug)
    if not edition:
        return render("partials/alert.html", message="Edition not found.", level="error")

    slugs = [s.strip() for s in edition.get("section_slugs", "").split(",") if s.strip()]
    slugs = [s for s in slugs if s != slug]
    repo.update_edition_sections(edition_slug, ",".join(slugs))

    layout = _build_edition_layout(repo, edition_slug)
    return render("partials/edition_layout_body.html", layout=layout,
        message=f"Removed {slug}", level="success")


@router.post("/layout/{edition_slug}/add-divider", response_class=HTMLResponse)
async def add_divider(edition_slug: str, after: str = Form("")):
    """Insert a divider after a given section slug."""
    repo = get_repo()
    edition = repo.get_edition_by_slug(edition_slug)
    if not edition:
        return render("partials/alert.html", message="Edition not found.", level="error")

    slugs = [s.strip() for s in edition.get("section_slugs", "").split(",") if s.strip()]

    # Generate unique divider ID
    divider_count = sum(1 for s in slugs if s.startswith("__divider"))
    divider_slug = f"__divider_{divider_count + 1}"

    if after and after in slugs:
        idx = slugs.index(after) + 1
        slugs.insert(idx, divider_slug)
    else:
        slugs.append(divider_slug)

    repo.update_edition_sections(edition_slug, ",".join(slugs))
    layout = _build_edition_layout(repo, edition_slug)
    return render("partials/edition_layout_body.html", layout=layout,
        message="Divider added", level="success")
