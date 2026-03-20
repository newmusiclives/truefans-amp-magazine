"""Tracking pixel and click redirect endpoints (public, embedded in emails)."""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse, Response

from weeklyamp.web.deps import get_config, get_repo

router = APIRouter()
logger = logging.getLogger(__name__)

# 1x1 transparent GIF (43 bytes)
_TRANSPARENT_GIF = (
    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
    b"\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00"
    b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
    b"\x44\x01\x00\x3b"
)


@router.get("/t/open/{issue_id}/{subscriber_id}.gif")
async def track_open(issue_id: int, subscriber_id: int):
    """Record an open event and return a 1x1 transparent GIF."""
    cfg = get_config()

    if cfg.tracking.open_tracking:
        try:
            repo = get_repo()
            conn = repo._conn()
            conn.execute(
                """INSERT INTO email_tracking_events
                   (issue_id, subscriber_id, event_type, created_at)
                   VALUES (?, ?, 'open', ?)""",
                (issue_id, subscriber_id, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            conn.close()
        except Exception:
            logger.exception("Failed to record open event issue=%s sub=%s", issue_id, subscriber_id)

    return Response(
        content=_TRANSPARENT_GIF,
        media_type="image/gif",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@router.get("/t/click/{issue_id}/{subscriber_id}")
async def track_click(
    issue_id: int,
    subscriber_id: int,
    url: str = Query(""),
):
    """Record a click event and redirect to the original URL."""
    # Decode the base64-encoded URL
    try:
        original_url = base64.urlsafe_b64decode(url.encode()).decode("utf-8")
    except Exception:
        original_url = url or "/"

    cfg = get_config()

    if cfg.tracking.click_tracking:
        try:
            repo = get_repo()
            conn = repo._conn()
            conn.execute(
                """INSERT INTO email_tracking_events
                   (issue_id, subscriber_id, event_type, url, created_at)
                   VALUES (?, ?, 'click', ?, ?)""",
                (issue_id, subscriber_id, original_url, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            conn.close()
        except Exception:
            logger.exception("Failed to record click event issue=%s sub=%s", issue_id, subscriber_id)

    return RedirectResponse(url=original_url, status_code=302)
