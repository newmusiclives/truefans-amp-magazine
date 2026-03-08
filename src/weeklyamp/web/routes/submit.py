"""Public-facing submission routes (no sidebar) + API endpoint."""

from __future__ import annotations

import logging
import secrets
import threading
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

# ---- Rate limiting ----
_submit_attempts: dict[str, list[float]] = {}
_submit_lock = threading.Lock()


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _get_rate_config() -> tuple[int, int]:
    cfg = load_config()
    return cfg.rate_limits.submit_max, cfg.rate_limits.submit_window


def _is_submit_rate_limited(ip: str) -> bool:
    max_attempts, window = _get_rate_config()
    now = time.time()
    with _submit_lock:
        attempts = _submit_attempts.get(ip, [])
        attempts = [t for t in attempts if now - t < window]
        _submit_attempts[ip] = attempts
        return len(attempts) >= max_attempts


def _record_submission(ip: str) -> None:
    with _submit_lock:
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
        max_attempts, window = _get_rate_config()
        return JSONResponse(
            status_code=429,
            content={"error": "Too many submissions. Please try again later."},
            headers={
                "Retry-After": str(window),
                "X-RateLimit-Limit": str(max_attempts),
                "X-RateLimit-Remaining": "0",
            },
        )

    cfg = load_config()

    # Auth check — always require a valid API key
    if not cfg.submissions.api_key:
        return JSONResponse(
            status_code=403,
            content={"error": "API submissions are not configured"},
        )
    if not secrets.compare_digest(x_truefans_api_key or "", cfg.submissions.api_key):
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

        # Calculate remaining
        max_attempts, window = _get_rate_config()
        with _submit_lock:
            current = len([t for t in _submit_attempts.get(ip, []) if time.time() - t < window])
        remaining = max(0, max_attempts - current)

        return JSONResponse(
            status_code=201,
            content={"id": submission_id, "status": "submitted"},
            headers={
                "X-RateLimit-Limit": str(max_attempts),
                "X-RateLimit-Remaining": str(remaining),
            },
        )
    except Exception:
        logger.exception("API submission failed")
        return JSONResponse(status_code=400, content={"error": "Submission could not be processed"})
