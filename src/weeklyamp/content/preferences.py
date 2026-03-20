"""Subscriber preference center logic.

Allows subscribers to manage their content frequency, send-time
preferences, edition subscriptions, and interest tags through a
token-authenticated preference center.
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Optional

from weeklyamp.core.models import AppConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)

# Default preferences applied when a subscriber has no saved preferences.
_DEFAULT_PREFERENCES: dict = {
    "content_frequency": "all",
    "preferred_send_hour": 9,
    "timezone": "America/New_York",
    "interests": "",
}


class PreferenceManager:
    """Manage subscriber preferences and preference-center tokens."""

    def __init__(self, repo: Repository, config: AppConfig) -> None:
        self.repo = repo
        self.config = config

    # ------------------------------------------------------------------
    # Preferences CRUD
    # ------------------------------------------------------------------

    def get_preferences(self, subscriber_id: int) -> dict:
        """Fetch preferences for *subscriber_id*.

        Returns a dict with sensible defaults when no row exists yet.
        """
        conn = self.repo._conn()
        row = conn.execute(
            "SELECT * FROM subscriber_preferences WHERE subscriber_id = ?",
            (subscriber_id,),
        ).fetchone()
        conn.close()

        if row:
            return dict(row)

        # Return defaults keyed to this subscriber
        return {
            "subscriber_id": subscriber_id,
            **_DEFAULT_PREFERENCES,
        }

    def update_preferences(
        self,
        subscriber_id: int,
        content_frequency: str = "all",
        preferred_send_hour: int = 9,
        timezone: str = "America/New_York",
        interests: str = "",
    ) -> None:
        """Upsert subscriber preferences."""
        conn = self.repo._conn()
        conn.execute(
            """INSERT INTO subscriber_preferences
                   (subscriber_id, content_frequency, preferred_send_hour, timezone, interests)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(subscriber_id) DO UPDATE SET
                   content_frequency = excluded.content_frequency,
                   preferred_send_hour = excluded.preferred_send_hour,
                   timezone = excluded.timezone,
                   interests = excluded.interests,
                   updated_at = CURRENT_TIMESTAMP""",
            (subscriber_id, content_frequency, preferred_send_hour, timezone, interests),
        )
        conn.commit()
        conn.close()
        logger.info("Updated preferences for subscriber %s", subscriber_id)

    # ------------------------------------------------------------------
    # Subscriber profile (combined view)
    # ------------------------------------------------------------------

    def get_subscriber_profile(self, email: str) -> Optional[dict]:
        """Return a combined profile: subscriber info + editions + preferences + referral code."""
        subscriber = self.repo.get_subscriber_by_email(email)
        if not subscriber:
            return None

        sub_id = subscriber["id"]

        # Editions subscribed
        conn = self.repo._conn()
        edition_rows = conn.execute(
            """SELECT ne.slug, ne.name, se.send_days
               FROM subscriber_editions se
               JOIN newsletter_editions ne ON se.edition_id = ne.id
               WHERE se.subscriber_id = ?""",
            (sub_id,),
        ).fetchall()
        conn.close()

        editions = [dict(r) for r in edition_rows]
        preferences = self.get_preferences(sub_id)

        # Referral code (deterministic from subscriber id + email)
        referral_code = self._generate_referral_code(sub_id, email)

        return {
            "subscriber": subscriber,
            "editions": editions,
            "preferences": preferences,
            "referral_code": referral_code,
        }

    # ------------------------------------------------------------------
    # Edition management
    # ------------------------------------------------------------------

    def update_editions(
        self,
        subscriber_id: int,
        edition_slugs: list[str],
        edition_days: Optional[dict[str, list[str]]] = None,
    ) -> None:
        """Update which editions a subscriber receives.

        Delegates to the Repository's ``subscribe_to_editions`` pattern
        after looking up the subscriber's email.
        """
        conn = self.repo._conn()
        row = conn.execute(
            "SELECT email FROM subscribers WHERE id = ?", (subscriber_id,)
        ).fetchone()
        conn.close()

        if not row:
            logger.warning("Subscriber %s not found for edition update", subscriber_id)
            return

        email = row["email"]
        self.repo.subscribe_to_editions(
            email=email,
            edition_slugs=edition_slugs,
            edition_days=edition_days,
        )
        logger.info(
            "Updated editions for subscriber %s: %s", subscriber_id, edition_slugs
        )

    # ------------------------------------------------------------------
    # Token generation / validation (itsdangerous)
    # ------------------------------------------------------------------

    def generate_preference_token(self, subscriber_id: int) -> str:
        """Create a signed, time-limited token for the preference center URL."""
        from itsdangerous import URLSafeTimedSerializer

        secret = os.environ.get("WEEKLYAMP_SECRET_KEY", "dev-secret")
        s = URLSafeTimedSerializer(secret)
        return s.dumps(subscriber_id, salt="preference-center")

    def validate_preference_token(
        self, token: str, max_age: int = 86400
    ) -> Optional[int]:
        """Validate *token* and return the subscriber_id, or ``None`` on failure."""
        from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

        secret = os.environ.get("WEEKLYAMP_SECRET_KEY", "dev-secret")
        s = URLSafeTimedSerializer(secret)
        try:
            subscriber_id: int = s.loads(
                token, salt="preference-center", max_age=max_age
            )
            return subscriber_id
        except (BadSignature, SignatureExpired):
            logger.warning("Invalid or expired preference token")
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_referral_code(subscriber_id: int, email: str) -> str:
        """Deterministic referral code derived from subscriber id + email."""
        raw = f"{subscriber_id}:{email}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:8].upper()
        return f"TF-{digest}"
