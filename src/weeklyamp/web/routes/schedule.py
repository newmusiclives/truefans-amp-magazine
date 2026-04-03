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


def _distribute_sections(sections: list[dict], num_days: int = 3) -> list[list[str]]:
    """Split a list of sections evenly across N days."""
    slugs = [s["slug"] for s in sections]
    if not slugs:
        return [[] for _ in range(num_days)]
    buckets: list[list[str]] = [[] for _ in range(num_days)]
    for i, slug in enumerate(slugs):
        buckets[i % num_days].append(slug)
    return buckets


# ---------------------------------------------------------------------------
# Edition Layout Editor — per-day section management
# ---------------------------------------------------------------------------

def _build_day_layout(repo, edition_slug: str) -> dict:
    """Build a 3-day layout for an edition showing sections per day."""
    edition = repo.get_edition_by_slug(edition_slug)
    if not edition:
        return {}

    all_sections = repo.get_active_sections()
    section_map = {s["slug"]: s for s in all_sections}
    schedules = repo.get_send_schedules()

    # All sections belonging to this edition (master list)
    master_slugs = [s.strip() for s in edition.get("section_slugs", "").split(",") if s.strip()]

    # Build per-day columns
    days_data = []
    used_across_days = set()

    for day in SEND_DAYS:
        # Find schedule for this edition+day
        sched = None
        for s in schedules:
            if s.get("edition_slug") == edition_slug and s["day_of_week"] == day:
                sched = s
                break

        day_slugs = []
        if sched and sched.get("section_slugs"):
            day_slugs = [s.strip() for s in sched["section_slugs"].split(",") if s.strip()]

        sections_list = []
        for slug in day_slugs:
            if slug.startswith("__divider"):
                sections_list.append({"type": "divider", "slug": slug, "display_name": "— Ad Break —"})
            else:
                sec = section_map.get(slug)
                if sec:
                    sections_list.append({
                        "type": "section",
                        "slug": slug,
                        "display_name": sec.get("display_name", slug),
                        "category": sec.get("category", ""),
                        "word_count_label": sec.get("word_count_label", "medium"),
                    })
            used_across_days.add(slug)

        days_data.append({
            "day": day,
            "day_title": day.title(),
            "sections_list": sections_list,
            "section_count": len([s for s in sections_list if s["type"] == "section"]),
            "raw_slugs": ",".join(day_slugs),
        })

    # Find duplicates (sections appearing in more than one day)
    slug_day_map: dict[str, list[str]] = {}
    for dd in days_data:
        for s in dd["sections_list"]:
            if s["type"] == "section":
                slug_day_map.setdefault(s["slug"], []).append(dd["day"])
    duplicates = {slug: days for slug, days in slug_day_map.items() if len(days) > 1}

    # Sections in master list but not assigned to any day
    all_day_slugs = set()
    for dd in days_data:
        for s in dd["sections_list"]:
            if s["type"] == "section":
                all_day_slugs.add(s["slug"])
    unassigned = []
    for slug in master_slugs:
        if slug not in all_day_slugs and not slug.startswith("__divider"):
            sec = section_map.get(slug)
            if sec:
                unassigned.append(sec)

    return {
        "edition": edition,
        "days": days_data,
        "duplicates": duplicates,
        "unassigned": unassigned,
        "total_sections": len(master_slugs),
        "send_days": SEND_DAYS,
    }


def _save_day_sections(repo, edition_slug: str, day: str, section_slugs: str):
    """Save the section list for a specific edition+day schedule slot."""
    schedules = repo.get_send_schedules()
    label = ""
    for s in schedules:
        if s.get("edition_slug") == edition_slug and s["day_of_week"] == day:
            label = s.get("label", "")
            break
    if not label:
        ed = repo.get_edition_by_slug(edition_slug)
        label = f"{ed['name']} — {day.title()}" if ed else day.title()
    repo.upsert_send_schedule(day, label, section_slugs, edition_slug)


# ---------------------------------------------------------------------------
# Main schedule page
# ---------------------------------------------------------------------------

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
    if not slugs and edition_slug:
        edition_sections = repo.get_edition_sections(edition_slug)
        slugs = [s["slug"] for s in edition_sections]

    section_slugs = ", ".join(slugs) if slugs else ""
    repo.upsert_send_schedule(day_of_week, label, section_slugs, edition_slug)

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

    existing = repo.get_issues_for_week(week_id)
    existing_keys = {(e["send_day"], e.get("edition_slug", "")) for e in existing}

    created = 0
    for sched in schedules:
        day = sched["day_of_week"]
        ed_slug = sched.get("edition_slug", "")
        if (day, ed_slug) in existing_keys:
            continue

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
# Edition Layout Editor routes
# ---------------------------------------------------------------------------

@router.get("/layout/{edition_slug}", response_class=HTMLResponse)
async def edition_layout(edition_slug: str):
    repo = get_repo()
    layout = _build_day_layout(repo, edition_slug)
    if not layout:
        return render("partials/alert.html", message="Edition not found.", level="error")
    editions = repo.get_editions()
    return render("edition_layout.html", layout=layout, editions=editions)


@router.post("/layout/{edition_slug}/{day}/move/{slug}/{direction}", response_class=HTMLResponse)
async def move_section(edition_slug: str, day: str, slug: str, direction: str):
    """Move a section up or down within a specific day."""
    repo = get_repo()
    schedules = repo.get_send_schedules()
    sched = None
    for s in schedules:
        if s.get("edition_slug") == edition_slug and s["day_of_week"] == day:
            sched = s
            break
    if not sched:
        return render("partials/alert.html", message="Schedule not found.", level="error")

    slugs = [s.strip() for s in sched.get("section_slugs", "").split(",") if s.strip()]
    if slug not in slugs:
        return render("partials/alert.html", message="Section not in this day.", level="error")

    idx = slugs.index(slug)
    if direction == "up" and idx > 0:
        slugs[idx], slugs[idx - 1] = slugs[idx - 1], slugs[idx]
    elif direction == "down" and idx < len(slugs) - 1:
        slugs[idx], slugs[idx + 1] = slugs[idx + 1], slugs[idx]

    _save_day_sections(repo, edition_slug, day, ",".join(slugs))
    layout = _build_day_layout(repo, edition_slug)
    return render("partials/edition_layout_body.html", layout=layout)


@router.post("/layout/{edition_slug}/{day}/add-section", response_class=HTMLResponse)
async def add_section_to_day(edition_slug: str, day: str, slug: str = Form(...)):
    """Add a section to a specific day's lineup."""
    repo = get_repo()
    schedules = repo.get_send_schedules()
    sched = None
    for s in schedules:
        if s.get("edition_slug") == edition_slug and s["day_of_week"] == day:
            sched = s
            break

    current = []
    if sched and sched.get("section_slugs"):
        current = [s.strip() for s in sched["section_slugs"].split(",") if s.strip()]

    if slug not in current:
        current.append(slug)
        _save_day_sections(repo, edition_slug, day, ",".join(current))

    layout = _build_day_layout(repo, edition_slug)
    return render("partials/edition_layout_body.html", layout=layout,
        message=f"Added to {day.title()}", level="success")


@router.post("/layout/{edition_slug}/{day}/remove-section/{slug}", response_class=HTMLResponse)
async def remove_section_from_day(edition_slug: str, day: str, slug: str):
    """Remove a section from a specific day's lineup."""
    repo = get_repo()
    schedules = repo.get_send_schedules()
    sched = None
    for s in schedules:
        if s.get("edition_slug") == edition_slug and s["day_of_week"] == day:
            sched = s
            break

    current = []
    if sched and sched.get("section_slugs"):
        current = [s.strip() for s in sched["section_slugs"].split(",") if s.strip()]

    current = [s for s in current if s != slug]
    _save_day_sections(repo, edition_slug, day, ",".join(current))

    layout = _build_day_layout(repo, edition_slug)
    return render("partials/edition_layout_body.html", layout=layout,
        message=f"Removed from {day.title()}", level="success")


@router.post("/layout/{edition_slug}/{day}/add-divider", response_class=HTMLResponse)
async def add_divider(edition_slug: str, day: str, after: str = Form("")):
    """Insert a divider/ad break after a section in a specific day."""
    repo = get_repo()
    schedules = repo.get_send_schedules()
    sched = None
    for s in schedules:
        if s.get("edition_slug") == edition_slug and s["day_of_week"] == day:
            sched = s
            break

    current = []
    if sched and sched.get("section_slugs"):
        current = [s.strip() for s in sched["section_slugs"].split(",") if s.strip()]

    divider_count = sum(1 for s in current if s.startswith("__divider"))
    divider_slug = f"__divider_{divider_count + 1}"

    if after and after in current:
        idx = current.index(after) + 1
        current.insert(idx, divider_slug)
    else:
        current.append(divider_slug)

    _save_day_sections(repo, edition_slug, day, ",".join(current))
    layout = _build_day_layout(repo, edition_slug)
    return render("partials/edition_layout_body.html", layout=layout,
        message="Divider added", level="success")


@router.post("/layout/{edition_slug}/{from_day}/move-to/{slug}", response_class=HTMLResponse)
async def move_section_to_day(edition_slug: str, from_day: str, slug: str, to_day: str = Form(...)):
    """Move a section from one day to another within the same edition."""
    if from_day == to_day:
        layout = _build_day_layout(get_repo(), edition_slug)
        return render("partials/edition_layout_body.html", layout=layout)

    repo = get_repo()
    schedules = repo.get_send_schedules()

    # Remove from source day
    from_sched = None
    for s in schedules:
        if s.get("edition_slug") == edition_slug and s["day_of_week"] == from_day:
            from_sched = s
            break
    from_slugs = []
    if from_sched and from_sched.get("section_slugs"):
        from_slugs = [s.strip() for s in from_sched["section_slugs"].split(",") if s.strip()]
    from_slugs = [s for s in from_slugs if s != slug]
    _save_day_sections(repo, edition_slug, from_day, ",".join(from_slugs))

    # Add to target day
    to_sched = None
    for s in schedules:
        if s.get("edition_slug") == edition_slug and s["day_of_week"] == to_day:
            to_sched = s
            break
    to_slugs = []
    if to_sched and to_sched.get("section_slugs"):
        to_slugs = [s.strip() for s in to_sched["section_slugs"].split(",") if s.strip()]
    if slug not in to_slugs:
        to_slugs.append(slug)
    _save_day_sections(repo, edition_slug, to_day, ",".join(to_slugs))

    layout = _build_day_layout(repo, edition_slug)
    return render("partials/edition_layout_body.html", layout=layout,
        message=f"Moved to {to_day.title()}", level="success")


# ── Scheduled Sends ──

@router.get("/scheduled-sends", response_class=HTMLResponse)
async def scheduled_sends_page(request: Request):
    repo = get_repo()
    config = get_config()
    # Get scheduled sends
    conn = repo._conn()
    sends = conn.execute(
        "SELECT ss.*, i.issue_number, i.edition_slug FROM scheduled_sends ss LEFT JOIN issues i ON i.id = ss.issue_id ORDER BY ss.scheduled_at DESC LIMIT 50"
    ).fetchall()
    conn.close()
    sends = [dict(s) for s in sends]
    issues = repo.get_upcoming_issues(limit=20)
    editions = repo.get_editions()
    return HTMLResponse(render("scheduled_sends.html", sends=sends, issues=issues, editions=editions, config=config))


@router.post("/scheduled-sends", response_class=HTMLResponse)
async def create_scheduled_send(
    request: Request,
    issue_id: int = Form(...),
    edition_slug: str = Form(""),
    subject: str = Form(...),
    scheduled_at: str = Form(...),
):
    config = get_config()
    repo = get_repo()
    from weeklyamp.delivery.scheduler import SendScheduler
    scheduler = SendScheduler(repo, config.scheduler, config.email)
    scheduler.schedule_send(issue_id, edition_slug, subject, scheduled_at)
    return HTMLResponse('<div class="alert alert-success">Scheduled send created successfully.</div>')


@router.post("/scheduled-sends/{send_id}/cancel", response_class=HTMLResponse)
async def cancel_scheduled_send(send_id: int, request: Request):
    config = get_config()
    repo = get_repo()
    from weeklyamp.delivery.scheduler import SendScheduler
    scheduler = SendScheduler(repo, config.scheduler, config.email)
    scheduler.cancel_send(send_id)
    return HTMLResponse('<div class="alert alert-success">Send cancelled.</div>')
