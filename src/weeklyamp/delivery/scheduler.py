"""Scheduled newsletter publishing — queue, check, and execute timed sends."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from weeklyamp.core.models import EmailConfig, SchedulerConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


class SendScheduler:
    """Manages the ``scheduled_sends`` queue for time-delayed publishing.

    Sends are inserted with a ``scheduled_at`` timestamp.  The
    ``process_pending`` method picks up all due sends and dispatches them
    via :class:`~weeklyamp.delivery.smtp_sender.SMTPSender`.

    All operations are gated behind ``scheduler_config.enabled``.  When
    disabled, scheduling methods log a warning and return early.
    """

    def __init__(
        self,
        repo: Repository,
        scheduler_config: SchedulerConfig,
        email_config: EmailConfig,
    ) -> None:
        self.repo = repo
        self.scheduler_config = scheduler_config
        self.email_config = email_config

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------

    def schedule_send(
        self,
        issue_id: int,
        edition_slug: str,
        subject: str,
        scheduled_at: str,
    ) -> Optional[int]:
        """Insert a new scheduled send into the queue.

        Args:
            issue_id: The issue to send.
            edition_slug: Target edition (e.g. ``"fan"``).
            subject: Email subject line.
            scheduled_at: ISO-8601 datetime string for when to send.

        Returns:
            The inserted row ID, or ``None`` if the scheduler is disabled.
        """
        if not self.scheduler_config.enabled:
            logger.warning("Scheduler is disabled — send not queued")
            return None

        conn = self.repo._conn()
        try:
            cur = conn.execute(
                """INSERT INTO scheduled_sends
                   (issue_id, edition_slug, subject, scheduled_at, status)
                   VALUES (?, ?, ?, ?, 'pending')""",
                (issue_id, edition_slug, subject, scheduled_at),
            )
            conn.commit()
            row_id = cur.lastrowid
            logger.info(
                "Scheduled send queued: id=%s issue=%s at=%s",
                row_id, issue_id, scheduled_at,
            )
            return row_id
        except Exception:
            logger.exception("Failed to queue scheduled send for issue %s", issue_id)
            conn.rollback()
            return None
        finally:
            conn.close()

    def cancel_send(self, scheduled_id: int) -> bool:
        """Mark a scheduled send as cancelled.

        Returns:
            ``True`` if the send was cancelled, ``False`` if it was not
            found or already processed.
        """
        conn = self.repo._conn()
        try:
            conn.execute(
                """UPDATE scheduled_sends
                   SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND status = 'pending'""",
                (scheduled_id,),
            )
            conn.commit()
            # Check if a row was actually updated
            row = conn.execute(
                "SELECT status FROM scheduled_sends WHERE id = ?", (scheduled_id,),
            ).fetchone()
            cancelled = row is not None and row["status"] == "cancelled"
            if cancelled:
                logger.info("Scheduled send %s cancelled", scheduled_id)
            return cancelled
        except Exception:
            logger.exception("Failed to cancel scheduled send %s", scheduled_id)
            conn.rollback()
            return False
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_pending_sends(self) -> list[dict]:
        """Return all pending sends whose ``scheduled_at`` is in the past."""
        conn = self.repo._conn()
        try:
            rows = conn.execute(
                """SELECT * FROM scheduled_sends
                   WHERE status = 'pending' AND scheduled_at <= CURRENT_TIMESTAMP
                   ORDER BY scheduled_at""",
            ).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]

    def get_upcoming_sends(self, limit: int = 10) -> list[dict]:
        """Return the next *limit* scheduled sends (pending, future or past)."""
        conn = self.repo._conn()
        try:
            rows = conn.execute(
                """SELECT * FROM scheduled_sends
                   WHERE status = 'pending'
                   ORDER BY scheduled_at
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def process_pending(self) -> list[int]:
        """Check for due sends and execute them.

        For each due send:
        1. Mark status as ``'processing'``.
        2. Retrieve the assembled HTML for the issue.
        3. Get subscriber list for the edition.
        4. Send via :class:`SMTPSender`.
        5. Mark as ``'sent'`` on success or ``'failed'`` on error.

        Returns:
            List of processed scheduled-send IDs.
        """
        if not self.scheduler_config.enabled:
            return []

        pending = self.get_pending_sends()
        if not pending:
            return []

        # Lazy import to avoid circular dependencies
        from weeklyamp.delivery.smtp_sender import SMTPSender

        sender = SMTPSender(self.email_config)
        processed: list[int] = []

        for send in pending:
            send_id = send["id"]
            issue_id = send["issue_id"]
            edition_slug = send.get("edition_slug", "")
            subject = send.get("subject", "")

            # Mark as processing
            conn = self.repo._conn()
            try:
                conn.execute(
                    """UPDATE scheduled_sends
                       SET status = 'processing', updated_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (send_id,),
                )
                conn.commit()
            finally:
                conn.close()

            try:
                # Get assembled HTML
                assembled = self.repo.get_assembled(issue_id)
                if not assembled:
                    raise ValueError(f"No assembled content for issue {issue_id}")

                html_body = assembled.get("html_content", "")
                plain_text = assembled.get("plain_text", "")

                # Get subscribers for this edition
                # TODO: add edition-filtered subscriber query to Repository
                # For now, get all active subscribers
                recipients = self.repo.get_subscribers("active")

                if not recipients:
                    logger.warning(
                        "No recipients for scheduled send %s (issue %s)",
                        send_id, issue_id,
                    )

                # Send via SMTP
                result = sender.send_bulk(
                    recipients=recipients,
                    subject=subject,
                    html_body=html_body,
                    plain_text=plain_text,
                )

                # Mark as sent
                conn = self.repo._conn()
                try:
                    conn.execute(
                        """UPDATE scheduled_sends
                           SET status = 'sent',
                               sent_at = CURRENT_TIMESTAMP,
                               result_json = ?,
                               updated_at = CURRENT_TIMESTAMP
                           WHERE id = ?""",
                        (
                            f'{{"sent":{result["sent"]},"failed":{result["failed"]}}}',
                            send_id,
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()

                logger.info(
                    "Scheduled send %s complete: sent=%d failed=%d",
                    send_id, result["sent"], result["failed"],
                )

            except Exception:
                logger.exception("Scheduled send %s failed", send_id)
                conn = self.repo._conn()
                try:
                    conn.execute(
                        """UPDATE scheduled_sends
                           SET status = 'failed', updated_at = CURRENT_TIMESTAMP
                           WHERE id = ?""",
                        (send_id,),
                    )
                    conn.commit()
                finally:
                    conn.close()

            processed.append(send_id)

        logger.info("Processed %d scheduled sends", len(processed))
        return processed
