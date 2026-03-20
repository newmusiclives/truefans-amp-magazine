"""Artist profile business logic for the TrueFans directory."""

from __future__ import annotations

import logging
import re
import secrets
from typing import Optional

from weeklyamp.core.models import AppConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


class ProfileManager:
    """Manages artist profile lifecycle: creation, approval, publishing,
    self-service editing, and the public directory."""

    def __init__(self, repo: Repository, config: AppConfig) -> None:
        self.repo = repo
        self.config = config

    def _check_enabled(self) -> bool:
        """Return True if artist profiles feature is enabled, log warning otherwise."""
        if not self.config.artist_profiles.enabled:
            logger.debug("Artist profiles feature is disabled")
            return False
        return True

    # ---- Slug generation ----

    def generate_slug(self, artist_name: str) -> str:
        """Convert an artist name to a URL-safe slug.

        Lowercases, replaces spaces with hyphens, strips special characters,
        and appends -2, -3, etc. if the slug already exists in the database.
        """
        slug = artist_name.lower().strip()
        slug = re.sub(r"[^a-z0-9\s-]", "", slug)
        slug = re.sub(r"[\s]+", "-", slug)
        slug = re.sub(r"-+", "-", slug).strip("-")
        if not slug:
            slug = "artist"

        # Ensure uniqueness
        base_slug = slug
        counter = 1
        while self.repo.get_artist_profile(slug) is not None:
            counter += 1
            slug = f"{base_slug}-{counter}"

        return slug

    # ---- Profile creation ----

    def create_from_submission(self, submission_id: int) -> Optional[int]:
        """Create an artist profile from an artist_submission record.

        Pulls artist_name, email, website, social links, and genre from the
        submission.  Generates a unique slug.  Returns the new profile_id,
        or None if the feature is disabled or the submission is not found.
        """
        if not self._check_enabled():
            return None

        submission = self.repo.get_submission(submission_id)
        if not submission:
            logger.warning("Submission %d not found", submission_id)
            return None

        artist_name = submission.get("artist_name", "Unknown Artist")
        slug = self.generate_slug(artist_name)

        profile_id = self.repo.create_artist_profile(
            slug=slug,
            artist_name=artist_name,
            email=submission.get("artist_email", ""),
            website=submission.get("artist_website", ""),
            social_links_json=submission.get("artist_social", "{}"),
            genres=submission.get("genre", ""),
            submission_id=submission_id,
        )

        logger.info(
            "Created artist profile %d (%s) from submission %d",
            profile_id, slug, submission_id,
        )
        return profile_id

    # ---- Approval / Publishing ----

    def approve_profile(self, profile_id: int) -> bool:
        """Set is_approved=1 on a profile.  Returns False if disabled."""
        if not self._check_enabled():
            return False
        self.repo.update_artist_profile(profile_id, is_approved=1)
        logger.info("Approved artist profile %d", profile_id)
        return True

    def publish_profile(self, profile_id: int) -> bool:
        """Set is_published=1, but only if the profile is already approved.

        Returns True on success, False if disabled or not approved.
        """
        if not self._check_enabled():
            return False

        # Fetch profile to check approval status
        conn = self.repo._conn()
        row = conn.execute(
            "SELECT is_approved FROM artist_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        conn.close()

        if not row:
            logger.warning("Profile %d not found", profile_id)
            return False

        if not row["is_approved"]:
            logger.warning("Cannot publish profile %d — not approved", profile_id)
            return False

        self.repo.update_artist_profile(profile_id, is_published=1)
        logger.info("Published artist profile %d", profile_id)
        return True

    # ---- Self-service token ----

    def generate_self_service_token(self, profile_id: int) -> Optional[str]:
        """Generate a random self-service edit token, store it on the profile,
        and return it.  Returns None if the feature is disabled."""
        if not self._check_enabled():
            return None

        token = secrets.token_urlsafe(32)
        self.repo.update_artist_profile(profile_id, self_service_token=token)
        logger.info("Generated self-service token for profile %d", profile_id)
        return token

    # ---- Public directory ----

    def get_directory(
        self,
        genre_filter: str = "",
        search: str = "",
        limit: int = 50,
    ) -> list[dict]:
        """Get published artist profiles, optionally filtered by genre or search term.

        Returns a list of profile dicts, each augmented with ``follower_count``.
        """
        if not self._check_enabled():
            return []

        conn = self.repo._conn()
        conditions = ["is_published = 1"]
        params: list = []

        if genre_filter:
            conditions.append("LOWER(genres) LIKE ?")
            params.append(f"%{genre_filter.lower()}%")

        if search:
            conditions.append("LOWER(artist_name) LIKE ?")
            params.append(f"%{search.lower()}%")

        where = " AND ".join(conditions)
        params.append(limit)

        rows = conn.execute(
            f"SELECT * FROM artist_profiles WHERE {where} ORDER BY artist_name LIMIT ?",
            params,
        ).fetchall()
        conn.close()

        profiles = [dict(r) for r in rows]

        # Augment each profile with follower count
        for p in profiles:
            p["follower_count"] = self.repo.get_artist_follower_count(p["id"])

        return profiles

    # ---- Profile detail ----

    def get_profile_with_details(self, slug: str) -> Optional[dict]:
        """Get a single profile enriched with follower count, features list,
        and spotify data (if available).  Returns None if disabled or not found."""
        if not self._check_enabled():
            return None

        profile = self.repo.get_artist_profile(slug)
        if not profile:
            return None

        profile["follower_count"] = self.repo.get_artist_follower_count(profile["id"])
        profile["features"] = self.repo.get_artist_features(profile["id"])

        # Spotify data placeholder — if the spotify integration is active and
        # the profile has a spotify_artist_id, downstream code can enrich this.
        profile["spotify_data"] = None
        if self.config.spotify.enabled and profile.get("spotify_artist_id"):
            try:
                from weeklyamp.content.spotify import get_artist_data
                profile["spotify_data"] = get_artist_data(
                    profile["spotify_artist_id"], self.config
                )
            except Exception:
                logger.debug("Spotify lookup failed for %s", slug)

        return profile
