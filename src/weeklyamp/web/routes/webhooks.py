"""Webhook management routes (admin)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def webhooks_page():
    cfg = get_config()

    if not cfg.webhooks.enabled:
        return render("webhooks.html", enabled=False, webhooks=[], logs=[], config=cfg)

    repo = get_repo()
    conn = repo._conn()
    hooks = conn.execute(
        "SELECT * FROM webhooks ORDER BY created_at DESC"
    ).fetchall()
    hooks = [dict(r) for r in hooks]

    logs = conn.execute(
        "SELECT * FROM webhook_log ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    logs = [dict(r) for r in logs]
    conn.close()

    return render("webhooks.html", enabled=True, webhooks=hooks, logs=logs, config=cfg)


@router.post("/create", response_class=HTMLResponse)
async def create_webhook(
    name: str = Form(...),
    url: str = Form(...),
    direction: str = Form("outbound"),
    event_types: str = Form(""),
):
    cfg = get_config()
    if not cfg.webhooks.enabled:
        return render("partials/alert.html",
            message="Webhooks are not enabled. Set webhooks.enabled: true in config.",
            level="error")

    repo = get_repo()
    try:
        conn = repo._conn()
        conn.execute(
            """INSERT INTO webhooks (name, url, direction, event_types, is_active, created_at)
               VALUES (?, ?, ?, ?, 1, datetime('now'))""",
            (name, url, direction, event_types),
        )
        conn.commit()
        conn.close()

        return render("partials/alert.html",
            message=f"Webhook '{name}' created.", level="success")
    except Exception as exc:
        return render("partials/alert.html",
            message=f"Failed to create webhook: {exc}", level="error")


@router.post("/{webhook_id}/toggle", response_class=HTMLResponse)
async def toggle_webhook(webhook_id: int):
    cfg = get_config()
    if not cfg.webhooks.enabled:
        return render("partials/alert.html",
            message="Webhooks are not enabled.", level="error")

    repo = get_repo()
    try:
        conn = repo._conn()
        hook = conn.execute(
            "SELECT * FROM webhooks WHERE id = ?", (webhook_id,)
        ).fetchone()

        if not hook:
            conn.close()
            return render("partials/alert.html",
                message="Webhook not found.", level="error")

        new_state = 0 if hook["is_active"] else 1
        conn.execute(
            "UPDATE webhooks SET is_active = ? WHERE id = ?",
            (new_state, webhook_id),
        )
        conn.commit()
        conn.close()

        state_label = "activated" if new_state else "deactivated"
        return render("partials/alert.html",
            message=f"Webhook '{hook['name']}' {state_label}.", level="success")
    except Exception as exc:
        return render("partials/alert.html",
            message=f"Toggle failed: {exc}", level="error")


@router.post("/inbound")
async def inbound_webhook(request: Request):
    """Inbound webhook receiver — verify HMAC signature and process payload."""
    cfg = get_config()

    if not cfg.webhooks.enabled:
        return JSONResponse({"error": "Webhooks disabled"}, status_code=403)

    # Read body
    body = await request.body()
    body_str = body.decode("utf-8")

    # Verify HMAC signature if secret is configured
    if cfg.webhooks.inbound_secret:
        signature = request.headers.get("X-Webhook-Signature", "")
        expected = hmac.new(
            cfg.webhooks.inbound_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected):
            logger.warning("Inbound webhook HMAC verification failed")
            return JSONResponse({"error": "Invalid signature"}, status_code=401)

    # Parse and log
    try:
        payload = json.loads(body_str)
    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    event_type = payload.get("event", "unknown")

    try:
        repo = get_repo()
        conn = repo._conn()
        conn.execute(
            """INSERT INTO webhook_logs
               (webhook_id, direction, event_type, payload, status_code, created_at)
               VALUES (NULL, 'inbound', ?, ?, 200, ?)""",
            (event_type, body_str, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()
    except Exception:
        logger.exception("Failed to log inbound webhook")

    return JSONResponse({"status": "ok", "event": event_type})
