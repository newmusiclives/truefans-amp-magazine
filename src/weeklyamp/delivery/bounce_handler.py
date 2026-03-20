"""Bounce handling and email suppression for newsletter delivery."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from weeklyamp.core.models import DeliverabilityConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


class BounceHandler:
    """Records bounce events, manages suppression lists, and filters recipients.

    All operations are gated behind ``config.bounce_handling``.  When the
    feature flag is ``False``, recording still works (for auditing) but
    suppression checks always return ``False`` and filtering is a no-op.
    """

    def __init__(self, repo: Repository, config: DeliverabilityConfig) -> None:
        self.repo = repo
        self.config = config

    # ------------------------------------------------------------------
    # Record bounces
    # ------------------------------------------------------------------

    def record_bounce(
        self,
        email: str,
        bounce_type: str,
        raw_response: str = "",
    ) -> Optional[int]:
        """Log a bounce event to the ``bounce_log`` table.

        Args:
            email: The recipient email address that bounced.
            bounce_type: One of ``'hard'``, ``'soft'``, ``'complaint'``.
            raw_response: The raw server / webhook response for debugging.

        Returns:
            The inserted row ID, or ``None`` on failure.
        """
        conn = self.repo._conn()
        try:
            cur = conn.execute(
                """INSERT INTO bounce_log (email, bounce_type, raw_response)
                   VALUES (?, ?, ?)""",
                (email, bounce_type, raw_response),
            )
            conn.commit()
            row_id = cur.lastrowid
            logger.info(
                "Bounce recorded: email=%s type=%s id=%s", email, bounce_type, row_id,
            )
            return row_id
        except Exception:
            logger.exception("Failed to record bounce for %s", email)
            conn.rollback()
            return None
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Suppression checks
    # ------------------------------------------------------------------

    def should_suppress(self, email: str) -> bool:
        """Return ``True`` if *email* should be suppressed from future sends.

        Suppression rules (evaluated only when ``bounce_handling`` is enabled):
        * Hard bounces >= ``hard_bounce_threshold``
        * Soft bounces >= ``soft_bounce_threshold``
        * Any complaint on record
        """
        if not self.config.bounce_handling:
            return False

        conn = self.repo._conn()
        try:
            row = conn.execute(
                """SELECT
                       COALESCE(SUM(CASE WHEN bounce_type = 'hard' THEN 1 ELSE 0 END), 0) AS hard,
                       COALESCE(SUM(CASE WHEN bounce_type = 'soft' THEN 1 ELSE 0 END), 0) AS soft,
                       COALESCE(SUM(CASE WHEN bounce_type = 'complaint' THEN 1 ELSE 0 END), 0) AS complaint
                   FROM bounce_log
                   WHERE email = ?""",
                (email,),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            return False

        if row["hard"] >= self.config.hard_bounce_threshold:
            return True
        if row["soft"] >= self.config.soft_bounce_threshold:
            return True
        if row["complaint"] > 0:
            return True
        return False

    def get_suppressed_emails(self) -> set[str]:
        """Return the full set of email addresses that should be suppressed.

        This scans the ``bounce_log`` table and applies the threshold rules
        from config.  Only meaningful when ``bounce_handling`` is enabled.
        """
        if not self.config.bounce_handling:
            return set()

        conn = self.repo._conn()
        try:
            rows = conn.execute(
                """SELECT email,
                       COALESCE(SUM(CASE WHEN bounce_type = 'hard' THEN 1 ELSE 0 END), 0) AS hard,
                       COALESCE(SUM(CASE WHEN bounce_type = 'soft' THEN 1 ELSE 0 END), 0) AS soft,
                       COALESCE(SUM(CASE WHEN bounce_type = 'complaint' THEN 1 ELSE 0 END), 0) AS complaint
                   FROM bounce_log
                   GROUP BY email""",
            ).fetchall()
        finally:
            conn.close()

        suppressed: set[str] = set()
        for row in rows:
            if row["hard"] >= self.config.hard_bounce_threshold:
                suppressed.add(row["email"])
            elif row["soft"] >= self.config.soft_bounce_threshold:
                suppressed.add(row["email"])
            elif row["complaint"] > 0:
                suppressed.add(row["email"])

        logger.debug("Suppression list contains %d emails", len(suppressed))
        return suppressed

    # ------------------------------------------------------------------
    # Recipient filtering
    # ------------------------------------------------------------------

    def filter_recipients(self, recipients: list[dict]) -> list[dict]:
        """Remove suppressed emails from a recipient list.

        Args:
            recipients: List of subscriber dicts, each containing an
                ``"email"`` key.

        Returns:
            Filtered list with suppressed addresses removed.  If bounce
            handling is disabled, the original list is returned as-is.
        """
        if not self.config.bounce_handling:
            return recipients

        suppressed = self.get_suppressed_emails()
        if not suppressed:
            return recipients

        original_count = len(recipients)
        filtered = [r for r in recipients if r.get("email", "").lower() not in suppressed]
        removed = original_count - len(filtered)

        if removed:
            logger.info(
                "Filtered %d suppressed recipients from %d total",
                removed,
                original_count,
            )
        return filtered

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_bounce_stats(self) -> dict[str, int]:
        """Return a summary of bounce events.

        Returns:
            ``{"hard": N, "soft": N, "complaint": N, "total": N}``
        """
        conn = self.repo._conn()
        try:
            row = conn.execute(
                """SELECT
                       COALESCE(SUM(CASE WHEN bounce_type = 'hard' THEN 1 ELSE 0 END), 0) AS hard,
                       COALESCE(SUM(CASE WHEN bounce_type = 'soft' THEN 1 ELSE 0 END), 0) AS soft,
                       COALESCE(SUM(CASE WHEN bounce_type = 'complaint' THEN 1 ELSE 0 END), 0) AS complaint,
                       COUNT(*) AS total
                   FROM bounce_log""",
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            return {"hard": 0, "soft": 0, "complaint": 0, "total": 0}

        return {
            "hard": row["hard"],
            "soft": row["soft"],
            "complaint": row["complaint"],
            "total": row["total"],
        }
