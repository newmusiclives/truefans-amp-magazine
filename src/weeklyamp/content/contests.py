"""Contest and giveaway system for newsletter engagement.

Allows creating contests, recording entries, picking random winners.
INACTIVE by default — enable via config.
"""

from __future__ import annotations

import logging
import random
from typing import Optional

from weeklyamp.core.models import ContestsConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


class ContestManager:
    """Create, manage, and pick winners for contests and giveaways."""

    def __init__(self, repo: Repository, config: ContestsConfig) -> None:
        self.repo = repo
        self.config = config

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def create_contest(
        self,
        title: str,
        description: str,
        prize: str,
        contest_type: str = "share",
        entry_requirement: str = "",
        edition_slug: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> Optional[int]:
        """Create a new contest.  Returns the contest id."""
        if not self.config.enabled:
            logger.info("Contests disabled — skipping create_contest")
            return None

        # Check active contest limit
        active = self.get_active_contests()
        if len(active) >= self.config.max_active:
            raise ValueError(
                f"Max active contests ({self.config.max_active}) reached"
            )

        conn = self.repo._conn()
        try:
            cur = conn.execute(
                """INSERT INTO contests
                   (title, description, prize_description, contest_type,
                    entry_requirement, edition_slug, start_date, end_date, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
                (title, description, prize, contest_type,
                 entry_requirement, edition_slug, start_date, end_date),
            )
            conn.commit()
            contest_id = cur.lastrowid
            logger.info("Created contest %d: %s", contest_id, title)
            return contest_id
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------

    def enter_contest(
        self,
        contest_id: int,
        subscriber_id: int,
        email: str = "",
        entry_data: str = "{}",
    ) -> dict:
        """Record a contest entry.  Returns ``{success, already_entered, message}``."""
        if not self.config.enabled:
            return {"success": False, "already_entered": False, "message": "Contests disabled"}

        conn = self.repo._conn()
        try:
            # Check contest exists and is active
            row = conn.execute(
                "SELECT * FROM contests WHERE id = ?", (contest_id,)
            ).fetchone()
            if not row:
                return {"success": False, "already_entered": False, "message": "Contest not found"}
            contest = dict(row)
            if contest["status"] != "active":
                return {"success": False, "already_entered": False, "message": "Contest is not active"}

            # Check duplicate
            existing = conn.execute(
                "SELECT id FROM contest_entries WHERE contest_id = ? AND subscriber_id = ?",
                (contest_id, subscriber_id),
            ).fetchone()
            if existing:
                return {"success": False, "already_entered": True, "message": "Already entered"}

            conn.execute(
                """INSERT INTO contest_entries
                   (contest_id, subscriber_id, email, entry_data_json)
                   VALUES (?, ?, ?, ?)""",
                (contest_id, subscriber_id, email, entry_data),
            )
            conn.commit()
            logger.info("Subscriber %d entered contest %d", subscriber_id, contest_id)
            return {"success": True, "already_entered": False, "message": "Entry recorded"}
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_active_contests(self) -> list[dict]:
        """Return all active contests."""
        conn = self.repo._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM contests WHERE status = 'active' ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_all_contests(self) -> list[dict]:
        """Return all contests regardless of status."""
        conn = self.repo._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM contests ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_contest(self, contest_id: int) -> Optional[dict]:
        """Return a single contest by id."""
        conn = self.repo._conn()
        try:
            row = conn.execute(
                "SELECT * FROM contests WHERE id = ?", (contest_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_entry_count(self, contest_id: int) -> int:
        """Count entries for a contest."""
        conn = self.repo._conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM contest_entries WHERE contest_id = ?",
                (contest_id,),
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    def get_entries(self, contest_id: int) -> list[dict]:
        """Return all entries for a contest."""
        conn = self.repo._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM contest_entries WHERE contest_id = ? ORDER BY created_at",
                (contest_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Close / Pick winner
    # ------------------------------------------------------------------

    def close_contest(self, contest_id: int) -> None:
        """Set contest status to closed."""
        if not self.config.enabled:
            return
        conn = self.repo._conn()
        try:
            conn.execute(
                "UPDATE contests SET status = 'closed' WHERE id = ?",
                (contest_id,),
            )
            conn.commit()
            logger.info("Closed contest %d", contest_id)
        finally:
            conn.close()

    def pick_winner(self, contest_id: int) -> Optional[dict]:
        """Pick a random winner from entries.

        Updates the contest with the winner info and sets status to 'awarded'.
        Returns the winning entry or None if no entries exist.
        """
        if not self.config.enabled:
            return None

        entries = self.get_entries(contest_id)
        if not entries:
            logger.warning("No entries for contest %d — cannot pick winner", contest_id)
            return None

        winner = random.choice(entries)

        conn = self.repo._conn()
        try:
            # Look up subscriber name/email
            winner_name = winner.get("email", "")
            sub_row = conn.execute(
                "SELECT email, first_name FROM subscribers WHERE id = ?",
                (winner["subscriber_id"],),
            ).fetchone()
            if sub_row:
                sub = dict(sub_row)
                winner_name = sub.get("first_name") or sub.get("email", winner_name)

            conn.execute(
                """UPDATE contests
                   SET status = 'awarded',
                       winner_subscriber_id = ?,
                       winner_name = ?
                   WHERE id = ?""",
                (winner["subscriber_id"], winner_name, contest_id),
            )
            conn.commit()
            logger.info("Contest %d winner: subscriber %d (%s)",
                        contest_id, winner["subscriber_id"], winner_name)
            winner["winner_name"] = winner_name
            return winner
        finally:
            conn.close()
