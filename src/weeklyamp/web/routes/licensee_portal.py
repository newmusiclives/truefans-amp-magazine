"""White-label licensee portal — city edition operators manage their newsletter."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from weeklyamp.web.deps import get_config, get_repo, render
from weeklyamp.web.security import (
    _clear_attempts,
    _get_client_ip,
    _is_rate_limited,
    _log_security_event,
    _record_attempt,
    clear_licensee_session,
    create_licensee_session,
    get_licensee_id_from_session,
    verify_password,
)

router = APIRouter()

_RATE_LIMIT_TYPE = "licensee_login"


def _render_dashboard(licensee: dict) -> HTMLResponse:
    """Render the licensee dashboard for an authenticated licensee."""
    repo = get_repo()
    config = get_config()
    city = licensee.get("city_market_slug", "")
    # Scope subscriber count to the editions this licensee runs, not the
    # global tenant-wide count. edition_slugs is a comma-separated list
    # stored on the licensee row.
    licensee_editions = [
        s.strip() for s in (licensee.get("edition_slugs") or "").split(",") if s.strip()
    ]
    subscriber_count = repo.get_subscriber_count(edition_slugs=licensee_editions or None)
    revenue = repo.get_license_revenue(licensee["id"])
    prospects = repo.get_sponsor_prospects(limit=10)
    city_prospects = [
        p for p in prospects if city in (p.get("target_editions", "") or "")
    ]
    return HTMLResponse(
        render(
            "licensee_dashboard.html",
            licensee=licensee,
            subscriber_count=subscriber_count,
            revenue=revenue,
            prospects=city_prospects,
            config=config,
        )
    )


@router.get("/login", response_class=HTMLResponse)
async def licensee_login_page(request: Request):
    # Already logged in — go straight to dashboard
    if get_licensee_id_from_session(request) is not None:
        return RedirectResponse("/licensee/dashboard", status_code=302)
    return HTMLResponse(render("licensee_login.html"))


@router.post("/login")
async def licensee_login(
    request: Request, email: str = Form(...), password: str = Form(...)
):
    ip = _get_client_ip(request)

    # Rate limit by IP to prevent credential stuffing
    if _is_rate_limited(ip, limit_type=_RATE_LIMIT_TYPE):
        _log_security_event(request, "licensee_login_rate_limited", detail=email)
        return HTMLResponse(
            render(
                "licensee_login.html",
                error="Too many login attempts. Please try again later.",
            ),
            status_code=429,
        )

    repo = get_repo()
    licensee = repo.get_licensee_by_email(email)

    # Constant-ish-time response: always check a hash even if licensee doesn't exist,
    # to avoid leaking which emails are registered via timing.
    stored_hash = (licensee or {}).get("password_hash", "") or ""
    password_ok = bool(stored_hash) and verify_password(password, stored_hash)

    if not licensee or not password_ok:
        _record_attempt(ip, limit_type=_RATE_LIMIT_TYPE)
        _log_security_event(request, "licensee_login_failure", detail=email)
        return HTMLResponse(
            render("licensee_login.html", error="Invalid credentials"),
            status_code=401,
        )

    # Refuse logins for non-active licensees (suspended, past_due, revoked, etc.)
    status = (licensee.get("status") or "").lower()
    if status and status not in ("active", "trialing"):
        _log_security_event(
            request, "licensee_login_blocked_status", detail=f"{email}:{status}"
        )
        return HTMLResponse(
            render(
                "licensee_login.html",
                error="This account is not active. Please contact support.",
            ),
            status_code=403,
        )

    _clear_attempts(ip, limit_type=_RATE_LIMIT_TYPE)
    _log_security_event(request, "licensee_login_success", detail=email)

    response = RedirectResponse("/licensee/dashboard", status_code=302)
    create_licensee_session(response, licensee["id"], request)
    return response


@router.get("/dashboard", response_class=HTMLResponse)
async def licensee_dashboard(request: Request):
    licensee_id = get_licensee_id_from_session(request)
    if not licensee_id:
        return RedirectResponse("/licensee/login", status_code=302)
    repo = get_repo()
    licensee = repo.get_licensee(licensee_id)
    if not licensee:
        # Session points at a deleted licensee — clear it and force re-login
        response = RedirectResponse("/licensee/login", status_code=302)
        clear_licensee_session(response)
        return response
    return _render_dashboard(licensee)


@router.get("/logout")
async def licensee_logout(request: Request) -> Response:
    _log_security_event(request, "licensee_logout")
    response = RedirectResponse("/licensee/login", status_code=302)
    clear_licensee_session(response)
    return response
