"""Public-facing submission routes (no sidebar) + API endpoint."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Form, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse

from jinja2 import Environment, FileSystemLoader

from weeklyamp.core.config import load_config
from weeklyamp.db.repository import Repository
from weeklyamp.submissions.intake import process_api_submission, process_web_submission

_TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent.parent / "templates" / "web"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)

router = APIRouter()


@router.get("/submit", response_class=HTMLResponse)
async def submit_form():
    tpl = _env.get_template("submit_public.html")
    return tpl.render()


@router.post("/submit", response_class=HTMLResponse)
async def submit_process(
    artist_name: str = Form(...),
    artist_email: str = Form(""),
    artist_website: str = Form(""),
    artist_social: str = Form(""),
    submission_type: str = Form("new_release"),
    title: str = Form(""),
    description: str = Form(""),
    release_date: str = Form(""),
    genre: str = Form(""),
    links: str = Form(""),
):
    cfg = load_config()
    repo = Repository(cfg.db_path)

    form_data = {
        "artist_name": artist_name,
        "artist_email": artist_email,
        "artist_website": artist_website,
        "artist_social": artist_social,
        "submission_type": submission_type,
        "title": title,
        "description": description,
        "release_date": release_date,
        "genre": genre,
        "links": links,
    }

    try:
        process_web_submission(repo, form_data)
        tpl = _env.get_template("submit_public.html")
        return tpl.render(
            success=True,
            message="Thank you! Your submission has been received and will be reviewed by our team.",
        )
    except Exception as e:
        tpl = _env.get_template("submit_public.html")
        return tpl.render(error=True, message=f"Something went wrong: {e}")


@router.post("/api/v1/submissions")
async def api_submit(request: Request, x_truefans_api_key: str = Header(None)):
    """JSON API endpoint for TrueFans CONNECT integration."""
    cfg = load_config()

    # Auth check
    if cfg.submissions.api_key:
        if x_truefans_api_key != cfg.submissions.api_key:
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid or missing API key"},
            )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    repo = Repository(cfg.db_path)
    try:
        submission_id = process_api_submission(repo, body)
        return JSONResponse(
            status_code=201,
            content={"id": submission_id, "status": "submitted"},
        )
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
