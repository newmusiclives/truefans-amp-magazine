"""Sponsor & ad block management routes.

Manages:
- Sponsor directory (CRM contacts, bookings, revenue)
- 9 main sponsors: 3 newsletters x 3 editions x 1 sponsor
- 27 ad block slots: 3 newsletters x 3 editions x 3 positions
"""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from weeklyamp.web.deps import get_repo, render

router = APIRouter()

POSITIONS = ["top", "mid", "bottom"]
EDITION_NUMBERS = [1, 2, 3]
BOOKING_STATUSES = ["inquiry", "booked", "confirmed", "delivered", "invoiced", "paid"]


def _build_data(repo):
    """Build the grid data for both main sponsors and ad blocks."""
    editions = repo.get_editions(active_only=True)
    all_blocks = repo.get_all_sponsor_blocks()
    all_main = repo.get_all_edition_sponsors()

    block_map = {}
    for b in all_blocks:
        key = (b["edition_slug"], b["edition_number"], b["position"])
        block_map[key] = b

    main_map = {}
    for m in all_main:
        key = (m["edition_slug"], m["edition_number"])
        main_map[key] = m

    grid = []
    total_main = 0
    for ed in editions:
        edition_rows = []
        for num in EDITION_NUMBERS:
            main = main_map.get((ed["slug"], num))
            if main:
                total_main += 1
            slots = []
            for pos in POSITIONS:
                block = block_map.get((ed["slug"], num, pos))
                slots.append({"position": pos, "block": block})
            edition_rows.append({
                "number": num,
                "main_sponsor": main,
                "slots": slots,
                "filled": sum(1 for s in slots if s["block"]),
            })
        grid.append({
            "edition": ed,
            "rows": edition_rows,
            "total_filled": sum(r["filled"] for r in edition_rows),
            "total_main": sum(1 for r in edition_rows if r["main_sponsor"]),
        })

    total_filled = sum(g["total_filled"] for g in grid)
    sponsors = repo.get_sponsors()
    revenue = repo.get_sponsor_revenue_summary()
    return grid, total_filled, total_main, sponsors, revenue


@router.get("/", response_class=HTMLResponse)
async def sponsor_blocks_page():
    repo = get_repo()
    grid, total_filled, total_main, sponsors, revenue = _build_data(repo)

    return render("sponsor_blocks.html",
        grid=grid,
        positions=POSITIONS,
        edition_numbers=EDITION_NUMBERS,
        total_filled=total_filled,
        total_slots=27,
        total_main=total_main,
        sponsors=sponsors,
        revenue=revenue,
        statuses=BOOKING_STATUSES,
    )


# ---- Ad Block CRUD ----

@router.post("/add", response_class=HTMLResponse)
async def add_block(
    edition_slug: str = Form(...),
    edition_number: int = Form(...),
    position: str = Form("mid"),
    sponsor_name: str = Form(""),
    headline: str = Form(""),
    body_html: str = Form(""),
    cta_url: str = Form(""),
    cta_text: str = Form("Learn More"),
    image_url: str = Form(""),
):
    repo = get_repo()
    issue = repo.get_current_issue()
    issue_id = issue["id"] if issue else 0

    existing = repo.get_sponsor_blocks_for_edition(edition_slug, edition_number)
    for b in existing:
        if b["position"] == position:
            return render("partials/alert.html",
                message=f"Slot already filled: {edition_slug} Ed.{edition_number} {position}. Delete the existing block first.",
                level="error")

    repo.create_sponsor_block(
        issue_id=issue_id, position=position, sponsor_name=sponsor_name,
        headline=headline, body_html=body_html, cta_url=cta_url,
        cta_text=cta_text, image_url=image_url,
        edition_slug=edition_slug, edition_number=edition_number,
    )

    grid, total_filled, total_main, sponsors, revenue = _build_data(repo)
    return render("partials/sponsor_blocks_grid.html",
        grid=grid, positions=POSITIONS, edition_numbers=EDITION_NUMBERS,
        total_filled=total_filled, total_slots=27, total_main=total_main,
        sponsors=sponsors, revenue=revenue, statuses=BOOKING_STATUSES,
        message=f"Ad block added: {edition_slug} Ed.{edition_number} ({position})", level="success")


@router.post("/delete/{block_id}", response_class=HTMLResponse)
async def delete_block(block_id: int):
    repo = get_repo()
    block = repo.get_sponsor_block(block_id)
    repo.delete_sponsor_block(block_id)

    grid, total_filled, total_main, sponsors, revenue = _build_data(repo)
    label = f"{block['edition_slug']} Ed.{block['edition_number']} ({block['position']})" if block else ""
    return render("partials/sponsor_blocks_grid.html",
        grid=grid, positions=POSITIONS, edition_numbers=EDITION_NUMBERS,
        total_filled=total_filled, total_slots=27, total_main=total_main,
        sponsors=sponsors, revenue=revenue, statuses=BOOKING_STATUSES,
        message=f"Deleted ad block: {label}" if label else "Block deleted", level="success")


@router.post("/update/{block_id}", response_class=HTMLResponse)
async def update_block(
    block_id: int,
    sponsor_name: str = Form(""),
    headline: str = Form(""),
    body_html: str = Form(""),
    cta_url: str = Form(""),
    cta_text: str = Form("Learn More"),
    image_url: str = Form(""),
):
    repo = get_repo()
    repo.update_sponsor_block(block_id,
        sponsor_name=sponsor_name, headline=headline, body_html=body_html,
        cta_url=cta_url, cta_text=cta_text, image_url=image_url,
    )

    grid, total_filled, total_main, sponsors, revenue = _build_data(repo)
    return render("partials/sponsor_blocks_grid.html",
        grid=grid, positions=POSITIONS, edition_numbers=EDITION_NUMBERS,
        total_filled=total_filled, total_slots=27, total_main=total_main,
        sponsors=sponsors, revenue=revenue, statuses=BOOKING_STATUSES,
        message="Ad block updated", level="success")


# ---- Main Sponsor ----

@router.post("/main-sponsor/set", response_class=HTMLResponse)
async def set_main_sponsor(
    edition_slug: str = Form(...),
    edition_number: int = Form(...),
    sponsor_name: str = Form(""),
    logo_url: str = Form(""),
    tagline: str = Form(""),
    website_url: str = Form(""),
    notes: str = Form(""),
):
    repo = get_repo()
    repo.set_edition_sponsor(
        edition_slug=edition_slug, edition_number=edition_number,
        sponsor_name=sponsor_name, logo_url=logo_url, tagline=tagline,
        website_url=website_url, notes=notes,
    )

    grid, total_filled, total_main, sponsors, revenue = _build_data(repo)
    return render("partials/sponsor_blocks_grid.html",
        grid=grid, positions=POSITIONS, edition_numbers=EDITION_NUMBERS,
        total_filled=total_filled, total_slots=27, total_main=total_main,
        sponsors=sponsors, revenue=revenue, statuses=BOOKING_STATUSES,
        message=f"Main sponsor set: {sponsor_name} for {edition_slug} Ed.{edition_number}", level="success")


@router.post("/main-sponsor/remove", response_class=HTMLResponse)
async def remove_main_sponsor(
    edition_slug: str = Form(...),
    edition_number: int = Form(...),
):
    repo = get_repo()
    repo.remove_edition_sponsor(edition_slug, edition_number)

    grid, total_filled, total_main, sponsors, revenue = _build_data(repo)
    return render("partials/sponsor_blocks_grid.html",
        grid=grid, positions=POSITIONS, edition_numbers=EDITION_NUMBERS,
        total_filled=total_filled, total_slots=27, total_main=total_main,
        sponsors=sponsors, revenue=revenue, statuses=BOOKING_STATUSES,
        message=f"Main sponsor removed from {edition_slug} Ed.{edition_number}", level="success")


# ---- Sponsor Directory (CRM) ----

@router.post("/sponsors/add", response_class=HTMLResponse)
async def add_sponsor(
    name: str = Form(...),
    contact_name: str = Form(""),
    contact_email: str = Form(""),
    website: str = Form(""),
    notes: str = Form(""),
):
    repo = get_repo()
    try:
        repo.create_sponsor(name, contact_name, contact_email, website, notes)
        message = f"Added sponsor: {name}"
        level = "success"
    except Exception as exc:
        message = f"Failed: {exc}"
        level = "error"

    sponsors = repo.get_sponsors()
    revenue = repo.get_sponsor_revenue_summary()
    return render("partials/sponsors_table.html",
        sponsors=sponsors, revenue=revenue, statuses=BOOKING_STATUSES,
        message=message, level=level)


@router.get("/sponsors/{sponsor_id}", response_class=HTMLResponse)
async def sponsor_detail(sponsor_id: int):
    repo = get_repo()
    sponsor = repo.get_sponsor(sponsor_id)
    if not sponsor:
        return render("partials/alert.html", message="Sponsor not found.", level="error")

    bookings = repo.get_bookings_for_sponsor(sponsor_id)
    upcoming_issues = repo.get_upcoming_issues(limit=10)
    return render("sponsor_detail.html",
        sponsor=sponsor, bookings=bookings, upcoming_issues=upcoming_issues,
        statuses=BOOKING_STATUSES)


@router.post("/sponsors/{sponsor_id}/update", response_class=HTMLResponse)
async def update_sponsor(
    sponsor_id: int,
    name: str = Form(...),
    contact_name: str = Form(""),
    contact_email: str = Form(""),
    website: str = Form(""),
    notes: str = Form(""),
):
    repo = get_repo()
    repo.update_sponsor(sponsor_id, name=name, contact_name=contact_name,
                         contact_email=contact_email, website=website, notes=notes)

    sponsor = repo.get_sponsor(sponsor_id)
    bookings = repo.get_bookings_for_sponsor(sponsor_id)
    upcoming_issues = repo.get_upcoming_issues(limit=10)
    return render("sponsor_detail.html",
        sponsor=sponsor, bookings=bookings, upcoming_issues=upcoming_issues,
        statuses=BOOKING_STATUSES, message="Sponsor updated", level="success")


@router.post("/sponsors/book", response_class=HTMLResponse)
async def book_sponsor(
    sponsor_id: int = Form(...),
    issue_id: int = Form(...),
    position: str = Form("mid"),
    rate_cents: int = Form(0),
    notes: str = Form(""),
):
    repo = get_repo()
    repo.create_booking(sponsor_id, issue_id, position, rate_cents, notes)

    sponsor = repo.get_sponsor(sponsor_id)
    bookings = repo.get_bookings_for_sponsor(sponsor_id)
    upcoming_issues = repo.get_upcoming_issues(limit=10)
    return render("sponsor_detail.html",
        sponsor=sponsor, bookings=bookings, upcoming_issues=upcoming_issues,
        statuses=BOOKING_STATUSES, message="Booking created", level="success")


@router.post("/sponsors/booking/{booking_id}/status", response_class=HTMLResponse)
async def update_booking_status(booking_id: int, status: str = Form(...)):
    repo = get_repo()
    repo.update_booking_status(booking_id, status)
    return render("partials/alert.html", message=f"Status updated to {status}", level="success")


# ---- Sponsor Performance Analytics ----

@router.get("/analytics", response_class=HTMLResponse)
async def sponsor_analytics():
    repo = get_repo()
    performance = repo.get_sponsor_performance()
    return render("sponsor_analytics.html", performance=performance)
