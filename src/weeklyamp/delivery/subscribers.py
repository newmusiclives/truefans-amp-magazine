"""Subscriber sync between GoHighLevel and local database."""

from __future__ import annotations

from rich.console import Console

from weeklyamp.core.models import GHLConfig
from weeklyamp.db.repository import Repository
from weeklyamp.delivery.ghl import GHLClient

console = Console()


def sync_subscribers(repo: Repository, config: GHLConfig) -> dict[str, int]:
    """Pull all contacts from GoHighLevel and upsert into local DB.

    Contacts are filtered by edition tags to identify newsletter subscribers.
    Returns {"synced": N, "new": N, "total": N}.
    """
    client = GHLClient(config)

    try:
        contacts = client.get_all_contacts()
    finally:
        client.close()

    # Collect all edition tag values for filtering
    edition_tag_values = set(config.edition_tags.values())

    existing_count = repo.get_subscriber_count()
    synced = 0

    for contact in contacts:
        email = contact.get("email", "")
        if not email:
            continue

        # Only sync contacts that have at least one newsletter tag
        contact_tags = contact.get("tags", []) or []
        if not any(tag in edition_tag_values for tag in contact_tags):
            continue

        ghl_contact_id = contact.get("id", "")
        repo.upsert_subscriber(email=email, ghl_contact_id=ghl_contact_id, status="active")
        synced += 1

    new_count = repo.get_subscriber_count()

    return {
        "synced": synced,
        "new": max(0, new_count - existing_count),
        "total": new_count,
    }


def push_subscribers_to_ghl(repo: Repository, config: GHLConfig) -> dict[str, int]:
    """Push local subscribers to GoHighLevel as contacts with edition tags.

    Returns {"pushed": N, "skipped": N, "errors": N}.
    """
    client = GHLClient(config)
    pushed = 0
    skipped = 0
    errors = 0

    try:
        subscribers = repo.get_subscribers("active")
        for sub in subscribers:
            if sub.get("ghl_contact_id"):
                skipped += 1
                continue

            # Determine edition tags from subscriber_editions
            tags = list(config.edition_tags.values())  # Default: all editions

            try:
                result = client.create_contact(
                    email=sub["email"],
                    first_name=sub.get("first_name", ""),
                    tags=tags,
                )
                ghl_id = result.get("id", "")
                if ghl_id:
                    repo.update_subscriber_ghl_id(sub["id"], ghl_id)
                pushed += 1
            except Exception:
                errors += 1
    finally:
        client.close()

    return {"pushed": pushed, "skipped": skipped, "errors": errors}
