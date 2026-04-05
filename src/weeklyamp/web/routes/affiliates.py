"""Affiliate program management routes."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def affiliates_page(request: Request):
    repo = get_repo()
    programs = repo.get_affiliate_programs()
    categories = {}
    for p in programs:
        cat = p.get("category", "general")
        categories.setdefault(cat, []).append(p)
    return HTMLResponse(render("affiliates.html", categories=categories, programs=programs))


@router.get("/redirect/{slug}")
async def affiliate_redirect(slug: str):
    from fastapi.responses import RedirectResponse
    repo = get_repo()
    program = repo.get_affiliate_by_slug(slug)
    if not program:
        return RedirectResponse("/affiliates/", status_code=302)
    repo.record_affiliate_click(program["id"])
    return RedirectResponse(program["affiliate_url"], status_code=302)


@router.get("/marketplace", response_class=HTMLResponse)
async def affiliate_marketplace(request: Request):
    """Public affiliate marketplace — browse and apply to programs."""
    repo = get_repo()
    programs = repo.get_affiliate_programs()
    public_programs = [p for p in programs if p.get("is_active")]
    categories = {}
    for p in public_programs:
        cat = p.get("category", "general")
        categories.setdefault(cat, []).append(p)
    return HTMLResponse(render("affiliate_marketplace.html", categories=categories))


@router.post("/apply", response_class=HTMLResponse)
async def affiliate_apply(request: Request, program_id: int = Form(...), name: str = Form(...), email: str = Form(...), website: str = Form(""), message: str = Form("")):
    """Apply to join an affiliate program."""
    repo = get_repo()
    conn = repo._conn()
    conn.execute(
        """INSERT INTO affiliate_applications (program_id, name, email, website, message, status)
           VALUES (?, ?, ?, ?, ?, 'pending')""",
        (program_id, name, email, website, message),
    )
    conn.commit()
    conn.close()
    return HTMLResponse('<div class="alert alert-success">Application submitted! We\'ll review it within 48 hours.</div>')


@router.get("/dashboard", response_class=HTMLResponse)
async def affiliate_dashboard(request: Request):
    """Affiliate partner dashboard — track clicks and revenue."""
    repo = get_repo()
    session = getattr(request.state, "session", None) or {}
    affiliate_email = session.get("affiliate_email", "")
    if not affiliate_email:
        return HTMLResponse(render("affiliate_login.html"))
    conn = repo._conn()
    placements = conn.execute(
        """SELECT ap.*, aprog.name as program_name
           FROM affiliate_placements ap
           JOIN affiliate_programs aprog ON aprog.id = ap.program_id
           WHERE ap.affiliate_email = ?
           ORDER BY ap.created_at DESC""",
        (affiliate_email,),
    ).fetchall()
    conn.close()
    return HTMLResponse(render("affiliate_dashboard.html", placements=[dict(p) for p in placements]))
