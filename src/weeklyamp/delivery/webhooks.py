"""Webhook system for inbound and outbound event notifications."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime
from typing import Optional

import httpx

from weeklyamp.core.models import WebhookConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


class WebhookManager:
    """Fire outbound webhooks, verify inbound signatures, and manage webhook config.

    All operations are gated behind ``config.enabled``.  When disabled,
    ``fire_event`` is a no-op and ``verify_inbound`` always returns ``False``.
    """

    def __init__(self, repo: Repository, config: WebhookConfig) -> None:
        self.repo = repo
        self.config = config

    # ------------------------------------------------------------------
    # Outbound: fire events
    # ------------------------------------------------------------------

    def fire_event(self, event_type: str, payload_dict: dict) -> list[dict]:
        """Find all active outbound webhooks matching *event_type* and POST to each.

        Each request includes:
        * ``Content-Type: application/json``
        * ``X-WeeklyAmp-Signature``: HMAC-SHA256 hex digest of the JSON body
          using the webhook's secret.
        * ``X-WeeklyAmp-Event``: The event type string.

        Results are logged to the ``webhook_log`` table.

        Args:
            event_type: Event identifier (e.g. ``"issue.published"``).
            payload_dict: Arbitrary JSON-serialisable payload.

        Returns:
            List of result dicts: ``{"webhook_id": int, "status_code": int,
            "success": bool, "error": str | None}``.
        """
        if not self.config.enabled:
            logger.debug("Webhooks disabled — skipping event %s", event_type)
            return []

        webhooks = self._get_matching_webhooks(event_type)
        if not webhooks:
            logger.debug("No outbound webhooks registered for %s", event_type)
            return []

        body_bytes = json.dumps(payload_dict, default=str).encode("utf-8")
        results: list[dict] = []

        for wh in webhooks:
            webhook_id = wh["id"]
            url = wh["url"]
            secret = wh.get("secret", "")

            # Compute HMAC signature
            signature = ""
            if secret:
                signature = hmac.new(
                    secret.encode("utf-8"),
                    body_bytes,
                    hashlib.sha256,
                ).hexdigest()

            headers = {
                "Content-Type": "application/json",
                "X-WeeklyAmp-Event": event_type,
                "X-WeeklyAmp-Signature": signature,
            }

            status_code = 0
            success = False
            error_msg: Optional[str] = None

            try:
                with httpx.Client(timeout=self.config.timeout_seconds) as client:
                    resp = client.post(url, content=body_bytes, headers=headers)
                    status_code = resp.status_code
                    success = 200 <= status_code < 300
                    if not success:
                        error_msg = f"HTTP {status_code}: {resp.text[:500]}"
            except httpx.TimeoutException:
                error_msg = "Request timed out"
                logger.warning("Webhook %s timed out for event %s", webhook_id, event_type)
            except Exception as exc:
                error_msg = str(exc)[:500]
                logger.exception(
                    "Webhook %s failed for event %s", webhook_id, event_type,
                )

            # Log the result
            self._log_delivery(
                webhook_id=webhook_id,
                event_type=event_type,
                url=url,
                status_code=status_code,
                success=success,
                error=error_msg,
            )

            results.append({
                "webhook_id": webhook_id,
                "status_code": status_code,
                "success": success,
                "error": error_msg,
            })

        return results

    # ------------------------------------------------------------------
    # Inbound: signature verification
    # ------------------------------------------------------------------

    def verify_inbound(self, signature: str, payload: bytes, secret: str) -> bool:
        """Verify an HMAC-SHA256 signature for an inbound webhook.

        Args:
            signature: The hex-encoded signature from the request header.
            payload: The raw request body bytes.
            secret: The shared secret for this webhook.

        Returns:
            ``True`` if the signature is valid.
        """
        if not self.config.enabled:
            return False

        if not signature or not secret:
            return False

        expected = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(signature, expected)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def get_webhooks(self, direction: str = "") -> list[dict]:
        """List webhooks, optionally filtered by direction.

        Args:
            direction: ``"inbound"``, ``"outbound"``, or ``""`` for all.

        Returns:
            List of webhook config dicts.
        """
        conn = self.repo._conn()
        try:
            if direction:
                rows = conn.execute(
                    "SELECT * FROM webhooks WHERE direction = ? AND is_active = 1 ORDER BY name",
                    (direction,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM webhooks WHERE is_active = 1 ORDER BY name",
                ).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]

    def create_webhook(
        self,
        name: str,
        url: str,
        direction: str,
        event_types: list[str],
        secret: str = "",
    ) -> Optional[int]:
        """Register a new webhook.

        Args:
            name: Human-readable label.
            url: The endpoint URL.
            direction: ``"inbound"`` or ``"outbound"``.
            event_types: List of event type strings this webhook subscribes to
                (stored as comma-separated).
            secret: Shared secret for HMAC signing.

        Returns:
            The inserted row ID, or ``None`` on error.
        """
        if not self.config.enabled:
            logger.warning("Webhooks disabled — cannot create webhook")
            return None

        events_csv = ",".join(event_types)
        conn = self.repo._conn()
        try:
            cur = conn.execute(
                """INSERT INTO webhooks (name, url, direction, event_types, secret)
                   VALUES (?, ?, ?, ?, ?)""",
                (name, url, direction, events_csv, secret),
            )
            conn.commit()
            row_id = cur.lastrowid
            logger.info("Webhook created: id=%s name=%s direction=%s", row_id, name, direction)
            return row_id
        except Exception:
            logger.exception("Failed to create webhook %s", name)
            conn.rollback()
            return None
        finally:
            conn.close()

    def get_webhook_log(self, webhook_id: int, limit: int = 50) -> list[dict]:
        """Return recent delivery log entries for a webhook.

        Args:
            webhook_id: The webhook to query.
            limit: Maximum entries to return.

        Returns:
            List of log entry dicts, most recent first.
        """
        conn = self.repo._conn()
        try:
            rows = conn.execute(
                """SELECT * FROM webhook_log
                   WHERE webhook_id = ?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (webhook_id, limit),
            ).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_matching_webhooks(self, event_type: str) -> list[dict]:
        """Return active outbound webhooks whose ``event_types`` include *event_type*."""
        conn = self.repo._conn()
        try:
            rows = conn.execute(
                """SELECT * FROM webhooks
                   WHERE direction = 'outbound' AND is_active = 1""",
            ).fetchall()
        finally:
            conn.close()

        matching = []
        for row in rows:
            row_dict = dict(row)
            registered_events = [
                e.strip() for e in row_dict.get("event_types", "").split(",") if e.strip()
            ]
            if event_type in registered_events or "*" in registered_events:
                matching.append(row_dict)
        return matching

    def _log_delivery(
        self,
        webhook_id: int,
        event_type: str,
        url: str,
        status_code: int,
        success: bool,
        error: Optional[str],
    ) -> None:
        """Insert a row into ``webhook_log``."""
        conn = self.repo._conn()
        try:
            conn.execute(
                """INSERT INTO webhook_log
                   (webhook_id, event_type, url, status_code, success, error)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (webhook_id, event_type, url, status_code, int(success), error or ""),
            )
            conn.commit()
        except Exception:
            logger.exception("Failed to log webhook delivery for %s", webhook_id)
            conn.rollback()
        finally:
            conn.close()
