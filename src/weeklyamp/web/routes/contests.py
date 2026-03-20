"""Contest routes — public contest pages and admin management."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from jinja2 import Environment, FileSystemLoader

from weeklyamp.content.contests import ContestManager
from weeklyamp.web.deps import get_config, get_repo, render

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent.parent / "templates" / "web"
_pub_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

router = APIRouter()


def _get_manager():
    cfg = get_config()
    repo = get_repo()
    return ContestManager(repo, cfg.contests), repo, cfg


# ---- Public routes ----


@router.get("/contests", response_class=HTMLResponse)
async def contests_public():
    """List active contests (public page)."""
    manager, repo, cfg = _get_manager()
    active = manager.get_active_contests()

    # Add entry counts
    for c in active:
        c["entry_count"] = manager.get_entry_count(c["id"])

    # Past winners
    conn = repo._conn()
    try:
        rows = conn.execute(
            "SELECT * FROM contests WHERE status = 'awarded' ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        past_winners = [dict(r) for r in rows]
    finally:
        conn.close()

    tpl = _pub_env.get_template("contests_public.html")
    return tpl.render(
        contests=active,
        past_winners=past_winners,
        enabled=cfg.contests.enabled,
    )


@router.get("/contests/{contest_id}", response_class=HTMLResponse)
async def contest_detail_public(contest_id: int):
    """Contest detail page (public)."""
    manager, repo, cfg = _get_manager()
    contest = manager.get_contest(contest_id)
    if not contest:
        return HTMLResponse("<h2>Contest not found</h2>", status_code=404)

    entry_count = manager.get_entry_count(contest_id)

    tpl = _pub_env.get_template("contest_detail_public.html")
    return tpl.render(
        contest=contest,
        entry_count=entry_count,
        enabled=cfg.contests.enabled,
    )


@router.post("/contests/{contest_id}/enter", response_class=HTMLResponse)
async def contest_enter(contest_id: int, request: Request):
    """Enter a contest (public, email required)."""
    manager, repo, cfg = _get_manager()
    form = await request.form()
    email = form.get("email", "").strip()[:254]

    contest = manager.get_contest(contest_id)
    if not contest:
        return HTMLResponse("<h2>Contest not found</h2>", status_code=404)

    if not email or not _EMAIL_RE.match(email):
        entry_count = manager.get_entry_count(contest_id)
        tpl = _pub_env.get_template("contest_detail_public.html")
        return HTMLResponse(tpl.render(
            contest=contest, entry_count=entry_count,
            enabled=cfg.contests.enabled,
            error="Please enter a valid email address.",
        ))

    # Find or create subscriber
    conn = repo._conn()
    try:
        sub = conn.execute(
            "SELECT id FROM subscribers WHERE email = ?", (email,)
        ).fetchone()
        if sub:
            subscriber_id = sub["id"]
        else:
            cur = conn.execute(
                "INSERT INTO subscribers (email, status) VALUES (?, 'active')",
                (email,),
            )
            conn.commit()
            subscriber_id = cur.lastrowid
    finally:
        conn.close()

    result = manager.enter_contest(contest_id, subscriber_id, email=email)

    entry_count = manager.get_entry_count(contest_id)
    tpl = _pub_env.get_template("contest_detail_public.html")

    if result.get("already_entered"):
        return HTMLResponse(tpl.render(
            contest=contest, entry_count=entry_count,
            enabled=cfg.contests.enabled,
            error="You have already entered this contest!",
        ))

    if result.get("success"):
        return HTMLResponse(tpl.render(
            contest=contest, entry_count=entry_count,
            enabled=cfg.contests.enabled,
            success="You're entered! Good luck!",
        ))

    return HTMLResponse(tpl.render(
        contest=contest, entry_count=entry_count,
        enabled=cfg.contests.enabled,
        error=result.get("message", "Could not enter contest."),
    ))


# ---- Admin routes ----


@router.get("/admin/contests", response_class=HTMLResponse)
async def admin_contests():
    """Admin contest management page."""
    manager, repo, cfg = _get_manager()
    contests = manager.get_all_contests()

    for c in contests:
        c["entry_count"] = manager.get_entry_count(c["id"])

    editions = repo.get_editions(active_only=True)

    return render("admin_contests.html",
        contests=contests,
        editions=editions,
        enabled=cfg.contests.enabled,
    )


@router.post("/admin/contests/create", response_class=HTMLResponse)
async def admin_contest_create(
    title: str = Form(...),
    description: str = Form(""),
    prize: str = Form(""),
    contest_type: str = Form("share"),
    entry_requirement: str = Form(""),
    edition_slug: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
):
    """Create a new contest."""
    manager, repo, cfg = _get_manager()

    try:
        contest_id = manager.create_contest(
            title=title,
            description=description,
            prize=prize,
            contest_type=contest_type,
            entry_requirement=entry_requirement,
            edition_slug=edition_slug,
            start_date=start_date,
            end_date=end_date,
        )
        message = f"Created contest #{contest_id}: {title}"
        level = "success"
    except Exception as exc:
        message = f"Failed: {exc}"
        level = "error"

    contests = manager.get_all_contests()
    for c in contests:
        c["entry_count"] = manager.get_entry_count(c["id"])
    editions = repo.get_editions(active_only=True)

    return render("admin_contests.html",
        contests=contests, editions=editions,
        enabled=cfg.contests.enabled,
        message=message, level=level,
    )


@router.post("/admin/contests/{contest_id}/close", response_class=HTMLResponse)
async def admin_contest_close(contest_id: int):
    """Close a contest."""
    manager, repo, cfg = _get_manager()
    manager.close_contest(contest_id)

    contests = manager.get_all_contests()
    for c in contests:
        c["entry_count"] = manager.get_entry_count(c["id"])
    editions = repo.get_editions(active_only=True)

    return render("admin_contests.html",
        contests=contests, editions=editions,
        enabled=cfg.contests.enabled,
        message=f"Contest #{contest_id} closed", level="success",
    )


@router.post("/admin/contests/{contest_id}/pick-winner", response_class=HTMLResponse)
async def admin_contest_pick_winner(contest_id: int):
    """Pick a random winner for a contest."""
    manager, repo, cfg = _get_manager()
    winner = manager.pick_winner(contest_id)

    if winner:
        message = f"Winner picked: {winner.get('winner_name', 'unknown')}"
        level = "success"
    else:
        message = "No entries — cannot pick a winner"
        level = "error"

    contests = manager.get_all_contests()
    for c in contests:
        c["entry_count"] = manager.get_entry_count(c["id"])
    editions = repo.get_editions(active_only=True)

    return render("admin_contests.html",
        contests=contests, editions=editions,
        enabled=cfg.contests.enabled,
        message=message, level=level,
    )
