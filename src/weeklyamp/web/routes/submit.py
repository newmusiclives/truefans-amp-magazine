"""Public-facing submission routes (no sidebar) + API endpoint."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import APIRouter, Form, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

from weeklyamp.core.config import load_config
from weeklyamp.db.repository import Repository
from weeklyamp.submissions.intake import process_api_submission, process_web_submission

_TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent.parent / "templates" / "web"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)

router = APIRouter()

# ---- Rate limiting (10 submissions per IP per 15 minutes) ----
_submit_attempts: dict[str, list[float]] = {}
_SUBMIT_MAX = 10
_SUBMIT_WINDOW = 900  # 15 minutes


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_submit_rate_limited(ip: str) -> bool:
    now = time.time()
    attempts = _submit_attempts.get(ip, [])
    attempts = [t for t in attempts if now - t < _SUBMIT_WINDOW]
    _submit_attempts[ip] = attempts
    return len(attempts) >= _SUBMIT_MAX


def _record_submission(ip: str) -> None:
    _submit_attempts.setdefault(ip, []).append(time.time())


@router.get("/submit", response_class=HTMLResponse)
async def submit_form():
    tpl = _env.get_template("submit_public.html")
    return tpl.render()


@router.post("/submit", response_class=HTMLResponse)
async def submit_process(
    request: Request,
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
    ip = _get_client_ip(request)
    if _is_submit_rate_limited(ip):
        tpl = _env.get_template("submit_public.html")
        return HTMLResponse(
            tpl.render(error=True, message="Too many submissions. Please try again later."),
            status_code=429,
        )

    cfg = load_config()
    repo = Repository(cfg.db_path)

    form_data = {
        "artist_name": artist_name[:200],
        "artist_email": artist_email[:254],
        "artist_website": artist_website[:500],
        "artist_social": artist_social[:500],
        "submission_type": submission_type[:500],
        "title": title[:500],
        "description": description[:10_000],
        "release_date": release_date[:500],
        "genre": genre[:500],
        "links": links[:500],
    }

    try:
        process_web_submission(repo, form_data)
        _record_submission(ip)
        tpl = _env.get_template("submit_public.html")
        return tpl.render(
            success=True,
            message="Thank you! Your submission has been received and will be reviewed by our team.",
        )
    except Exception:
        logger.exception("Web submission failed")
        tpl = _env.get_template("submit_public.html")
        return tpl.render(error=True, message="Something went wrong. Please try again later.")


@router.post("/api/v1/submissions")
async def api_submit(request: Request, x_truefans_api_key: str = Header(None)):
    """JSON API endpoint for TrueFans CONNECT integration."""
    ip = _get_client_ip(request)
    if _is_submit_rate_limited(ip):
        return JSONResponse(
            status_code=429,
            content={"error": "Too many submissions. Please try again later."},
        )

    cfg = load_config()

    # Auth check — always require a valid API key
    if not cfg.submissions.api_key:
        return JSONResponse(
            status_code=403,
            content={"error": "API submissions are not configured"},
        )
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
        _record_submission(ip)
        return JSONResponse(
            status_code=201,
            content={"id": submission_id, "status": "submitted"},
        )
    except Exception:
        logger.exception("API submission failed")
        return JSONResponse(status_code=400, content={"error": "Submission could not be processed"})
