"""Trivia admin and public voting routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Form, Query
from fastapi.responses import HTMLResponse

from weeklyamp.content.trivia_polls import TriviaManager
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


def _get_manager():
    cfg = get_config()
    repo = get_repo()
    return TriviaManager(repo, cfg.trivia_polls), repo, cfg


# ---- Admin routes ----


@router.get("/trivia", response_class=HTMLResponse)
async def trivia_list_page():
    """List all trivia/polls."""
    manager, repo, cfg = _get_manager()
    polls = repo.get_trivia_polls(limit=100)

    # Parse options JSON for display
    for p in polls:
        p["options"] = json.loads(p.get("options_json", "[]"))
        results = manager.get_results(p["id"])
        p["total_votes"] = results.get("total_votes", 0)

    issues = []
    try:
        conn = repo._conn()
        rows = conn.execute(
            "SELECT id, issue_number, title, edition_slug FROM issues ORDER BY issue_number DESC LIMIT 20"
        ).fetchall()
        conn.close()
        issues = [dict(r) for r in rows]
    except Exception:
        pass

    return render("trivia_list.html",
        polls=polls,
        issues=issues,
        enabled=cfg.trivia_polls.enabled,
    )


@router.post("/trivia/create", response_class=HTMLResponse)
async def trivia_create(
    question_type: str = Form("trivia"),
    question_text: str = Form(...),
    options: str = Form(...),
    correct_index: int = Form(-1),
    target_issue_id: int = Form(...),
    explanation: str = Form(""),
):
    """Create a new trivia question or poll."""
    manager, repo, cfg = _get_manager()
    option_list = [o.strip() for o in options.split(",") if o.strip()]

    try:
        if question_type == "trivia":
            poll_id = manager.create_trivia(
                question_text=question_text,
                options=option_list,
                correct_index=correct_index,
                target_issue_id=target_issue_id,
                explanation=explanation,
            )
        else:
            poll_id = manager.create_poll(
                question_text=question_text,
                options=option_list,
                target_issue_id=target_issue_id,
            )
        message = f"Created {question_type} #{poll_id}"
        level = "success"
    except Exception as exc:
        message = f"Failed: {exc}"
        level = "error"

    # Re-fetch list
    polls = repo.get_trivia_polls(limit=100)
    for p in polls:
        p["options"] = json.loads(p.get("options_json", "[]"))
        results = manager.get_results(p["id"])
        p["total_votes"] = results.get("total_votes", 0)

    issues = []
    try:
        conn = repo._conn()
        rows = conn.execute(
            "SELECT id, issue_number, title, edition_slug FROM issues ORDER BY issue_number DESC LIMIT 20"
        ).fetchall()
        conn.close()
        issues = [dict(r) for r in rows]
    except Exception:
        pass

    return render("trivia_list.html",
        polls=polls,
        issues=issues,
        enabled=cfg.trivia_polls.enabled,
        message=message,
        level=level,
    )


# ---- Public routes (no auth required) ----
# NOTE: /trivia/leaderboard must be defined BEFORE /trivia/{poll_id}
# to avoid FastAPI matching "leaderboard" as a poll_id parameter.


@router.get("/trivia/leaderboard", response_class=HTMLResponse)
async def public_leaderboard():
    """Public trivia leaderboard."""
    manager, repo, cfg = _get_manager()
    leaderboard = manager.get_leaderboard(limit=cfg.trivia_polls.leaderboard_size)

    return render("trivia_leaderboard.html",
        leaderboard=leaderboard,
    )


@router.get("/t/vote/{poll_id}/{option_index}/{subscriber_id}", response_class=HTMLResponse)
async def public_vote(poll_id: int, option_index: int, subscriber_id: int):
    """Record a vote and show the results page."""
    manager, repo, cfg = _get_manager()

    poll = repo.get_trivia_poll(poll_id)
    if not poll:
        return HTMLResponse("<h2>Poll not found</h2>", status_code=404)

    poll["options"] = json.loads(poll.get("options_json", "[]"))

    vote_result = manager.record_vote(poll_id, subscriber_id, option_index)

    return render("trivia_vote_confirm.html",
        poll=poll,
        vote_result=vote_result,
        option_index=option_index,
        subscriber_id=subscriber_id,
    )


# ---- Admin detail routes (must come after /trivia/leaderboard) ----


@router.get("/trivia/{poll_id}", response_class=HTMLResponse)
async def trivia_detail_page(poll_id: int):
    """Trivia/poll detail with results."""
    manager, repo, cfg = _get_manager()
    poll = repo.get_trivia_poll(poll_id)
    if not poll:
        return HTMLResponse("<h2>Poll not found</h2>", status_code=404)

    poll["options"] = json.loads(poll.get("options_json", "[]"))
    results = manager.get_results(poll_id)

    return render("trivia_detail.html",
        poll=poll,
        results=results,
        enabled=cfg.trivia_polls.enabled,
    )


@router.post("/trivia/{poll_id}/close", response_class=HTMLResponse)
async def trivia_close(poll_id: int):
    """Close a poll."""
    manager, repo, cfg = _get_manager()
    manager.close_poll(poll_id)

    poll = repo.get_trivia_poll(poll_id)
    poll["options"] = json.loads(poll.get("options_json", "[]"))
    results = manager.get_results(poll_id)

    return render("trivia_detail.html",
        poll=poll,
        results=results,
        enabled=cfg.trivia_polls.enabled,
        message="Poll closed",
        level="success",
    )
