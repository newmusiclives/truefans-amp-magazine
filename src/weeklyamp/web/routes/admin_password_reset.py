"""Admin password reset via email (GHL SMTP).

Flow:
  1. GET /login/forgot → enter admin email
  2. POST /login/forgot → if email matches the configured admin email,
     issue a 30-min signed token, store it in admin_settings under
     `password_reset_token` (one-shot), and send the reset link via
     SMTPSender. Return a neutral "check your email" page regardless
     of whether the email matched — never leak admin-email-enumeration.
  3. GET /login/reset?token=... → verify token, show new-password form
  4. POST /login/reset → update admin_settings.admin_password_hash,
     invalidate cached hash, consume the one-shot token.

Requires:
  - email.enabled=true + SMTP creds configured (uses existing SMTPSender)
  - An admin email address configured, either via env
    WEEKLYAMP_ADMIN_EMAIL or admin_settings['admin_email'].

Until email is wired (see memory project_email_pipeline_dark), this
flow accepts POSTs but the reset message never leaves the box. The
token is still issued and logged; an operator can retrieve it from
security_log + admin_settings during the outage window.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from weeklyamp.web.deps import get_config, get_repo, render
from weeklyamp.web.security import (
    _log_security_event,
    hash_password,
    invalidate_admin_hash_cache,
    issue_password_reset_token,
    verify_password_reset_token,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_admin_email() -> str:
    """Resolution order: env var → admin_settings row → empty string."""
    env = os.environ.get("WEEKLYAMP_ADMIN_EMAIL", "").strip()
    if env:
        return env
    try:
        return get_repo().get_admin_setting("admin_email") or ""
    except Exception:
        return ""


def _send_reset_email(to_email: str, reset_url: str) -> bool:
    """Send the reset link via SMTPSender. Returns True on dispatch,
    False if email is disabled or sending failed (we still return a
    neutral response to the user either way)."""
    try:
        config = get_config()
        if not config.email.enabled:
            logger.warning("Password reset requested but email.enabled=false — token logged, not sent")
            return False
        from weeklyamp.delivery.smtp_sender import SMTPSender
        sender = SMTPSender(config.email)
        result = sender.send_single(
            to_email=to_email,
            subject="Reset your TrueFans SIGNAL admin password",
            html_body=(
                f"<p>Someone (hopefully you) requested a password reset.</p>"
                f"<p><a href=\"{reset_url}\">Reset your password</a></p>"
                f"<p>This link expires in 30 minutes. If you didn't request it, ignore this email.</p>"
            ),
        )
        return bool(result)
    except Exception:
        logger.exception("Failed to send password reset email")
        return False


@router.get("/forgot", response_class=HTMLResponse)
async def forgot_password_form(request: Request) -> Response:
    return HTMLResponse(render("admin_password_forgot.html", message="", error=""))


@router.post("/forgot")
async def forgot_password_submit(
    request: Request,
    email: str = Form(...),
) -> Response:
    admin_email = _get_admin_email()
    # Never confirm/deny whether the email matches — prevents
    # enumeration. We always show the same neutral success page.
    neutral = HTMLResponse(render(
        "admin_password_forgot.html",
        message="If that email matches an admin account, a reset link is on its way.",
        error="",
    ))

    if not admin_email:
        logger.warning("Password reset attempted but no admin email configured")
        return neutral
    if email.strip().lower() != admin_email.strip().lower():
        _log_security_event(request, "password_reset_request_bad_email")
        return neutral

    token = issue_password_reset_token(admin_email)
    # Store as one-shot: presence of this key means the token is valid
    # for consumption. Reset handler clears it after successful update.
    try:
        get_repo().set_admin_setting("password_reset_token", token)
    except Exception:
        logger.exception("Failed to persist password reset token")
        return neutral

    # Build absolute URL from the current request — honors HTTPS/proxy.
    base = str(request.base_url).rstrip("/")
    reset_url = f"{base}/login/reset?token={token}"
    _send_reset_email(admin_email, reset_url)
    _log_security_event(request, "password_reset_requested")
    return neutral


@router.get("/reset", response_class=HTMLResponse)
async def reset_password_form(request: Request) -> Response:
    token = request.query_params.get("token", "")
    if not verify_password_reset_token(token):
        return HTMLResponse(
            render("admin_password_reset.html", token="", error="Reset link is invalid or expired."),
            status_code=400,
        )
    # Also check the one-shot DB row — token must match the row value.
    stored = get_repo().get_admin_setting("password_reset_token")
    if stored != token:
        return HTMLResponse(
            render("admin_password_reset.html", token="", error="Reset link has already been used."),
            status_code=400,
        )
    return HTMLResponse(render("admin_password_reset.html", token=token, error=""))


@router.post("/reset")
async def reset_password_submit(
    request: Request,
    token: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
) -> Response:
    email = verify_password_reset_token(token)
    if not email:
        return HTMLResponse(
            render("admin_password_reset.html", token="", error="Reset link is invalid or expired."),
            status_code=400,
        )
    repo = get_repo()
    if repo.get_admin_setting("password_reset_token") != token:
        return HTMLResponse(
            render("admin_password_reset.html", token="", error="Reset link has already been used."),
            status_code=400,
        )
    if new_password != confirm_password:
        return HTMLResponse(
            render("admin_password_reset.html", token=token, error="Passwords do not match."),
            status_code=400,
        )
    if len(new_password) < 12:
        return HTMLResponse(
            render("admin_password_reset.html", token=token, error="Password must be at least 12 characters."),
            status_code=400,
        )

    repo.set_admin_setting("admin_password_hash", hash_password(new_password))
    invalidate_admin_hash_cache()
    # Consume the one-shot token so it can't be replayed.
    repo.set_admin_setting("password_reset_token", "")
    _log_security_event(request, "password_reset_completed")
    return RedirectResponse("/login", status_code=302)
