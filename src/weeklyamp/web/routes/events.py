"""Event management — virtual and in-person music events with ticketing."""
from __future__ import annotations
import secrets
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def events_page(request: Request):
    repo = get_repo()
    conn = repo._conn()
    events = conn.execute("SELECT * FROM events ORDER BY event_date DESC LIMIT 20").fetchall()
    conn.close()
    return HTMLResponse(render("events.html", events=[dict(e) for e in events]))

@router.post("/create", response_class=HTMLResponse)
async def create_event(request: Request, title: str = Form(...), description: str = Form(""), event_type: str = Form("virtual"), edition_slug: str = Form(""), location: str = Form(""), event_date: str = Form(""), ticket_price_cents: int = Form(0), max_attendees: int = Form(0)):
    repo = get_repo()
    conn = repo._conn()
    conn.execute(
        "INSERT INTO events (title, description, event_type, edition_slug, location, event_date, ticket_price_cents, max_attendees, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft')",
        (title, description, event_type, edition_slug, location, event_date, ticket_price_cents, max_attendees),
    )
    conn.commit()
    conn.close()
    return HTMLResponse(f'<div class="alert alert-success">Event "{title}" created.</div>')

@router.get("/public", response_class=HTMLResponse)
async def public_events(request: Request):
    repo = get_repo()
    conn = repo._conn()
    events = conn.execute("SELECT * FROM events WHERE status = 'published' ORDER BY event_date ASC").fetchall()
    conn.close()
    return HTMLResponse(render("events_public.html", events=[dict(e) for e in events]))

@router.post("/register/{event_id}", response_class=HTMLResponse)
async def register_event(event_id: int, request: Request, email: str = Form(...), name: str = Form("")):
    repo = get_repo()
    config = get_config()
    conn = repo._conn()
    event = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if not event:
        conn.close()
        return HTMLResponse('<div class="alert alert-danger">Event not found.</div>', status_code=404)
    event = dict(event)

    # Check if paid event — redirect to Manifest checkout
    ticket_price = event.get("ticket_price_cents", 0)
    if ticket_price > 0 and config.paid_tiers.enabled:
        conn.close()
        from weeklyamp.billing.stripe_client import PaymentClient
        client = PaymentClient(config.paid_tiers)
        ticket_code = secrets.token_urlsafe(8).upper()
        checkout_url = client.create_checkout_session(
            price_id=f"event_{event_id}",
            customer_email=email,
            success_url=f"{config.site_domain}/events/ticket/{ticket_code}",
            cancel_url=f"{config.site_domain}/events/public",
            metadata={"event_id": str(event_id), "email": email, "name": name, "ticket_code": ticket_code},
        )
        if checkout_url:
            # Pre-create registration as pending
            conn = repo._conn()
            conn.execute(
                "INSERT INTO event_registrations (event_id, email, name, payment_status, ticket_code) VALUES (?, ?, ?, 'pending', ?)",
                (event_id, email, name, ticket_code),
            )
            conn.commit()
            conn.close()
            return RedirectResponse(checkout_url, status_code=303)

    # Free event — register directly
    ticket_code = secrets.token_urlsafe(8).upper()
    try:
        conn.execute(
            "INSERT INTO event_registrations (event_id, email, name, payment_status, ticket_code) VALUES (?, ?, ?, 'free', ?)",
            (event_id, email, name, ticket_code),
        )
        conn.execute("UPDATE events SET registered_count = registered_count + 1 WHERE id = ?", (event_id,))
        conn.commit()
    except Exception:
        conn.close()
        return HTMLResponse('<div class="alert alert-warning">Already registered.</div>')
    conn.close()
    return HTMLResponse(f'<div class="alert alert-success">You\'re registered! Your ticket code: <strong>{ticket_code}</strong></div>')

@router.get("/ticket/{ticket_code}", response_class=HTMLResponse)
async def view_ticket(ticket_code: str, request: Request):
    """View ticket details after registration/payment."""
    repo = get_repo()
    conn = repo._conn()
    reg = conn.execute(
        """SELECT er.*, e.title, e.event_date, e.location, e.event_type
           FROM event_registrations er
           JOIN events e ON e.id = er.event_id
           WHERE er.ticket_code = ?""",
        (ticket_code,),
    ).fetchone()
    conn.close()
    if not reg:
        return HTMLResponse("Ticket not found", status_code=404)
    return HTMLResponse(render("event_ticket.html", ticket=dict(reg)))

@router.post("/checkin/{ticket_code}")
async def checkin(ticket_code: str, request: Request):
    """Check in an attendee at the event."""
    repo = get_repo()
    conn = repo._conn()
    reg = conn.execute("SELECT * FROM event_registrations WHERE ticket_code = ?", (ticket_code,)).fetchone()
    if not reg:
        conn.close()
        return JSONResponse({"error": "Ticket not found"}, status_code=404)
    if reg["checked_in_at"]:
        conn.close()
        return JSONResponse({"error": "Already checked in"}, status_code=400)
    conn.execute(
        "UPDATE event_registrations SET checked_in_at = CURRENT_TIMESTAMP WHERE ticket_code = ?",
        (ticket_code,),
    )
    conn.commit()
    conn.close()
    return JSONResponse({"status": "checked_in", "name": reg["name"], "email": reg["email"]})
