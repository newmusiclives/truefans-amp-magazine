"""A/B testing framework for newsletter subject lines, content, and send times.

This module is INACTIVE by default — all mutating operations check the
``ABTestConfig.enabled`` flag before writing to the database.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime
from typing import Any, Optional

from weeklyamp.core.models import ABTestConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


class ABTestManager:
    """Create, manage, and evaluate A/B tests."""

    def __init__(self, repo: Repository, config: ABTestConfig) -> None:
        self.repo = repo
        self.config = config

    @property
    def _enabled(self) -> bool:
        return self.config.enabled

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_test(
        self,
        issue_id: int,
        test_type: str,
        variant_a: str,
        variant_b: str,
        sample_percent: int = 20,
    ) -> Optional[int]:
        """Insert a new A/B test and its two result rows.

        Returns the test id, or ``None`` if the feature is disabled.
        """
        if not self._enabled:
            logger.debug("A/B testing disabled — skipping create_test")
            return None

        sample = sample_percent or self.config.default_sample_percent

        conn = self.repo._conn()
        try:
            cur = conn.execute(
                """INSERT INTO ab_tests
                   (issue_id, test_type, variant_a, variant_b,
                    sample_size_percent, status)
                   VALUES (?, ?, ?, ?, ?, 'draft')""",
                (issue_id, test_type, variant_a, variant_b, sample),
            )
            conn.commit()
            test_id: int = cur.lastrowid

            # Create one result row per variant
            for variant in ("a", "b"):
                conn.execute(
                    """INSERT INTO ab_test_results
                       (test_id, variant, sends, opens, clicks, unsubscribes)
                       VALUES (?, ?, 0, 0, 0, 0)""",
                    (test_id, variant),
                )
            conn.commit()
            conn.close()

            logger.info("Created A/B test %d for issue %d (%s)", test_id, issue_id, test_type)
            return test_id
        except Exception:
            logger.exception("Failed to create A/B test")
            conn.close()
            return None

    # ------------------------------------------------------------------
    # Recipient splitting
    # ------------------------------------------------------------------

    def split_recipients(
        self, test_id: int, recipients: list[str]
    ) -> dict[str, list[str]]:
        """Split a recipient list into variant groups.

        Returns ``{"a": [...], "b": [...], "remainder": [...]}``.
        """
        if not self._enabled or not recipients:
            return {"a": [], "b": [], "remainder": list(recipients)}

        test = self.get_test(test_id)
        if not test:
            return {"a": [], "b": [], "remainder": list(recipients)}

        sample_pct = test.get("sample_size_percent", self.config.default_sample_percent)
        sample_size = max(2, int(len(recipients) * sample_pct / 100))
        # Ensure even split
        sample_size = sample_size if sample_size % 2 == 0 else sample_size + 1
        sample_size = min(sample_size, len(recipients))

        shuffled = list(recipients)
        random.shuffle(shuffled)

        half = sample_size // 2
        group_a = shuffled[:half]
        group_b = shuffled[half:sample_size]
        remainder = shuffled[sample_size:]

        return {"a": group_a, "b": group_b, "remainder": remainder}

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_send(self, test_id: int, variant: str, count: int) -> None:
        """Update the sends count for a variant."""
        if not self._enabled:
            return
        conn = self.repo._conn()
        try:
            conn.execute(
                "UPDATE ab_test_results SET sends = sends + ? "
                "WHERE test_id = ? AND variant = ?",
                (count, test_id, variant),
            )
            conn.commit()
        finally:
            conn.close()

    def record_event(self, test_id: int, variant: str, event_type: str) -> None:
        """Increment opens, clicks, or unsubscribes for a variant."""
        if not self._enabled:
            return

        column_map = {
            "open": "opens",
            "click": "clicks",
            "unsubscribe": "unsubscribes",
        }
        column = column_map.get(event_type)
        if not column:
            logger.warning("Unknown event type for A/B test: %s", event_type)
            return

        conn = self.repo._conn()
        try:
            conn.execute(
                f"UPDATE ab_test_results SET {column} = {column} + 1 "
                "WHERE test_id = ? AND variant = ?",
                (test_id, variant),
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate_winner(self, test_id: int) -> Optional[str]:
        """Compare open rates between variants and pick a winner.

        A winner is declared when the difference in open rates exceeds 5
        percentage points.  Updates ab_tests.winner and status.

        Returns the winning variant letter (``"a"`` or ``"b"``), or
        ``None`` if no significant difference is found.
        """
        if not self._enabled:
            return None

        conn = self.repo._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM ab_test_results WHERE test_id = ? ORDER BY variant",
                (test_id,),
            ).fetchall()

            if len(rows) < 2:
                conn.close()
                return None

            results = {r["variant"]: dict(r) for r in rows}
            a = results.get("a", {})
            b = results.get("b", {})

            sends_a = a.get("sends", 0) or 1
            sends_b = b.get("sends", 0) or 1
            rate_a = (a.get("opens", 0) / sends_a) * 100
            rate_b = (b.get("opens", 0) / sends_b) * 100

            diff = abs(rate_a - rate_b)
            winner: Optional[str] = None
            if diff > 5.0:
                winner = "a" if rate_a > rate_b else "b"

            if winner:
                conn.execute(
                    "UPDATE ab_tests SET winner = ?, status = 'complete' WHERE id = ?",
                    (winner, test_id),
                )
                conn.commit()
                logger.info(
                    "A/B test %d winner: variant %s (%.1f%% vs %.1f%%)",
                    test_id, winner, rate_a, rate_b,
                )
            else:
                conn.execute(
                    "UPDATE ab_tests SET status = 'measuring' WHERE id = ?",
                    (test_id,),
                )
                conn.commit()
                logger.info(
                    "A/B test %d: no significant winner yet (%.1f%% vs %.1f%%)",
                    test_id, rate_a, rate_b,
                )

            conn.close()
            return winner
        except Exception:
            logger.exception("Failed to evaluate A/B test %d", test_id)
            conn.close()
            return None

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_test(self, test_id: int) -> Optional[dict]:
        """Return an A/B test with its results joined."""
        conn = self.repo._conn()
        try:
            row = conn.execute(
                "SELECT * FROM ab_tests WHERE id = ?", (test_id,)
            ).fetchone()
            if not row:
                conn.close()
                return None

            test = dict(row)
            results = conn.execute(
                "SELECT * FROM ab_test_results WHERE test_id = ? ORDER BY variant",
                (test_id,),
            ).fetchall()
            test["results"] = [dict(r) for r in results]
            conn.close()
            return test
        except Exception:
            logger.exception("Failed to get A/B test %d", test_id)
            conn.close()
            return None

    def get_tests_for_issue(self, issue_id: int) -> list[dict]:
        """List all A/B tests for a given issue."""
        conn = self.repo._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM ab_tests WHERE issue_id = ? ORDER BY id DESC",
                (issue_id,),
            ).fetchall()
            tests = []
            for row in rows:
                test = dict(row)
                results = conn.execute(
                    "SELECT * FROM ab_test_results WHERE test_id = ? ORDER BY variant",
                    (test["id"],),
                ).fetchall()
                test["results"] = [dict(r) for r in results]
                tests.append(test)
            conn.close()
            return tests
        except Exception:
            logger.exception("Failed to get tests for issue %d", issue_id)
            conn.close()
            return []
