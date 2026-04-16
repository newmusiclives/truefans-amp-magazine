"""Public subscribe routes — newsletter edition signup."""

from __future__ import annotations

import logging
import re
import secrets
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from jinja2 import Environment, FileSystemLoader

from weeklyamp.core.config import load_config
from weeklyamp.content.referrals import ReferralManager
from weeklyamp.web.deps import get_repo as _get_repo, render

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

    # Parse per-edition frequency (3×/2×/1× per week) and map to delivery days.
    # 3× → Mon/Wed/Sat, 2× → Mon/Sat, 1× → Sat. Backwards-compat: also accept
    # the legacy days_{slug} multi-checkbox if a client posts it.
    allowed_days = {"monday", "wednesday", "saturday"}
    freq_to_days = {
        3: ["monday", "wednesday", "saturday"],
        2: ["monday", "saturday"],
        1: ["saturday"],
    }
    edition_days: dict[str, list[str]] = {}
    for slug in selected_slugs:
        legacy = [d for d in form.getlist(f"days_{slug}") if d in allowed_days]
        if legacy:
            edition_days[slug] = legacy
            continue
        try:
            freq = int(form.get(f"frequency_{slug}", "3"))
        except (TypeError, ValueError):
            freq = 3
        edition_days[slug] = freq_to_days.get(freq, freq_to_days[3])

    # Check for referral code from query params or form
    ref_code = form.get("ref", "") or ""
    if not ref_code:
        ref_code = request.query_params.get("ref", "") or ""
    ref_code = ref_code.strip()

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

        # Generate referral code + record referral source (if enabled)
        cfg = load_config()
        referral_code = None
        if cfg.referrals.enabled:
            mgr = ReferralManager(repo, cfg.referrals)
            referral_code = mgr.get_or_create_code(sub_id)

            # Track who referred this subscriber
            if ref_code:
                mgr.record_referral(ref_code, email)

        # PRG: redirect to confirmation page with edition info + days in query
        parts = []
        for slug in selected_slugs:
            days_str = "+".join(edition_days[slug])
            parts.append(f"{slug}:{days_str}")
        editions_param = ",".join(parts)
        confirm_url = f"/subscribe/confirm?editions={editions_param}"
        if referral_code:
            confirm_url += f"&rcode={referral_code}"
        return RedirectResponse(
            confirm_url,
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


@router.post("/unsubscribe/survey", response_class=HTMLResponse)
async def unsubscribe_survey(request: Request):
    form = await request.form()
    email = form.get("email", "").strip()
    reason = form.get("reason", "").strip()
    feedback = form.get("feedback", "").strip()
    if reason:
        repo = _get_repo()
        repo.save_unsubscribe_survey(email=email, reason=reason, feedback=feedback)
    tpl = _env.get_template("unsubscribe.html")
    return HTMLResponse(tpl.render(success=True, survey_submitted=True))


@router.get("/resubscribe", response_class=HTMLResponse)
async def resubscribe(request: Request):
    """One-click resubscribe link for users who unsubscribed by accident.

    Reuses the unsubscribe_token (kept on the row even after status flips
    to 'unsubscribed') so the link in old footers continues to work.
    """
    token = request.query_params.get("token", "").strip()
    tpl = _env.get_template("resubscribe.html") if (
        Path(__file__).parent.parent.parent.parent.parent / "templates" / "web" / "resubscribe.html"
    ).exists() else _env.get_template("unsubscribe.html")
    if not token:
        return HTMLResponse("Invalid link", status_code=400)
    repo = _get_repo()
    conn = repo._conn()
    row = conn.execute(
        "SELECT id, status FROM subscribers WHERE unsubscribe_token = ?",
        (token,),
    ).fetchone()
    if not row:
        conn.close()
        return HTMLResponse("This link is no longer valid.", status_code=400)
    sub_id = row["id"] if isinstance(row, dict) else row[0]
    conn.execute(
        "UPDATE subscribers SET status = 'active', synced_at = CURRENT_TIMESTAMP WHERE id = ?",
        (sub_id,),
    )
    conn.commit()
    conn.close()
    try:
        return HTMLResponse(tpl.render(resubscribed=True))
    except Exception:
        return HTMLResponse(
            "<h1>You're back in!</h1><p>We re-activated your subscription. "
            "Welcome back to TrueFans SIGNAL.</p>"
        )


@router.post("/feedback")
async def issue_feedback(request: Request):
    """Footer widget: subscribers click love-it / meh / unsubscribe-me on
    a sent issue. Records to engagement_metrics for editorial review.

    Form params: token, issue_id, rating ('love'|'meh'|'unsub').
    """
    form = await request.form()
    token = (form.get("token", "") or "").strip()
    issue_id_raw = (form.get("issue_id", "") or "").strip()
    rating = (form.get("rating", "") or "").strip().lower()
    if rating not in ("love", "meh", "unsub"):
        return JSONResponse({"error": "invalid rating"}, status_code=400)
    repo = _get_repo()
    conn = repo._conn()
    sub_row = conn.execute(
        "SELECT id FROM subscribers WHERE unsubscribe_token = ?", (token,)
    ).fetchone()
    if not sub_row:
        conn.close()
        return JSONResponse({"error": "invalid token"}, status_code=400)
    sub_id = sub_row["id"] if isinstance(sub_row, dict) else sub_row[0]
    try:
        issue_id = int(issue_id_raw) if issue_id_raw else None
    except ValueError:
        issue_id = None
    try:
        conn.execute(
            "INSERT INTO email_tracking_events "
            "(subscriber_id, issue_id, event_type, occurred_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (sub_id, issue_id, f"feedback:{rating}"),
        )
        conn.commit()
    except Exception:
        # email_tracking_events might not exist on dev DBs — fall through
        pass
    if rating == "unsub":
        conn.execute(
            "UPDATE subscribers SET status = 'unsubscribed' WHERE id = ?",
            (sub_id,),
        )
        conn.commit()
    conn.close()
    return JSONResponse({"recorded": True, "rating": rating})


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
    rcode = request.query_params.get("rcode", "")
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

    # Build referral URL if code was generated
    cfg = load_config()
    referral_url = ""
    subscriber_count = 0
    if rcode:
        referral_url = f"{cfg.site_domain.rstrip('/')}/refer?code={rcode}"

    # Get subscriber count for social proof
    try:
        conn = repo._conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM subscribers WHERE status = 'active'"
        ).fetchone()
        conn.close()
        subscriber_count = row["cnt"] if row else 0
    except Exception:
        pass

    tpl = _env.get_template("subscribe_confirm.html")
    return tpl.render(
        selected_editions=selected,
        referral_url=referral_url,
        subscriber_count=subscriber_count,
    )


@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_quiz(request: Request, token: str = ""):
    return HTMLResponse(render("onboarding_quiz.html", token=token))


@router.post("/onboarding", response_class=HTMLResponse)
async def process_onboarding(request: Request):
    form = await request.form()
    repo = _get_repo()
    # Save responses
    music_role = form.get("music_role", "")
    genres = form.getlist("genres")
    interests = form.get("interests", "")

    # Map role to edition
    edition_map = {"fan": "fan", "artist": "artist", "industry": "industry", "both": "fan,artist"}
    recommended_edition = edition_map.get(music_role, "fan")

    return HTMLResponse(render("onboarding_result.html",
        recommended_edition=recommended_edition, genres=genres, interests=interests))
