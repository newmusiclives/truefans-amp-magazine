"""Welcome drip email sequence.

Manages multi-step welcome sequences that are sent to new subscribers
over a configurable delay schedule.  The manager identifies pending
sends but does **not** deliver them — the caller is responsible for
the actual send (e.g. via SMTP or GoHighLevel).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from weeklyamp.core.models import EmailConfig, WelcomeSequenceConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


class WelcomeManager:
    """Orchestrate welcome-sequence step creation, scheduling, and send tracking."""

    def __init__(
        self,
        repo: Repository,
        config: WelcomeSequenceConfig,
        email_config: Optional[EmailConfig] = None,
    ) -> None:
        self.repo = repo
        self.config = config
        self.email_config = email_config

    # ------------------------------------------------------------------
    # Step CRUD
    # ------------------------------------------------------------------

    def get_steps(self, edition_slug: str = "") -> list[dict]:
        """Fetch active welcome-sequence steps, ordered by step_number.

        Optionally filter by *edition_slug*; returns all steps when empty.
        """
        conn = self.repo._conn()
        if edition_slug:
            rows = conn.execute(
                """SELECT * FROM welcome_sequence_steps
                   WHERE is_active = 1 AND edition_slug = ?
                   ORDER BY step_number""",
                (edition_slug,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM welcome_sequence_steps
                   WHERE is_active = 1
                   ORDER BY step_number""",
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def create_step(
        self,
        edition_slug: str,
        step_number: int,
        delay_hours: int,
        subject: str,
        html_content: str,
        plain_text: str = "",
    ) -> int:
        """Insert a new welcome-sequence step. Returns the new row id."""
        conn = self.repo._conn()
        cur = conn.execute(
            """INSERT INTO welcome_sequence_steps
                   (edition_slug, step_number, delay_hours, subject, html_content, plain_text)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (edition_slug, step_number, delay_hours, subject, html_content, plain_text),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        logger.info(
            "Created welcome step #%d for edition '%s' (id=%s)",
            step_number, edition_slug, row_id,
        )
        return row_id

    def update_step(self, step_id: int, **fields: object) -> None:
        """Update one or more fields on a welcome-sequence step."""
        allowed = {
            "edition_slug", "step_number", "delay_hours", "subject",
            "html_content", "plain_text", "is_active",
        }
        filtered = {k: v for k, v in fields.items() if k in allowed}
        if not filtered:
            return

        sets = ", ".join(f"{k} = ?" for k in filtered)
        vals = list(filtered.values()) + [step_id]
        conn = self.repo._conn()
        conn.execute(
            f"UPDATE welcome_sequence_steps SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            vals,
        )
        conn.commit()
        conn.close()
        logger.info("Updated welcome step %s: %s", step_id, list(filtered.keys()))

    # ------------------------------------------------------------------
    # Pending-send detection
    # ------------------------------------------------------------------

    def get_pending_sends(self) -> list[dict]:
        """Find subscribers who subscribed within the last 7 days and have
        not yet received their next welcome step.

        Returns a list of ``{"subscriber": <dict>, "step": <dict>}`` pairs.
        """
        conn = self.repo._conn()
        rows = conn.execute(
            """SELECT s.id AS subscriber_id, s.email, s.subscribed_at,
                      ws.id AS step_id, ws.step_number, ws.delay_hours,
                      ws.subject, ws.edition_slug
               FROM subscribers s
               CROSS JOIN welcome_sequence_steps ws
               LEFT JOIN welcome_sequence_log wsl
                   ON wsl.subscriber_id = s.id AND wsl.step_id = ws.id
               WHERE s.status = 'active'
                 AND s.subscribed_at >= datetime('now', '-7 days')
                 AND ws.is_active = 1
                 AND wsl.id IS NULL
               ORDER BY s.id, ws.step_number""",
        ).fetchall()
        conn.close()

        results: list[dict] = []
        for r in rows:
            row = dict(r)
            results.append({
                "subscriber": {
                    "id": row["subscriber_id"],
                    "email": row["email"],
                    "subscribed_at": row["subscribed_at"],
                },
                "step": {
                    "id": row["step_id"],
                    "step_number": row["step_number"],
                    "delay_hours": row["delay_hours"],
                    "subject": row["subject"],
                    "edition_slug": row["edition_slug"],
                },
            })
        return results

    # ------------------------------------------------------------------
    # Send recording
    # ------------------------------------------------------------------

    def record_send(self, subscriber_id: int, step_id: int) -> int:
        """Record that a welcome step was sent to a subscriber."""
        conn = self.repo._conn()
        cur = conn.execute(
            """INSERT INTO welcome_sequence_log (subscriber_id, step_id)
               VALUES (?, ?)""",
            (subscriber_id, step_id),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        logger.info(
            "Recorded welcome send: subscriber=%s step=%s", subscriber_id, step_id
        )
        return row_id

    # ------------------------------------------------------------------
    # Queue processing
    # ------------------------------------------------------------------

    def process_welcome_queue(self) -> list[dict]:
        """Evaluate pending sends and return those whose delay has elapsed.

        For step 1 the delay is measured from ``subscribed_at``.  For
        subsequent steps the delay is measured from the send time of the
        previous step.

        Returns a list of ``{"subscriber": ..., "step": ...}`` dicts
        that are ready to send.  Does **not** actually send anything.
        """
        if not self.config.enabled:
            logger.debug("Welcome sequence disabled — skipping queue processing")
            return []

        pending = self.get_pending_sends()
        now = datetime.utcnow()
        ready: list[dict] = []

        # Group pending by subscriber so we can look up previous step times
        from collections import defaultdict
        by_subscriber: dict[int, list[dict]] = defaultdict(list)
        for item in pending:
            by_subscriber[item["subscriber"]["id"]].append(item)

        for sub_id, items in by_subscriber.items():
            # Sort by step_number to process in order
            items.sort(key=lambda x: x["step"]["step_number"])

            for item in items:
                step = item["step"]
                subscriber = item["subscriber"]
                delay = timedelta(hours=step["delay_hours"])

                if step["step_number"] == 1:
                    # Delay measured from subscription time
                    subscribed_at = subscriber["subscribed_at"]
                    if isinstance(subscribed_at, str):
                        try:
                            ref_time = datetime.fromisoformat(
                                subscribed_at.replace("Z", "+00:00")
                            )
                        except ValueError:
                            continue
                    else:
                        ref_time = subscribed_at
                else:
                    # Delay measured from previous step's send time
                    prev_step_number = step["step_number"] - 1
                    conn = self.repo._conn()
                    prev_row = conn.execute(
                        """SELECT wsl.sent_at
                           FROM welcome_sequence_log wsl
                           JOIN welcome_sequence_steps ws ON wsl.step_id = ws.id
                           WHERE wsl.subscriber_id = ? AND ws.step_number = ?
                           ORDER BY wsl.sent_at DESC LIMIT 1""",
                        (sub_id, prev_step_number),
                    ).fetchone()
                    conn.close()

                    if not prev_row:
                        # Previous step not yet sent — skip this one
                        break

                    sent_at = prev_row["sent_at"]
                    if isinstance(sent_at, str):
                        try:
                            ref_time = datetime.fromisoformat(
                                sent_at.replace("Z", "+00:00")
                            )
                        except ValueError:
                            break
                    else:
                        ref_time = sent_at

                if now >= ref_time + delay:
                    ready.append(item)
                else:
                    # Not ready yet — later steps for this subscriber won't be either
                    break

        logger.info("Welcome queue: %d sends ready out of %d pending", len(ready), len(pending))
        return ready
