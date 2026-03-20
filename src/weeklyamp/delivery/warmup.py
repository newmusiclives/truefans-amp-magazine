"""Domain warm-up manager for gradual send-volume ramp-up."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from weeklyamp.core.models import DeliverabilityConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


class WarmupManager:
    """Manages domain warm-up schedules to protect sender reputation.

    During warm-up, the daily send volume starts at ``warmup_daily_start``
    and increases by ``warmup_ramp_increment`` each day.  The warm-up state
    is persisted in the ``warmup_config`` table.

    All operations are gated behind ``config.warmup_enabled``.  When the
    feature is disabled, ``get_daily_limit`` returns ``None`` (unlimited)
    and ``limit_recipients`` is a no-op.
    """

    def __init__(self, repo: Repository, config: DeliverabilityConfig) -> None:
        self.repo = repo
        self.config = config

    # ------------------------------------------------------------------
    # Daily limit calculation
    # ------------------------------------------------------------------

    def get_daily_limit(self, domain: str) -> Optional[int]:
        """Calculate today's maximum send volume for *domain*.

        Formula: ``daily_limit + (ramp_increment * current_day)``

        Args:
            domain: The sending domain (e.g. ``"truefansnewsletters.com"``).

        Returns:
            The send limit for today, or ``None`` if warm-up is not active
            or the feature is disabled.
        """
        if not self.config.warmup_enabled:
            return None

        conn = self.repo._conn()
        try:
            row = conn.execute(
                """SELECT daily_limit, ramp_increment, current_day, is_active
                   FROM warmup_config
                   WHERE domain = ?""",
                (domain,),
            ).fetchone()
        finally:
            conn.close()

        if row is None or not row["is_active"]:
            return None

        limit = row["daily_limit"] + (row["ramp_increment"] * row["current_day"])
        logger.debug(
            "Warmup limit for %s: day=%d limit=%d", domain, row["current_day"], limit,
        )
        return limit

    # ------------------------------------------------------------------
    # Day advancement
    # ------------------------------------------------------------------

    def increment_day(self, domain: str) -> bool:
        """Advance the warm-up day counter for *domain*.

        Returns:
            ``True`` if the counter was incremented, ``False`` if warm-up
            is disabled or the domain has no active warm-up entry.
        """
        if not self.config.warmup_enabled:
            return False

        conn = self.repo._conn()
        try:
            row = conn.execute(
                "SELECT id, current_day, is_active FROM warmup_config WHERE domain = ?",
                (domain,),
            ).fetchone()
            if row is None or not row["is_active"]:
                return False

            new_day = row["current_day"] + 1
            conn.execute(
                "UPDATE warmup_config SET current_day = ? WHERE id = ?",
                (new_day, row["id"]),
            )
            conn.commit()
            logger.info("Warmup day incremented for %s: day=%d", domain, new_day)
            return True
        except Exception:
            logger.exception("Failed to increment warmup day for %s", domain)
            conn.rollback()
            return False
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Status checks
    # ------------------------------------------------------------------

    def is_warmup_active(self, domain: str) -> bool:
        """Return ``True`` if *domain* has an active warm-up in progress."""
        if not self.config.warmup_enabled:
            return False

        conn = self.repo._conn()
        try:
            row = conn.execute(
                "SELECT is_active FROM warmup_config WHERE domain = ?",
                (domain,),
            ).fetchone()
        finally:
            conn.close()

        return bool(row and row["is_active"])

    def get_warmup_status(self, domain: str) -> dict:
        """Return the current warm-up status for *domain*.

        Returns:
            ``{"active": bool, "current_day": int, "daily_limit": int,
            "ramp_increment": int, "today_limit": int, "started_at": str}``
        """
        default = {
            "active": False,
            "current_day": 0,
            "daily_limit": 0,
            "ramp_increment": 0,
            "today_limit": 0,
            "started_at": None,
        }

        if not self.config.warmup_enabled:
            return default

        conn = self.repo._conn()
        try:
            row = conn.execute(
                """SELECT daily_limit, ramp_increment, current_day, is_active, started_at
                   FROM warmup_config
                   WHERE domain = ?""",
                (domain,),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            return default

        today_limit = row["daily_limit"] + (row["ramp_increment"] * row["current_day"])
        return {
            "active": bool(row["is_active"]),
            "current_day": row["current_day"],
            "daily_limit": row["daily_limit"],
            "ramp_increment": row["ramp_increment"],
            "today_limit": today_limit,
            "started_at": row["started_at"],
        }

    # ------------------------------------------------------------------
    # Recipient limiting
    # ------------------------------------------------------------------

    def limit_recipients(self, recipients: list[dict], domain: str) -> list[dict]:
        """Truncate *recipients* to today's warm-up send limit for *domain*.

        If warm-up is not active or disabled, the full list is returned.

        Args:
            recipients: List of subscriber dicts.
            domain: The sending domain.

        Returns:
            A (possibly truncated) copy of the recipients list.
        """
        limit = self.get_daily_limit(domain)
        if limit is None:
            return recipients

        if len(recipients) <= limit:
            return recipients

        logger.info(
            "Warmup: truncating recipients from %d to %d for domain %s",
            len(recipients),
            limit,
            domain,
        )
        return recipients[:limit]
