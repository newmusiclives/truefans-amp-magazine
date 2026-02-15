"""Sponsor CRM routes."""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()

BOOKING_STATUSES = ["inquiry", "booked", "confirmed", "delivered", "invoiced", "paid"]


@router.get("/", response_class=HTMLResponse)
async def sponsors_page():
    repo = get_repo()
    sponsors = repo.get_sponsors()
    revenue = repo.get_sponsor_revenue_summary()
    return render("sponsors.html",
        sponsors=sponsors,
        revenue=revenue,
        statuses=BOOKING_STATUSES,
    )


@router.post("/add", response_class=HTMLResponse)
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
        sponsors=sponsors, revenue=revenue, message=message, level=level)


@router.get("/{sponsor_id}", response_class=HTMLResponse)
async def sponsor_detail(sponsor_id: int):
    repo = get_repo()
    sponsor = repo.get_sponsor(sponsor_id)
    if not sponsor:
        return render("partials/alert.html", message="Sponsor not found.", level="error")

    bookings = repo.get_bookings_for_sponsor(sponsor_id)
    upcoming_issues = repo.get_upcoming_issues(limit=10)
    return render("sponsor_detail.html",
        sponsor=sponsor,
        bookings=bookings,
        upcoming_issues=upcoming_issues,
        statuses=BOOKING_STATUSES,
    )


@router.post("/{sponsor_id}/update", response_class=HTMLResponse)
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
        sponsor=sponsor, bookings=bookings,
        upcoming_issues=upcoming_issues, statuses=BOOKING_STATUSES,
        message="Sponsor updated", level="success")


@router.post("/book", response_class=HTMLResponse)
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
        sponsor=sponsor, bookings=bookings,
        upcoming_issues=upcoming_issues, statuses=BOOKING_STATUSES,
        message="Booking created", level="success")


@router.post("/booking/{booking_id}/status", response_class=HTMLResponse)
async def update_booking_status(booking_id: int, status: str = Form(...)):
    repo = get_repo()
    repo.update_booking_status(booking_id, status)
    return render("partials/alert.html", message=f"Status updated to {status}", level="success")


@router.get("/calendar", response_class=HTMLResponse)
async def sponsor_calendar():
    repo = get_repo()
    cfg = get_config()
    open_slots = repo.get_open_slots(limit=12)
    sponsors = repo.get_sponsors()

    # Build calendar data: for each issue, get bookings
    calendar_data = []
    for issue in open_slots:
        bookings = repo.get_bookings_for_issue(issue["id"])
        calendar_data.append({
            "issue": issue,
            "bookings": bookings,
            "max_slots": cfg.sponsor_slots.max_per_issue,
            "open": cfg.sponsor_slots.max_per_issue - len(bookings),
        })

    return render("sponsor_calendar.html",
        calendar=calendar_data,
        sponsors=sponsors,
        positions=cfg.sponsor_slots.available_positions,
    )
