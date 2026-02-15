"""Beehiiv API v2 client for publishing and subscriber management."""

from __future__ import annotations

from typing import Optional

import httpx

from weeklyamp.core.models import BeehiivConfig


class BeehiivClient:
    """Client for the Beehiiv API v2."""

    def __init__(self, config: BeehiivConfig) -> None:
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def _pub_url(self, path: str) -> str:
        return f"/publications/{self.config.publication_id}{path}"

    # ---- Posts ----

    def create_post(
        self,
        title: str,
        html_content: str,
        subtitle: str = "",
        send: bool = False,
    ) -> dict:
        """Create a new post (email/web).

        Args:
            title: Post title
            html_content: Full HTML content
            subtitle: Optional subtitle
            send: If True, send immediately; otherwise save as draft
        """
        payload: dict = {
            "title": title,
            "subtitle": subtitle,
            "content": html_content,
            "content_type": "html",
            "status": "confirmed" if send else "draft",
        }

        resp = self._client.post(self._pub_url("/posts"), json=payload)
        resp.raise_for_status()
        return resp.json().get("data", {})

    def get_post(self, post_id: str) -> dict:
        """Get a post by ID."""
        resp = self._client.get(self._pub_url(f"/posts/{post_id}"))
        resp.raise_for_status()
        return resp.json().get("data", {})

    def list_posts(self, limit: int = 10) -> list[dict]:
        """List recent posts."""
        resp = self._client.get(
            self._pub_url("/posts"),
            params={"limit": limit, "order_by": "publish_date", "direction": "desc"},
        )
        resp.raise_for_status()
        return resp.json().get("data", [])

    # ---- Subscribers ----

    def list_subscribers(
        self,
        status: str = "active",
        limit: int = 100,
        page: Optional[int] = None,
    ) -> dict:
        """List subscribers. Returns full response with pagination."""
        params: dict = {"status": status, "limit": limit}
        if page:
            params["page"] = page
        resp = self._client.get(self._pub_url("/subscriptions"), params=params)
        resp.raise_for_status()
        return resp.json()

    def get_subscriber_count(self) -> int:
        """Get total active subscriber count."""
        data = self.list_subscribers(limit=1)
        return data.get("total_results", 0)

    def get_all_subscribers(self, status: str = "active") -> list[dict]:
        """Paginate through all subscribers."""
        all_subs: list[dict] = []
        page = 1
        while True:
            data = self.list_subscribers(status=status, limit=100, page=page)
            subs = data.get("data", [])
            if not subs:
                break
            all_subs.extend(subs)
            total = data.get("total_results", 0)
            if len(all_subs) >= total:
                break
            page += 1
        return all_subs

    # ---- Stats ----

    def get_post_stats(self, post_id: str) -> dict:
        """Get engagement stats for a post."""
        resp = self._client.get(self._pub_url(f"/posts/{post_id}/stats"))
        resp.raise_for_status()
        return resp.json().get("data", {})

    def close(self) -> None:
        self._client.close()
