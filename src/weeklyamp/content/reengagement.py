"""Re-engagement automation.

Identifies inactive subscribers, creates re-engagement campaigns,
tracks responses, and auto-suppresses long-term non-responders.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from weeklyamp.core.models import ReengagementConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


class ReengagementManager:
    """Manage the subscriber re-engagement lifecycle."""

    def __init__(self, repo: Repository, config: ReengagementConfig) -> None:
        self.repo = repo
        self.config = config

    # ------------------------------------------------------------------
    # Inactive subscriber detection
    # ------------------------------------------------------------------

    def find_inactive_subscribers(self, days: Optional[int] = None) -> list[dict]:
        """Find active subscribers with no tracking events in the last *days*.

        Defaults to ``config.inactive_days`` when *days* is ``None``.
        """
        if not self.config.enabled:
            logger.debug("Re-engagement disabled — skipping inactive scan")
            return []

        inactive_days = days if days is not None else self.config.inactive_days

        conn = self.repo._conn()
        rows = conn.execute(
            """SELECT s.*
               FROM subscribers s
               LEFT JOIN email_tracking_events ete
                   ON ete.subscriber_id = s.id
                   AND ete.created_at >= datetime('now', ? || ' days')
               WHERE s.status = 'active'
               GROUP BY s.id
               HAVING COUNT(ete.id) = 0""",
            (str(-inactive_days),),
        ).fetchall()
        conn.close()

        logger.info(
            "Found %d inactive subscribers (no events in %d days)",
            len(rows), inactive_days,
        )
        return [dict(r) for r in rows]

    def get_suppression_candidates(self, days: Optional[int] = None) -> list[dict]:
        """Find subscribers inactive for *suppress_after_days* who also
        have no re-engagement opens recorded.
        """
        if not self.config.enabled:
            return []

        suppress_days = days if days is not None else self.config.suppress_after_days

        conn = self.repo._conn()
        rows = conn.execute(
            """SELECT s.*
               FROM subscribers s
               LEFT JOIN email_tracking_events ete
                   ON ete.subscriber_id = s.id
                   AND ete.created_at >= datetime('now', ? || ' days')
               LEFT JOIN reengagement_log rl
                   ON rl.subscriber_id = s.id AND rl.opened = 1
               WHERE s.status = 'active'
               GROUP BY s.id
               HAVING COUNT(ete.id) = 0 AND COUNT(rl.id) = 0""",
            (str(-suppress_days),),
        ).fetchall()
        conn.close()

        logger.info(
            "Found %d suppression candidates (inactive %d+ days, no re-engagement opens)",
            len(rows), suppress_days,
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Campaign management
    # ------------------------------------------------------------------

    def create_campaign(
        self,
        subscriber_ids: list[int],
        campaign_type: str = "winback",
    ) -> list[int]:
        """Create a re-engagement log entry for each subscriber.

        Returns the list of created log row ids.
        """
        if not self.config.enabled:
            logger.debug("Re-engagement disabled — not creating campaign")
            return []

        conn = self.repo._conn()
        log_ids: list[int] = []
        for sub_id in subscriber_ids:
            cur = conn.execute(
                """INSERT INTO reengagement_log
                       (subscriber_id, campaign_type)
                   VALUES (?, ?)""",
                (sub_id, campaign_type),
            )
            log_ids.append(cur.lastrowid)
        conn.commit()
        conn.close()

        logger.info(
            "Created re-engagement campaign '%s' for %d subscribers",
            campaign_type, len(subscriber_ids),
        )
        return log_ids

    def record_response(
        self,
        log_id: int,
        opened: bool = False,
        clicked: bool = False,
    ) -> None:
        """Update a re-engagement log entry with open/click data."""
        conn = self.repo._conn()
        conn.execute(
            """UPDATE reengagement_log
               SET opened = ?, clicked = ?, responded_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (int(opened), int(clicked), log_id),
        )
        conn.commit()
        conn.close()
        logger.info("Recorded re-engagement response for log %s (opened=%s, clicked=%s)", log_id, opened, clicked)

    # ------------------------------------------------------------------
    # Auto-suppression
    # ------------------------------------------------------------------

    def auto_suppress_inactive(self) -> int:
        """Mark long-inactive subscribers with no engagement and no
        re-engagement response as ``status='inactive'``.

        Returns the count of suppressed subscribers.
        """
        if not self.config.enabled:
            logger.debug("Re-engagement disabled — skipping auto-suppress")
            return 0

        candidates = self.get_suppression_candidates()
        if not candidates:
            return 0

        conn = self.repo._conn()
        suppressed = 0
        for sub in candidates:
            conn.execute(
                "UPDATE subscribers SET status = 'inactive' WHERE id = ? AND status = 'active'",
                (sub["id"],),
            )
            suppressed += 1
        conn.commit()
        conn.close()

        logger.info("Auto-suppressed %d inactive subscribers", suppressed)
        return suppressed

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return a summary of re-engagement activity."""
        conn = self.repo._conn()

        inactive_row = conn.execute(
            "SELECT COUNT(*) as c FROM subscribers WHERE status = 'inactive'"
        ).fetchone()
        inactive_count = inactive_row["c"] if inactive_row else 0

        sent_row = conn.execute(
            "SELECT COUNT(*) as c FROM reengagement_log"
        ).fetchone()
        reengagement_sent = sent_row["c"] if sent_row else 0

        opened_row = conn.execute(
            "SELECT COUNT(*) as c FROM reengagement_log WHERE opened = 1"
        ).fetchone()
        reengagement_opened = opened_row["c"] if opened_row else 0

        suppressed_row = conn.execute(
            "SELECT COUNT(*) as c FROM subscribers WHERE status = 'inactive'"
        ).fetchone()
        suppressed = suppressed_row["c"] if suppressed_row else 0

        conn.close()

        return {
            "inactive_count": inactive_count,
            "reengagement_sent": reengagement_sent,
            "reengagement_opened": reengagement_opened,
            "suppressed": suppressed,
        }
