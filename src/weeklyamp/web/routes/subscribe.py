"""Public subscribe routes — newsletter edition signup."""

from __future__ import annotations

import logging
import re
import secrets
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from jinja2 import Environment, FileSystemLoader

from weeklyamp.core.config import load_config
from weeklyamp.web.deps import get_repo as _get_repo

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent.parent / "templates" / "web"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)

router = APIRouter()

# ---- Rate limiting ----
_subscribe_attempts: dict[str, list[float]] = {}
_subscribe_lock = threading.Lock()

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _get_rate_config() -> tuple[int, int]:
    cfg = load_config()
    return cfg.rate_limits.subscribe_max, cfg.rate_limits.subscribe_window


def _is_subscribe_rate_limited(ip: str) -> bool:
    max_attempts, window = _get_rate_config()
    now = time.time()
    with _subscribe_lock:
        attempts = _subscribe_attempts.get(ip, [])
        attempts = [t for t in attempts if now - t < window]
        _subscribe_attempts[ip] = attempts
        return len(attempts) >= max_attempts


def _record_subscribe(ip: str) -> None:
    with _subscribe_lock:
        _subscribe_attempts.setdefault(ip, []).append(time.time())


@router.get("/subscribe", response_class=HTMLResponse)
async def subscribe_form():
    repo = _get_repo()
    editions = repo.get_editions(active_only=True)
    tpl = _env.get_template("subscribe.html")
    return tpl.render(editions=editions)


@router.post("/subscribe", response_class=HTMLResponse)
async def subscribe_process(request: Request):
    repo = _get_repo()
    editions = repo.get_editions(active_only=True)
    form = await request.form()

    email = form.get("email", "").strip()[:254]
    first_name = form.get("first_name", "").strip()[:100]
    selected_slugs = form.getlist("editions")

    ip = _get_client_ip(request)

    # Rate limit
    if _is_subscribe_rate_limited(ip):
        tpl = _env.get_template("subscribe.html")
        return HTMLResponse(
            tpl.render(editions=editions, error="Too many signups. Please try again later."),
            status_code=429,
        )

    # Validate email
    if not email or not _EMAIL_RE.match(email):
        tpl = _env.get_template("subscribe.html")
        return HTMLResponse(
            tpl.render(editions=editions, error="Please enter a valid email address.",
                       email=email, first_name=first_name, selected=selected_slugs),
        )

    # Validate editions
    valid_slugs = {e["slug"] for e in editions}
    selected_slugs = [s for s in selected_slugs if s in valid_slugs]
    if not selected_slugs:
        tpl = _env.get_template("subscribe.html")
        return HTMLResponse(
            tpl.render(editions=editions, error="Please select at least one newsletter edition.",
                       email=email, first_name=first_name),
        )

    # Parse per-edition day preferences
    allowed_days = {"monday", "wednesday", "saturday"}
    edition_days: dict[str, list[str]] = {}
    for slug in selected_slugs:
        raw = form.getlist(f"days_{slug}")
        days = [d for d in raw if d in allowed_days]
        if not days:
            days = sorted(allowed_days)  # default: all 3 days
        edition_days[slug] = days

    try:
        sub_id = repo.subscribe_to_editions(
            email=email,
            edition_slugs=selected_slugs,
            first_name=first_name,
            source_channel="website",
            edition_days=edition_days,
        )
        verification_token = secrets.token_urlsafe(32)
        unsubscribe_token = secrets.token_urlsafe(32)
        repo.set_subscriber_tokens(sub_id, verification_token, unsubscribe_token)
        _record_subscribe(ip)

        # PRG: redirect to confirmation page with edition info + days in query
        parts = []
        for slug in selected_slugs:
            days_str = "+".join(edition_days[slug])
            parts.append(f"{slug}:{days_str}")
        editions_param = ",".join(parts)
        return RedirectResponse(
            f"/subscribe/confirm?editions={editions_param}",
            status_code=303,
        )
    except Exception:
        logger.exception("Subscribe failed")
        tpl = _env.get_template("subscribe.html")
        return HTMLResponse(
            tpl.render(editions=editions, error="Something went wrong. Please try again later.",
                       email=email, first_name=first_name, selected=selected_slugs),
        )


@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe(request: Request):
    token = request.query_params.get("token", "")
    tpl = _env.get_template("unsubscribe.html")
    if not token:
        return HTMLResponse(tpl.render(error="Invalid unsubscribe link."), status_code=400)
    repo = _get_repo()
    success = repo.unsubscribe_by_token(token)
    if success:
        return tpl.render(success=True)
    return HTMLResponse(tpl.render(error="This link has already been used or is invalid."), status_code=400)


@router.get("/verify", response_class=HTMLResponse)
async def verify_email(request: Request):
    token = request.query_params.get("token", "")
    tpl = _env.get_template("verify_email.html")
    if not token:
        return HTMLResponse(tpl.render(error="Invalid verification link."), status_code=400)
    repo = _get_repo()
    success = repo.verify_subscriber(token)
    if success:
        return tpl.render(success=True)
    return HTMLResponse(tpl.render(error="This link has already been used or is invalid."), status_code=400)


@router.get("/subscribe/confirm", response_class=HTMLResponse)
async def subscribe_confirm(request: Request):
    repo = _get_repo()
    raw = request.query_params.get("editions", "")
    editions = repo.get_editions(active_only=True)
    editions_by_slug = {e["slug"]: e for e in editions}

    # Parse "fan:monday+saturday,artist:wednesday" format (backwards-compat with plain slugs)
    selected = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            slug, days_str = part.split(":", 1)
            days = [d for d in days_str.split("+") if d]
        else:
            slug = part
            days = ["monday", "wednesday", "saturday"]
        if slug in editions_by_slug:
            ed = dict(editions_by_slug[slug])
            ed["selected_days"] = days
            selected.append(ed)

    tpl = _env.get_template("subscribe_confirm.html")
    return tpl.render(selected_editions=selected)
