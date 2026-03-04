"""Public subscribe routes — newsletter edition signup."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from jinja2 import Environment, FileSystemLoader

from weeklyamp.core.config import load_config
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent.parent / "templates" / "web"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)

router = APIRouter()

# ---- Rate limiting (5 signups per IP per 15 minutes) ----
_subscribe_attempts: dict[str, list[float]] = {}
_SUBSCRIBE_MAX = 5
_SUBSCRIBE_WINDOW = 900  # 15 minutes

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_subscribe_rate_limited(ip: str) -> bool:
    now = time.time()
    attempts = _subscribe_attempts.get(ip, [])
    attempts = [t for t in attempts if now - t < _SUBSCRIBE_WINDOW]
    _subscribe_attempts[ip] = attempts
    return len(attempts) >= _SUBSCRIBE_MAX


def _record_subscribe(ip: str) -> None:
    _subscribe_attempts.setdefault(ip, []).append(time.time())


def _get_repo() -> Repository:
    import os
    cfg = load_config()
    db_path = cfg.db_path
    if not os.path.isabs(db_path):
        if os.path.exists("/app"):
            db_path = os.path.join("/app", db_path)
        else:
            db_path = os.path.abspath(db_path)
    return Repository(db_path)


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
        repo.subscribe_to_editions(
            email=email,
            edition_slugs=selected_slugs,
            first_name=first_name,
            source_channel="website",
            edition_days=edition_days,
        )
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
