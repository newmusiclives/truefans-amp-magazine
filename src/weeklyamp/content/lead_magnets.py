"""Lead magnet business logic — creation, download gating, auto-subscribe."""

from __future__ import annotations

import re
import unicodedata
from typing import Optional


class LeadMagnetManager:
    """Manages lead magnets: create, list, gate downloads, auto-subscribe."""

    def __init__(self, repo, config) -> None:
        self.repo = repo
        self.config = config

    @staticmethod
    def generate_slug(title: str) -> str:
        """Generate a URL-safe slug from a title string."""
        slug = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
        slug = slug.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[-\s]+", "-", slug)
        return slug.strip("-")

    def create_magnet(
        self,
        title: str,
        slug: str,
        description: str,
        edition_slug: str,
        file_url: str,
        cover_image_url: str = "",
    ) -> int:
        """Create a new lead magnet. Returns the new row ID."""
        if not slug:
            slug = self.generate_slug(title)
        return self.repo.create_lead_magnet(
            title=title,
            slug=slug,
            description=description,
            edition_slug=edition_slug,
            file_url=file_url,
            cover_image_url=cover_image_url,
        )

    def get_active_magnets(self, edition_slug: str = "") -> list[dict]:
        """List active lead magnets, optionally filtered by edition."""
        magnets = self.repo.get_lead_magnets(active_only=True)
        if edition_slug:
            magnets = [m for m in magnets if m.get("edition_slug") == edition_slug]
        return magnets

    def get_all_magnets(self) -> list[dict]:
        """List all lead magnets (admin view)."""
        return self.repo.get_lead_magnets(active_only=False)

    def get_magnet_by_slug(self, slug: str) -> Optional[dict]:
        """Get a single lead magnet by its slug."""
        return self.repo.get_lead_magnet(slug)

    def record_download(self, slug: str, email: str) -> Optional[str]:
        """Record a download, auto-subscribe the user if not subscribed.

        Returns the file_url on success, None if magnet not found.
        """
        magnet = self.get_magnet_by_slug(slug)
        if not magnet:
            return None

        # Record download via repo
        self.repo.record_lead_magnet_download(
            lead_magnet_id=magnet["id"],
            email=email,
        )

        # Auto-subscribe if not already subscribed
        edition_slug = magnet.get("edition_slug", "")
        if edition_slug:
            try:
                self.repo.subscribe_to_editions(
                    email=email,
                    edition_slugs=[edition_slug],
                    source_channel="lead_magnet",
                )
            except Exception:
                pass  # Best-effort subscribe

        return magnet["file_url"]
