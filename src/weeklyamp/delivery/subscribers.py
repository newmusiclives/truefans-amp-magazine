"""Subscriber sync between Beehiiv and local SQLite."""

from __future__ import annotations

from rich.console import Console

from weeklyamp.core.models import BeehiivConfig
from weeklyamp.db.repository import Repository
from weeklyamp.delivery.beehiiv import BeehiivClient

console = Console()


def sync_subscribers(repo: Repository, config: BeehiivConfig) -> dict[str, int]:
    """Pull all subscribers from Beehiiv and upsert into local DB.

    Returns {"synced": N, "new": N, "total": N}.
    """
    client = BeehiivClient(config)

    try:
        subscribers = client.get_all_subscribers(status="active")
    finally:
        client.close()

    existing_count = repo.get_subscriber_count()
    synced = 0

    for sub in subscribers:
        email = sub.get("email", "")
        if not email:
            continue
        beehiiv_id = sub.get("id", "")
        status = sub.get("status", "active")
        repo.upsert_subscriber(email=email, beehiiv_id=beehiiv_id, status=status)
        synced += 1

    new_count = repo.get_subscriber_count()

    return {
        "synced": synced,
        "new": max(0, new_count - existing_count),
        "total": new_count,
    }
