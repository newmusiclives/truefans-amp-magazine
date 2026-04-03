"""Welcome sequence admin routes."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def welcome_page(request: Request):
    repo = get_repo()
    config = get_config()
    from weeklyamp.content.welcome_sequence import WelcomeManager

    mgr = WelcomeManager(repo, config.welcome_sequence)
    steps = mgr.get_steps()
    editions = repo.get_editions()
    return HTMLResponse(
        render(
            "welcome_sequence.html",
            steps=steps,
            editions=editions,
            config=config,
        )
    )


@router.post("/create", response_class=HTMLResponse)
async def create_step(
    request: Request,
    edition_slug: str = Form(""),
    step_number: int = Form(...),
    delay_hours: int = Form(...),
    subject: str = Form(...),
    html_content: str = Form(""),
):
    repo = get_repo()
    config = get_config()
    from weeklyamp.content.welcome_sequence import WelcomeManager

    mgr = WelcomeManager(repo, config.welcome_sequence)
    mgr.create_step(
        edition_slug=edition_slug,
        step_number=step_number,
        delay_hours=delay_hours,
        subject=subject,
        html_content=html_content,
    )
    return HTMLResponse(
        '<div class="alert alert-success">Welcome step created.</div>'
    )


@router.post("/{step_id}/delete", response_class=HTMLResponse)
async def delete_step(step_id: int, request: Request):
    repo = get_repo()
    conn = repo._conn()
    conn.execute(
        "UPDATE welcome_sequence_steps SET is_active = 0 WHERE id = ?", (step_id,)
    )
    conn.commit()
    conn.close()
    return HTMLResponse(
        '<div class="alert alert-success">Step removed.</div>'
    )
