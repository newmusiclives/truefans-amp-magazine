"""GoHighLevel (GHL) API v2 client for contact management and email campaigns."""

from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from weeklyamp.core.models import GHLConfig

logger = logging.getLogger(__name__)

# GHL API version header required for v2 endpoints
_API_VERSION = "2021-07-28"


class GHLClient:
    """Client for the GoHighLevel API v2."""

    def __init__(self, config: GHLConfig) -> None:
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
                "Version": _API_VERSION,
            },
            timeout=30.0,
        )

    # ---- Contacts ----

    def create_contact(
        self,
        email: str,
        first_name: str = "",
        last_name: str = "",
        tags: list[str] | None = None,
    ) -> dict:
        """Create a contact in GoHighLevel.

        Returns the created contact dict.
        """
        payload: dict = {
            "email": email,
            "locationId": self.config.location_id,
        }
        if first_name:
            payload["firstName"] = first_name
        if last_name:
            payload["lastName"] = last_name
        if tags:
            payload["tags"] = tags

        resp = self._client.post("/contacts/", json=payload)
        resp.raise_for_status()
        return resp.json().get("contact", {})

    def get_contact(self, contact_id: str) -> dict:
        """Get a contact by ID."""
        resp = self._client.get(f"/contacts/{contact_id}")
        resp.raise_for_status()
        return resp.json().get("contact", {})

    def update_contact(self, contact_id: str, **fields) -> dict:
        """Update a contact's fields (tags, name, etc.)."""
        resp = self._client.put(f"/contacts/{contact_id}", json=fields)
        resp.raise_for_status()
        return resp.json().get("contact", {})

    def add_tags(self, contact_id: str, tags: list[str]) -> dict:
        """Add tags to a contact."""
        resp = self._client.post(
            f"/contacts/{contact_id}/tags",
            json={"tags": tags},
        )
        resp.raise_for_status()
        return resp.json()

    def remove_tags(self, contact_id: str, tags: list[str]) -> dict:
        """Remove tags from a contact."""
        resp = self._client.delete(
            f"/contacts/{contact_id}/tags",
            json={"tags": tags},
        )
        resp.raise_for_status()
        return resp.json()

    def search_contacts(
        self,
        query: str = "",
        limit: int = 100,
        start_after: str = "",
    ) -> dict:
        """Search contacts. Returns full response with pagination metadata."""
        params: dict = {
            "locationId": self.config.location_id,
            "limit": limit,
        }
        if query:
            params["query"] = query
        if start_after:
            params["startAfterId"] = start_after

        resp = self._client.get("/contacts/", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_contacts_by_tag(self, tag: str, limit: int = 100) -> list[dict]:
        """Get all contacts with a specific tag.

        Uses search with tag filter and paginates through all results.
        """
        all_contacts: list[dict] = []
        start_after = ""

        while True:
            params: dict = {
                "locationId": self.config.location_id,
                "limit": limit,
                "query": tag,
            }
            if start_after:
                params["startAfterId"] = start_after

            resp = self._client.get("/contacts/", params=params)
            resp.raise_for_status()
            data = resp.json()

            contacts = data.get("contacts", [])
            # Filter to only those that actually have the tag
            tagged = [c for c in contacts if tag in (c.get("tags", []) or [])]
            all_contacts.extend(tagged)

            meta = data.get("meta", {})
            next_id = meta.get("startAfterId") or meta.get("nextPageUrl")
            if not contacts or not next_id:
                break
            start_after = meta.get("startAfterId", "")
            if not start_after:
                break
            # Respect rate limits
            time.sleep(0.5)

        return all_contacts

    def get_all_contacts(self, limit: int = 100) -> list[dict]:
        """Paginate through all contacts in the location."""
        all_contacts: list[dict] = []
        start_after = ""

        while True:
            params: dict = {
                "locationId": self.config.location_id,
                "limit": limit,
            }
            if start_after:
                params["startAfterId"] = start_after

            resp = self._client.get("/contacts/", params=params)
            resp.raise_for_status()
            data = resp.json()

            contacts = data.get("contacts", [])
            if not contacts:
                break
            all_contacts.extend(contacts)

            meta = data.get("meta", {})
            start_after = meta.get("startAfterId", "")
            if not start_after:
                break
            # Respect rate limits
            time.sleep(0.5)

        return all_contacts

    def get_contact_count(self, tag: str = "") -> int:
        """Get count of contacts, optionally filtered by tag."""
        if tag:
            return len(self.get_contacts_by_tag(tag, limit=100))
        data = self.search_contacts(limit=1)
        return data.get("meta", {}).get("total", 0)

    # ---- Email Sending ----

    def send_email(
        self,
        contact_id: str,
        subject: str,
        html_body: str,
        from_email: str = "",
        from_name: str = "",
    ) -> dict:
        """Send a transactional email to a single contact via GHL API.

        Note: For bulk newsletter sends, use SMTPSender instead.
        This is for one-off sends like test emails or confirmations.
        """
        payload: dict = {
            "type": "html",
            "contactId": contact_id,
            "subject": subject,
            "htmlBody": html_body,
        }
        if from_email:
            payload["emailFrom"] = from_email
        if from_name:
            payload["emailFrom"] = f"{from_name} <{from_email}>"

        resp = self._client.post(
            f"/conversations/messages/email",
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    # ---- Workflows ----

    def trigger_workflow(self, workflow_id: str, contact_id: str) -> dict:
        """Trigger a workflow for a contact."""
        resp = self._client.post(
            f"/contacts/{contact_id}/workflow/{workflow_id}",
        )
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self._client.close()
