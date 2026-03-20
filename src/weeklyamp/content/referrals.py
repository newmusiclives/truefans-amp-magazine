"""Referral system for subscriber-driven growth.

Generates unique referral codes, tracks referrals, and injects
personalised referral links into newsletter HTML.  INACTIVE by default
— all operations check ``ReferralConfig.enabled`` before writing.
"""

from __future__ import annotations

import logging
import random
import string
from typing import Optional

from weeklyamp.core.models import ReferralConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


class ReferralManager:
    """Manage referral codes, tracking, and link injection."""

    def __init__(self, repo: Repository, config: ReferralConfig) -> None:
        self.repo = repo
        self.config = config

    @property
    def _enabled(self) -> bool:
        return self.config.enabled

    # ------------------------------------------------------------------
    # Code management
    # ------------------------------------------------------------------

    def generate_code(self, subscriber_id: int) -> Optional[str]:
        """Create a unique referral code and persist it.

        Returns the code string, or ``None`` if disabled.
        """
        if not self._enabled:
            logger.debug("Referrals disabled — skipping generate_code")
            return None

        code = self.config.code_prefix + "".join(
            random.choices(string.ascii_uppercase + string.digits, k=6)
        )

        conn = self.repo._conn()
        try:
            conn.execute(
                """INSERT INTO referral_codes
                   (subscriber_id, code, referral_count)
                   VALUES (?, ?, 0)""",
                (subscriber_id, code),
            )
            conn.commit()
            conn.close()
            logger.info("Generated referral code %s for subscriber %d", code, subscriber_id)
            return code
        except Exception:
            logger.exception("Failed to generate referral code for subscriber %d", subscriber_id)
            conn.close()
            return None

    def get_or_create_code(self, subscriber_id: int) -> Optional[str]:
        """Return existing referral code or generate a new one."""
        if not self._enabled:
            return None

        conn = self.repo._conn()
        try:
            row = conn.execute(
                "SELECT code FROM referral_codes WHERE subscriber_id = ? LIMIT 1",
                (subscriber_id,),
            ).fetchone()
            conn.close()
            if row:
                return row["code"]
        except Exception:
            logger.exception("Failed to look up referral code for subscriber %d", subscriber_id)
            conn.close()

        return self.generate_code(subscriber_id)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_referral(self, referrer_code: str, referred_email: str) -> bool:
        """Log a referral and increment the referrer's count.

        Returns ``True`` on success, ``False`` otherwise.
        """
        if not self._enabled:
            return False

        conn = self.repo._conn()
        try:
            # Verify the code exists
            row = conn.execute(
                "SELECT id FROM referral_codes WHERE code = ?",
                (referrer_code,),
            ).fetchone()
            if not row:
                logger.warning("Unknown referral code: %s", referrer_code)
                conn.close()
                return False

            referral_code_id = row["id"]

            # Log the referral
            conn.execute(
                """INSERT INTO referral_log
                   (referral_code_id, referred_email)
                   VALUES (?, ?)""",
                (referral_code_id, referred_email),
            )

            # Increment count
            conn.execute(
                "UPDATE referral_codes SET referral_count = referral_count + 1 WHERE id = ?",
                (referral_code_id,),
            )
            conn.commit()
            conn.close()

            logger.info("Recorded referral: code=%s referred=%s", referrer_code, referred_email)
            return True
        except Exception:
            logger.exception("Failed to record referral for code %s", referrer_code)
            conn.close()
            return False

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_referral_stats(self, subscriber_id: int) -> dict:
        """Return referral stats for a subscriber.

        Returns a dict with keys ``code``, ``count``, ``reward_eligible``.
        """
        if not self._enabled:
            return {"code": None, "count": 0, "reward_eligible": False}

        conn = self.repo._conn()
        try:
            row = conn.execute(
                "SELECT code, referral_count FROM referral_codes WHERE subscriber_id = ? LIMIT 1",
                (subscriber_id,),
            ).fetchone()
            conn.close()

            if not row:
                return {"code": None, "count": 0, "reward_eligible": False}

            count = row["referral_count"]
            return {
                "code": row["code"],
                "count": count,
                "reward_eligible": count >= self.config.reward_threshold,
            }
        except Exception:
            logger.exception("Failed to get referral stats for subscriber %d", subscriber_id)
            conn.close()
            return {"code": None, "count": 0, "reward_eligible": False}

    def get_top_referrers(self, limit: int = 20) -> list[dict]:
        """Return the top referrers by count."""
        if not self._enabled:
            return []

        conn = self.repo._conn()
        try:
            rows = conn.execute(
                """SELECT rc.code, rc.referral_count, rc.subscriber_id,
                          s.email
                   FROM referral_codes rc
                   JOIN subscribers s ON rc.subscriber_id = s.id
                   ORDER BY rc.referral_count DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            logger.exception("Failed to get top referrers")
            conn.close()
            return []

    # ------------------------------------------------------------------
    # Link injection
    # ------------------------------------------------------------------

    def inject_referral_link(
        self, html_body: str, subscriber_id: int, site_domain: str
    ) -> str:
        """Replace ``{{ referral_url }}`` with a personalised referral link.

        Returns the modified HTML body.  If the feature is disabled or the
        subscriber has no code, the placeholder is removed silently.
        """
        placeholder = "{{ referral_url }}"
        if placeholder not in html_body:
            return html_body

        code = self.get_or_create_code(subscriber_id) if self._enabled else None
        if code:
            url = f"{site_domain.rstrip('/')}/refer?code={code}"
        else:
            url = site_domain

        return html_body.replace(placeholder, url)
