"""Notification manager — centralized notification system for all platform events."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


class NotificationManager:
    """Create, query, and manage notifications across the platform."""

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def notify(
        self,
        title: str,
        message: str,
        notification_type: str = "info",
        category: str = "system",
        action_url: str = "",
        entity_type: str = "",
        entity_id: int = 0,
    ) -> int:
        """Create a notification record.

        notification_type: info, success, warning, error
        category: system, subscriber, revenue, content, sponsor, licensee, artist
        """
        conn = self.repo._conn()
        cur = conn.execute(
            """INSERT INTO notifications (title, message, notification_type, category, action_url, entity_type, entity_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (title, message, notification_type, category, action_url, entity_type, entity_id),
        )
        conn.commit()
        notif_id = cur.lastrowid
        conn.close()
        return notif_id

    def get_recent(self, limit: int = 50, category: str = "") -> list[dict]:
        """Get recent notifications, optionally filtered by category."""
        conn = self.repo._conn()
        if category:
            rows = conn.execute(
                "SELECT * FROM notifications WHERE category = ? ORDER BY created_at DESC LIMIT ?",
                (category, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM notifications ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def mark_read(self, notification_id: int) -> None:
        """Mark a notification as read."""
        conn = self.repo._conn()
        conn.execute(
            "UPDATE notifications SET is_read = 1, read_at = CURRENT_TIMESTAMP WHERE id = ?",
            (notification_id,),
        )
        conn.commit()
        conn.close()

    def get_unread_count(self) -> int:
        """Get count of unread notifications."""
        conn = self.repo._conn()
        row = conn.execute("SELECT COUNT(*) as c FROM notifications WHERE is_read = 0").fetchone()
        conn.close()
        return row["c"] if row else 0

    # ---- Convenience Methods for Common Events ----

    def notify_new_subscriber(self, email: str, edition: str = "") -> int:
        edition_text = f" ({edition} edition)" if edition else ""
        return self.notify(
            title="New Subscriber",
            message=f"{email} subscribed{edition_text}",
            notification_type="success",
            category="subscriber",
            action_url="/admin/subscribers",
        )

    def notify_subscriber_milestone(self, count: int) -> int:
        return self.notify(
            title=f"Subscriber Milestone: {count:,}",
            message=f"You've reached {count:,} subscribers!",
            notification_type="success",
            category="subscriber",
        )

    def notify_revenue_event(self, event_type: str, amount_cents: int, description: str = "") -> int:
        amount_str = f"${amount_cents / 100:.2f}"
        return self.notify(
            title=f"Revenue: {event_type}",
            message=f"{amount_str} — {description}" if description else amount_str,
            notification_type="success",
            category="revenue",
            action_url="/revenue/",
        )

    def notify_sponsor_booking(self, sponsor_name: str, edition: str = "") -> int:
        return self.notify(
            title="Sponsor Booked",
            message=f"{sponsor_name} booked a sponsor slot" + (f" ({edition})" if edition else ""),
            notification_type="success",
            category="sponsor",
            action_url="/admin/sponsors",
        )

    def notify_issue_published(self, issue_number: int, edition: str = "") -> int:
        return self.notify(
            title="Issue Published",
            message=f"Issue #{issue_number}" + (f" ({edition})" if edition else "") + " has been published",
            notification_type="info",
            category="content",
        )

    def notify_licensee_activated(self, company_name: str, city: str = "") -> int:
        return self.notify(
            title="New Licensee Activated",
            message=f"{company_name}" + (f" — {city}" if city else ""),
            notification_type="success",
            category="licensee",
            action_url="/admin/licensing/",
        )

    def notify_artist_newsletter_signup(self, artist_name: str) -> int:
        return self.notify(
            title="Artist Newsletter Signup",
            message=f"{artist_name} signed up for an artist newsletter",
            notification_type="info",
            category="artist",
            action_url="/admin/artist-newsletters",
        )

    def notify_system_error(self, title: str, message: str) -> int:
        return self.notify(
            title=title,
            message=message,
            notification_type="error",
            category="system",
        )
