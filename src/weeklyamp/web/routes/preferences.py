"""Subscriber preference center (public, subscriber-facing)."""

from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()
logger = logging.getLogger(__name__)


def _validate_token(token: str):
    """Look up subscriber by preference token. Returns subscriber dict or None."""
    repo = get_repo()
    conn = repo._conn()
    row = conn.execute(
        "SELECT * FROM subscribers WHERE preference_token = ? AND status = 'active'",
        (token,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


@router.get("/preferences/{token}", response_class=HTMLResponse)
async def preferences_page(token: str):
    """Show preference form for a subscriber."""
    subscriber = _validate_token(token)
    if not subscriber:
        return HTMLResponse(
            "<html><body style='font-family:Inter,sans-serif;max-width:600px;margin:60px auto;text-align:center'>"
            "<h2>Invalid or expired link</h2>"
            "<p>This preference link is no longer valid. Please use the link from your most recent email.</p>"
            "</body></html>",
            status_code=404,
        )

    cfg = get_config()
    return render("preferences.html",
        subscriber=subscriber,
        token=token,
        newsletter_name=cfg.newsletter.name,
    )


@router.post("/preferences/{token}", response_class=HTMLResponse)
async def update_preferences(
    token: str,
    editions: list[str] = Form(default=[]),
    send_days: list[str] = Form(default=[]),
    content_frequency: str = Form("all"),
    timezone: str = Form("America/New_York"),
    interests: str = Form(""),
):
    """Update subscriber preferences."""
    subscriber = _validate_token(token)
    if not subscriber:
        return HTMLResponse(
            "<html><body style='font-family:Inter,sans-serif;max-width:600px;margin:60px auto;text-align:center'>"
            "<h2>Invalid or expired link</h2>"
            "<p>This preference link is no longer valid.</p>"
            "</body></html>",
            status_code=404,
        )

    try:
        repo = get_repo()
        conn = repo._conn()
        conn.execute(
            """UPDATE subscribers SET
               editions = ?,
               send_days = ?,
               content_frequency = ?,
               timezone = ?,
               interests = ?,
               updated_at = datetime('now')
               WHERE preference_token = ?""",
            (
                ",".join(editions),
                ",".join(send_days),
                content_frequency,
                timezone,
                interests.strip(),
                token,
            ),
        )
        conn.commit()
        conn.close()

        # Re-fetch updated subscriber
        subscriber = _validate_token(token)
        cfg = get_config()
        return render("preferences.html",
            subscriber=subscriber,
            token=token,
            newsletter_name=cfg.newsletter.name,
            message="Your preferences have been saved.",
            level="success",
        )
    except Exception as exc:
        logger.exception("Failed to update preferences for token=%s", token)
        cfg = get_config()
        return render("preferences.html",
            subscriber=subscriber,
            token=token,
            newsletter_name=cfg.newsletter.name,
            message=f"Failed to save preferences: {exc}",
            level="error",
        )
