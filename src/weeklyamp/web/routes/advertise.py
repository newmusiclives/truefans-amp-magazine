"""Public advertise page + sponsor inquiry management routes."""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from weeklyamp.content.sponsor_rates import RateCardEngine
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()

INQUIRY_STATUSES = ["new", "contacted", "qualified", "proposal", "closed_won", "closed_lost"]
BUDGET_RANGES = [
    "Under $500",
    "$500 - $1,000",
    "$1,000 - $2,500",
    "$2,500 - $5,000",
    "$5,000+",
]


# ---- PUBLIC (no auth) ----

@router.get("/advertise", response_class=HTMLResponse)
async def advertise_page():
    """Public 'Advertise with TrueFans' landing page."""
    config = get_config()
    repo = get_repo()

    engine = RateCardEngine(repo, config.sponsor_portal)
    media_kit = engine.get_media_kit_data()

    return render("advertise.html",
        media_kit=media_kit,
        budget_ranges=BUDGET_RANGES,
    )


@router.post("/advertise/inquiry", response_class=HTMLResponse)
async def submit_inquiry(
    company: str = Form(...),
    contact_name: str = Form(...),
    email: str = Form(...),
    website: str = Form(""),
    budget_range: str = Form(""),
    editions: list[str] = Form(default=[]),
    message: str = Form(""),
):
    """Submit a sponsor inquiry from the public page."""
    repo = get_repo()
    repo.create_sponsor_inquiry(
        company_name=company,
        contact_name=contact_name,
        contact_email=email,
        website=website,
        budget_range=budget_range,
        message=message,
        editions_interested=",".join(editions),
    )

    config = get_config()
    engine = RateCardEngine(repo, config.sponsor_portal)
    media_kit = engine.get_media_kit_data()

    return render("advertise.html",
        media_kit=media_kit,
        budget_ranges=BUDGET_RANGES,
        thank_you=True,
    )


# ---- ADMIN ----

@router.get("/advertise/inquiries", response_class=HTMLResponse)
async def inquiries_page():
    """Admin: view all sponsor inquiries."""
    repo = get_repo()
    inquiries = repo.get_sponsor_inquiries()

    return render("sponsor_inquiries.html",
        inquiries=inquiries,
        statuses=INQUIRY_STATUSES,
    )


@router.post("/advertise/inquiries/{inquiry_id}/status", response_class=HTMLResponse)
async def update_inquiry_status(
    inquiry_id: int,
    status: str = Form(...),
    notes: str = Form(""),
):
    """Admin: update inquiry status."""
    repo = get_repo()
    repo.update_sponsor_inquiry(inquiry_id, status=status, notes=notes)
    inquiries = repo.get_sponsor_inquiries()

    return render("sponsor_inquiries.html",
        inquiries=inquiries,
        statuses=INQUIRY_STATUSES,
        message=f"Inquiry #{inquiry_id} updated to {status}",
        level="success",
    )
