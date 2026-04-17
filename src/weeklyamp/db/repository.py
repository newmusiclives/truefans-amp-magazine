"""CRUD operations for all WEEKLYAMP database tables."""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime
from typing import Optional

from weeklyamp.core.database import get_connection

logger = logging.getLogger(__name__)


class _PgCursorAdapter:
    """Wraps a PgCursor/dict result to provide ``lastrowid`` like sqlite3."""

    def __init__(self, cur, lastrowid: Optional[int] = None) -> None:
        self._cur = cur
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()


class _PgConnAdapter:
    """Wraps a PgConnection so that SQLite-style ``?`` placeholders are
    transparently converted to ``%s`` before execution.  This lets every
    Repository method keep its original SQL strings unchanged.

    For INSERT statements, automatically appends ``RETURNING id`` so that
    ``cursor.lastrowid`` works as expected.
    """

    def __init__(self, conn) -> None:
        self._conn = conn

    @staticmethod
    def _convert(sql: str) -> str:
        return sql.replace("?", "%s")

    def execute(self, sql: str, params=None):
        converted = self._convert(sql)
        stripped = converted.strip()
        is_insert = stripped.upper().startswith("INSERT")
        # Auto-append RETURNING id for INSERT statements that don't already have it
        if is_insert and "RETURNING" not in stripped.upper():
            converted = converted.rstrip().rstrip(";") + " RETURNING id"
        raw_cur = self._conn.execute(converted, params)
        # Extract lastrowid from the RETURNING clause
        lastrowid = None
        if is_insert:
            try:
                row = raw_cur.fetchone()
                if row and "id" in row:
                    lastrowid = row["id"]
            except Exception:
                pass
        return _PgCursorAdapter(raw_cur, lastrowid)

    def executescript(self, sql: str) -> None:
        self._conn.executescript(sql)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


class Repository:
    """Central data-access layer for the WEEKLYAMP database.

    Supports both SQLite and PostgreSQL backends.  The backend is chosen
    at construction time via the ``backend`` parameter or the
    ``WEEKLYAMP_DB_BACKEND`` environment variable.
    """

    # Column whitelist for generic update methods — prevents SQL injection
    # via f-string column name interpolation.
    _ALLOWED_COLUMNS: dict[str, set[str]] = {
        "section_definitions": {
            "display_name", "sort_order", "is_active", "section_type",
            "target_word_count", "word_count_label", "prompt_template",
            "category", "series_type", "series_length", "series_current",
            "description", "suggested_reason", "last_used_issue_id", "suggested_at",
        },
        "sponsor_blocks": {
            "position", "sponsor_name", "headline", "body_html",
            "cta_url", "cta_text", "image_url", "is_active",
            "edition_slug", "edition_number",
        },
        "sponsors": {
            "name", "contact_name", "contact_email", "website", "notes", "is_active",
        },
        "ai_agents": {
            "agent_type", "name", "persona", "system_prompt",
            "autonomy_level", "config_json", "is_active",
        },
        "guest_contacts": {
            "name", "email", "organization", "role", "category", "website", "notes",
        },
        "guest_articles": {
            "contact_id", "title", "author_name", "author_bio", "original_url",
            "content_full", "content_summary", "display_mode", "permission_state",
            "target_issue_id", "target_section_slug", "draft_id",
        },
        "artist_submissions": {
            "artist_name", "artist_email", "artist_website", "artist_social",
            "submission_type", "title", "description", "release_date", "genre",
            "links_json", "attachments_json", "review_state",
            "target_issue_id", "target_section_slug", "draft_id", "api_source",
        },
        "editorial_calendar": {
            "issue_id", "planned_date", "theme", "notes",
            "section_assignments", "agent_assignments", "status",
        },
        "social_posts": {
            "platform", "content", "issue_id", "status",
            "scheduled_at", "posted_at", "agent_task_id",
        },
        "webhooks": {
            "name", "url", "direction", "event_types", "secret", "is_active",
        },
        "reusable_blocks": {
            "name", "html_content", "plain_text", "block_type", "is_active",
        },
        "ab_tests": {
            "status", "winner", "started_at", "completed_at",
        },
        "scheduled_sends": {
            "status", "error_message", "sent_at",
        },
    }

    @staticmethod
    def _validate_columns(table: str, columns: dict) -> None:
        """Raise ValueError if any column names are not in the whitelist."""
        allowed = Repository._ALLOWED_COLUMNS.get(table, set())
        bad = set(columns.keys()) - allowed
        if bad:
            raise ValueError(f"Invalid columns for {table}: {bad}")

    def __init__(self, db_path: str = "", database_url: str = "", backend: str = "") -> None:
        self.backend = backend or os.getenv("WEEKLYAMP_DB_BACKEND", "sqlite").lower()
        self.db_path = db_path
        self.database_url = database_url

    @property
    def _is_pg(self) -> bool:
        return self.backend == "postgres"

    def _conn(self):
        raw = get_connection(self.db_path, self.database_url, self.backend)
        if self._is_pg:
            return _PgConnAdapter(raw)
        return raw

    # NOTE: Placeholder conversion (? -> %s) and RETURNING id for
    # PostgreSQL are handled automatically by _PgConnAdapter, so all
    # Repository methods can use standard SQLite-style ? placeholders.

    # ---- Issues ----

    def create_issue(self, issue_number: int, title: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO issues (issue_number, title) VALUES (?, ?)",
            (issue_number, title),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_current_issue(self) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM issues ORDER BY issue_number DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_issue(self, issue_id: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_issue_status(self, issue_id: int, status: str) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE issues SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, issue_id),
        )
        conn.commit()
        conn.close()

    def get_next_issue_number(self) -> int:
        conn = self._conn()
        row = conn.execute("SELECT MAX(issue_number) as n FROM issues").fetchone()
        conn.close()
        return (row["n"] or 0) + 1

    def create_issue_with_schedule(
        self, issue_number: int, title: str = "", week_id: str = "",
        send_day: str = "", issue_template: str = "", edition_slug: str = "",
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO issues (issue_number, title, week_id, send_day, edition_slug, issue_template)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (issue_number, title, week_id, send_day, edition_slug, issue_template),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_issues_for_week(self, week_id: str) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM issues WHERE week_id = ? ORDER BY send_day", (week_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_upcoming_issues(self, limit: int = 10) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT * FROM issues WHERE status NOT IN ('published')
               ORDER BY issue_number DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_published_issues(self, limit: int = 20) -> list[dict]:
        """Return issues with status='published', newest first."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM issues WHERE status = 'published' ORDER BY publish_date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Section Definitions ----

    def get_active_sections(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM section_definitions WHERE is_active = 1 ORDER BY sort_order"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_all_sections(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM section_definitions ORDER BY sort_order"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_section(self, slug: str) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM section_definitions WHERE slug = ?", (slug,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_section(self, slug: str, **kwargs) -> None:
        if not kwargs:
            return
        self._validate_columns("section_definitions", kwargs)
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [slug]
        conn = self._conn()
        conn.execute(f"UPDATE section_definitions SET {sets} WHERE slug = ?", vals)
        conn.commit()
        conn.close()

    def add_section(self, slug: str, display_name: str, sort_order: int) -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO section_definitions (slug, display_name, sort_order) VALUES (?, ?, ?)",
            (slug, display_name, sort_order),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def update_section_word_count(self, slug: str, word_count_label: str, target_word_count: int) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE section_definitions SET word_count_label = ?, target_word_count = ? WHERE slug = ?",
            (word_count_label, target_word_count, slug),
        )
        conn.commit()
        conn.close()

    def get_sections_by_type(self, section_type: str) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM section_definitions WHERE section_type = ? AND is_active = 1 ORDER BY sort_order",
            (section_type,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_suggested_sections(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM section_definitions WHERE section_type = 'suggested' ORDER BY suggested_at DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def accept_suggested_section(self, slug: str, as_type: str = "rotating") -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE section_definitions SET section_type = ?, is_active = 1 WHERE slug = ?",
            (as_type, slug),
        )
        conn.commit()
        conn.close()

    def dismiss_suggested_section(self, slug: str) -> None:
        conn = self._conn()
        conn.execute(
            "DELETE FROM section_definitions WHERE slug = ? AND section_type = 'suggested'",
            (slug,),
        )
        conn.commit()
        conn.close()

    # ---- Rotation Log ----

    def log_rotation(self, issue_id: int, slug: str, was_included: bool = True) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO section_rotation_log (issue_id, section_slug, was_included) VALUES (?, ?, ?)",
            (issue_id, slug, int(was_included)),
        )
        conn.commit()
        conn.close()

    def get_rotation_history(self, slug: str, limit: int = 10) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT * FROM section_rotation_log WHERE section_slug = ?
               ORDER BY created_at DESC LIMIT ?""",
            (slug, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_recent_rotation_log(self, n: int = 4) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT * FROM section_rotation_log
               ORDER BY created_at DESC LIMIT ?""",
            (n * 20,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Sources ----

    def get_active_sources(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM sources WHERE is_active = 1"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def add_source(self, name: str, source_type: str, url: str, target_sections: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO sources (name, source_type, url, target_sections) VALUES (?, ?, ?, ?)",
            (name, source_type, url, target_sections),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def update_source_fetched(self, source_id: int) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE sources SET last_fetched = CURRENT_TIMESTAMP WHERE id = ?",
            (source_id,),
        )
        conn.commit()
        conn.close()

    # ---- Raw Content ----

    def add_raw_content(
        self,
        source_id: Optional[int],
        title: str,
        url: str,
        author: str = "",
        summary: str = "",
        full_text: str = "",
        published_at: Optional[str] = None,
        relevance_score: float = 0.0,
        matched_sections: str = "",
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO raw_content
               (source_id, title, url, author, summary, full_text, published_at,
                relevance_score, matched_sections)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (source_id, title, url, author, summary, full_text, published_at,
             relevance_score, matched_sections),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_unused_content(self, section_slug: Optional[str] = None, limit: int = 20) -> list[dict]:
        conn = self._conn()
        if section_slug:
            rows = conn.execute(
                """SELECT * FROM raw_content
                   WHERE is_used = 0 AND matched_sections LIKE ?
                   ORDER BY relevance_score DESC LIMIT ?""",
                (f"%{section_slug}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM raw_content WHERE is_used = 0 ORDER BY relevance_score DESC LIMIT ?",
                (limit,),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def mark_content_used(self, content_id: int) -> None:
        conn = self._conn()
        conn.execute("UPDATE raw_content SET is_used = 1 WHERE id = ?", (content_id,))
        conn.commit()
        conn.close()

    def content_url_exists(self, url: str) -> bool:
        conn = self._conn()
        row = conn.execute("SELECT 1 FROM raw_content WHERE url = ?", (url,)).fetchone()
        conn.close()
        return row is not None

    # ---- Editorial Inputs ----

    def add_editorial_input(
        self, issue_id: int, section_slug: str, topic: str, notes: str = "", reference_urls: str = ""
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO editorial_inputs (issue_id, section_slug, topic, notes, reference_urls)
               VALUES (?, ?, ?, ?, ?)""",
            (issue_id, section_slug, topic, notes, reference_urls),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_editorial_inputs(self, issue_id: int, section_slug: Optional[str] = None) -> list[dict]:
        conn = self._conn()
        if section_slug:
            rows = conn.execute(
                "SELECT * FROM editorial_inputs WHERE issue_id = ? AND section_slug = ?",
                (issue_id, section_slug),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM editorial_inputs WHERE issue_id = ?", (issue_id,)
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Drafts ----

    def create_draft(
        self,
        issue_id: int,
        section_slug: str,
        content: str,
        ai_model: str = "",
        prompt_used: str = "",
    ) -> int:
        conn = self._conn()
        # Get next version for this issue/section
        row = conn.execute(
            "SELECT MAX(version) as v FROM drafts WHERE issue_id = ? AND section_slug = ?",
            (issue_id, section_slug),
        ).fetchone()
        version = (row["v"] or 0) + 1
        cur = conn.execute(
            """INSERT INTO drafts (issue_id, section_slug, version, content, ai_model, prompt_used)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (issue_id, section_slug, version, content, ai_model, prompt_used),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_latest_draft(self, issue_id: int, section_slug: str) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            """SELECT * FROM drafts
               WHERE issue_id = ? AND section_slug = ?
               ORDER BY version DESC LIMIT 1""",
            (issue_id, section_slug),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_drafts_for_issue(self, issue_id: int) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT d.* FROM drafts d
               INNER JOIN (
                   SELECT section_slug, MAX(version) as max_v
                   FROM drafts WHERE issue_id = ?
                   GROUP BY section_slug
               ) latest ON d.section_slug = latest.section_slug AND d.version = latest.max_v
               WHERE d.issue_id = ?
               ORDER BY d.section_slug""",
            (issue_id, issue_id),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_draft_status(self, draft_id: int, status: str, reviewer_notes: str = "") -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE drafts SET status = ?, reviewer_notes = ? WHERE id = ?",
            (status, reviewer_notes, draft_id),
        )
        conn.commit()
        conn.close()

    def update_draft_content(self, draft_id: int, content: str) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE drafts SET content = ?, status = 'revised' WHERE id = ?",
            (content, draft_id),
        )
        conn.commit()
        conn.close()

    # ---- Assembled Issues ----

    def save_assembled(self, issue_id: int, html_content: str, plain_text: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO assembled_issues (issue_id, html_content, plain_text)
               VALUES (?, ?, ?)""",
            (issue_id, html_content, plain_text),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_assembled(self, issue_id: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM assembled_issues WHERE issue_id = ? ORDER BY id DESC LIMIT 1",
            (issue_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_assembled_ghl(self, assembled_id: int, campaign_id: str) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE assembled_issues SET ghl_campaign_id = ?, published_at = CURRENT_TIMESTAMP WHERE id = ?",
            (campaign_id, assembled_id),
        )
        conn.commit()
        conn.close()

    # ---- Subscribers ----

    def upsert_subscriber(self, email: str, ghl_contact_id: str = "", status: str = "active") -> None:
        conn = self._conn()
        conn.execute(
            """INSERT INTO subscribers (email, ghl_contact_id, status, synced_at)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(email) DO UPDATE SET
                   ghl_contact_id = excluded.ghl_contact_id,
                   status = excluded.status,
                   synced_at = CURRENT_TIMESTAMP""",
            (email, ghl_contact_id, status),
        )
        conn.commit()
        conn.close()

    def update_subscriber_ghl_id(self, subscriber_id: int, ghl_contact_id: str) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE subscribers SET ghl_contact_id = ? WHERE id = ?",
            (ghl_contact_id, subscriber_id),
        )
        conn.commit()
        conn.close()

    def get_subscriber_count(self, edition_slugs: "list[str] | None" = None) -> int:
        """Count active subscribers.

        Pass ``edition_slugs`` to scope the count to subscribers who are
        subscribed to any of the given edition slugs — used by the
        licensee portal so operators see their city's subscribers, not
        the global tenant count.
        """
        conn = self._conn()
        if edition_slugs:
            placeholders = ",".join("?" for _ in edition_slugs)
            sql = (
                "SELECT COUNT(DISTINCT s.id) as c FROM subscribers s "
                "JOIN subscriber_editions se ON se.subscriber_id = s.id "
                "JOIN newsletter_editions ne ON ne.id = se.edition_id "
                f"WHERE s.status = 'active' AND ne.slug IN ({placeholders})"
            )
            row = conn.execute(sql, tuple(edition_slugs)).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) as c FROM subscribers WHERE status = 'active'"
            ).fetchone()
        conn.close()
        return row["c"]

    def get_subscribers(self, status: str = "active") -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM subscribers WHERE status = ?", (status,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_subscribers_for_edition(self, edition_slug: str) -> list[dict]:
        """Return active subscribers who are subscribed to the given edition."""
        conn = self._conn()
        rows = conn.execute(
            """SELECT s.* FROM subscribers s
               JOIN subscriber_editions se ON se.subscriber_id = s.id
               JOIN newsletter_editions ne ON ne.id = se.edition_id
               WHERE s.status = 'active' AND ne.slug = ?""",
            (edition_slug,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Newsletter Editions ----

    def get_editions(self, active_only: bool = True) -> list[dict]:
        conn = self._conn()
        sql = "SELECT * FROM newsletter_editions"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY sort_order"
        rows = conn.execute(sql).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_edition_by_slug(self, slug: str) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM newsletter_editions WHERE slug = ?", (slug,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_edition_sections(self, slug: str, section_slugs: str) -> None:
        """Update the ordered section list for an edition."""
        conn = self._conn()
        conn.execute(
            "UPDATE newsletter_editions SET section_slugs = ? WHERE slug = ?",
            (section_slugs, slug),
        )
        conn.commit()
        conn.close()

    def subscribe_to_editions(
        self,
        email: str,
        edition_slugs: list[str],
        first_name: str = "",
        source_channel: str = "website",
        edition_days: Optional[dict[str, list[str]]] = None,
    ) -> int:
        """Upsert subscriber and link to editions. Returns subscriber id.

        Args:
            edition_days: optional mapping of edition slug to list of day names,
                e.g. {"fan": ["monday", "saturday"]}. Defaults to all 3 days.
        """
        conn = self._conn()
        conn.execute(
            """INSERT INTO subscribers (email, first_name, source_channel, status, subscribed_at)
               VALUES (?, ?, ?, 'active', CURRENT_TIMESTAMP)
               ON CONFLICT(email) DO UPDATE SET
                   first_name = CASE WHEN excluded.first_name != '' THEN excluded.first_name ELSE subscribers.first_name END,
                   source_channel = CASE WHEN excluded.source_channel != '' THEN excluded.source_channel ELSE subscribers.source_channel END,
                   status = 'active',
                   synced_at = CURRENT_TIMESTAMP""",
            (email, first_name, source_channel),
        )
        row = conn.execute("SELECT id FROM subscribers WHERE email = ?", (email,)).fetchone()
        sub_id = row["id"]
        default_days = "monday,wednesday,saturday"
        for slug in edition_slugs:
            edition = conn.execute(
                "SELECT id FROM newsletter_editions WHERE slug = ?", (slug,)
            ).fetchone()
            if edition:
                send_days = default_days
                if edition_days and slug in edition_days:
                    send_days = ",".join(edition_days[slug])
                conn.execute(
                    """INSERT INTO subscriber_editions (subscriber_id, edition_id, send_days)
                       VALUES (?, ?, ?)
                       ON CONFLICT(subscriber_id, edition_id) DO UPDATE SET
                           send_days = excluded.send_days""",
                    (sub_id, edition["id"], send_days),
                )
        conn.commit()
        conn.close()
        return sub_id

    def get_edition_subscriber_count(self, edition_id: int) -> int:
        conn = self._conn()
        row = conn.execute(
            "SELECT COUNT(*) as c FROM subscriber_editions WHERE edition_id = ?",
            (edition_id,),
        ).fetchone()
        conn.close()
        return row["c"]

    # ---- Engagement Metrics ----

    def save_engagement(
        self, issue_id: int, ghl_campaign_id: str,
        sends: int = 0, opens: int = 0, clicks: int = 0,
        open_rate: float = 0.0, click_rate: float = 0.0,
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO engagement_metrics
               (issue_id, ghl_campaign_id, sends, opens, clicks, open_rate, click_rate)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (issue_id, ghl_campaign_id, sends, opens, clicks, open_rate, click_rate),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_engagement(self, issue_id: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM engagement_metrics WHERE issue_id = ? ORDER BY id DESC LIMIT 1",
            (issue_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    # ---- Send Schedule ----

    def get_send_schedules(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM send_schedule WHERE is_active = 1 ORDER BY id"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def upsert_send_schedule(self, day_of_week: str, label: str = "", section_slugs: str = "", edition_slug: str = "") -> int:
        conn = self._conn()
        # Check if exists (keyed on day + edition)
        existing = conn.execute(
            "SELECT id FROM send_schedule WHERE day_of_week = ? AND edition_slug = ?",
            (day_of_week, edition_slug),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE send_schedule SET label = ?, section_slugs = ?, is_active = 1 WHERE day_of_week = ? AND edition_slug = ?",
                (label, section_slugs, day_of_week, edition_slug),
            )
            conn.commit()
            row_id = existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO send_schedule (day_of_week, edition_slug, label, section_slugs) VALUES (?, ?, ?, ?)",
                (day_of_week, edition_slug, label, section_slugs),
            )
            conn.commit()
            row_id = cur.lastrowid
        conn.close()
        return row_id

    def delete_send_schedule(self, day_of_week: str, edition_slug: str = "") -> None:
        conn = self._conn()
        conn.execute(
            "DELETE FROM send_schedule WHERE day_of_week = ? AND edition_slug = ?",
            (day_of_week, edition_slug),
        )
        conn.commit()
        conn.close()

    def get_edition_sections(self, edition_slug: str) -> list[dict]:
        """Get active sections that belong to a specific edition."""
        edition = self.get_edition_by_slug(edition_slug)
        if not edition:
            return []
        slugs = [s.strip() for s in edition.get("section_slugs", "").split(",") if s.strip()]
        if not slugs:
            return []
        all_sections = self.get_active_sections()
        section_map = {s["slug"]: s for s in all_sections}
        return [section_map[s] for s in slugs if s in section_map]

    # ---- Sponsor Blocks ----

    def create_sponsor_block(
        self, issue_id: int, position: str = "mid", sponsor_name: str = "",
        headline: str = "", body_html: str = "", cta_url: str = "",
        cta_text: str = "Learn More", image_url: str = "",
        edition_slug: str = "", edition_number: int = 1,
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO sponsor_blocks
               (issue_id, position, sponsor_name, headline, body_html, cta_url, cta_text, image_url,
                edition_slug, edition_number)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (issue_id, position, sponsor_name, headline, body_html, cta_url, cta_text, image_url,
             edition_slug, edition_number),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_sponsor_blocks_for_issue(self, issue_id: int) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM sponsor_blocks WHERE issue_id = ? AND is_active = 1 ORDER BY position",
            (issue_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_sponsor_blocks_for_edition(self, edition_slug: str, edition_number: int) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT * FROM sponsor_blocks
               WHERE edition_slug = ? AND edition_number = ? AND is_active = 1
               ORDER BY position""",
            (edition_slug, edition_number),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_all_sponsor_blocks(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM sponsor_blocks WHERE is_active = 1 ORDER BY edition_slug, edition_number, position"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_sponsor_block(self, block_id: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM sponsor_blocks WHERE id = ?", (block_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_sponsor_block(self, block_id: int, **kwargs) -> None:
        if not kwargs:
            return
        self._validate_columns("sponsor_blocks", kwargs)
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [block_id]
        conn = self._conn()
        conn.execute(f"UPDATE sponsor_blocks SET {sets} WHERE id = ?", vals)
        conn.commit()
        conn.close()

    def delete_sponsor_block(self, block_id: int) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM sponsor_blocks WHERE id = ?", (block_id,))
        conn.commit()
        conn.close()

    # ---- Sponsor Block Events (performance tracking) ----

    def record_sponsor_event(self, block_id: int, event_type: str, subscriber_id: int = 0, ip_address: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO sponsor_block_events (block_id, event_type, subscriber_id, ip_address) VALUES (?, ?, ?, ?)",
            (block_id, event_type, subscriber_id or None, ip_address),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_sponsor_performance(self, limit: int = 50) -> list[dict]:
        # Postgres's strict GROUP BY rejects non-aggregate columns that
        # aren't functionally dependent on the group key — `i.*` isn't
        # dependent on `sb.id` through a LEFT JOIN, so we enumerate
        # every non-aggregate column explicitly.
        conn = self._conn()
        rows = conn.execute(
            """SELECT sb.id as block_id, sb.sponsor_name, sb.position, sb.headline,
                      i.issue_number, i.edition_slug,
                      COUNT(CASE WHEN sbe.event_type = 'impression' THEN 1 END) as impressions,
                      COUNT(CASE WHEN sbe.event_type = 'click' THEN 1 END) as clicks,
                      CASE WHEN COUNT(CASE WHEN sbe.event_type = 'impression' THEN 1 END) > 0
                           THEN ROUND(100.0 * COUNT(CASE WHEN sbe.event_type = 'click' THEN 1 END) / COUNT(CASE WHEN sbe.event_type = 'impression' THEN 1 END), 1)
                           ELSE 0 END as ctr
               FROM sponsor_blocks sb
               LEFT JOIN sponsor_block_events sbe ON sbe.block_id = sb.id
               LEFT JOIN issues i ON i.id = sb.issue_id
               GROUP BY sb.id, sb.sponsor_name, sb.position, sb.headline,
                        i.issue_number, i.edition_slug
               ORDER BY clicks DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Edition Markets ----

    def get_edition_markets(self, edition_slug: str = "") -> list[dict]:
        conn = self._conn()
        if edition_slug:
            rows = conn.execute("SELECT * FROM edition_markets WHERE edition_slug = ? AND is_active = 1 ORDER BY sort_order", (edition_slug,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM edition_markets WHERE is_active = 1 ORDER BY edition_slug, sort_order").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def create_edition_market(self, edition_slug: str, market_slug: str, market_name: str, description: str = "", sort_order: int = 0) -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO edition_markets (edition_slug, market_slug, market_name, description, sort_order) VALUES (?, ?, ?, ?, ?)",
            (edition_slug, market_slug, market_name, description, sort_order),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def toggle_edition_market(self, market_id: int) -> None:
        conn = self._conn()
        conn.execute("UPDATE edition_markets SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END WHERE id = ?", (market_id,))
        conn.commit()
        conn.close()

    # ---- Artist Newsletters ----

    def create_artist_newsletter_waitlist(self, artist_name: str, email: str, website: str = "", social_links: str = "", genre: str = "", fan_count: str = "", message: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO artist_newsletter_waitlist (artist_name, email, website, social_links, genre, fan_count, message) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (artist_name, email, website, social_links, genre, fan_count, message),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_artist_newsletter_waitlist(self, status: str = "", limit: int = 50) -> list[dict]:
        conn = self._conn()
        if status:
            rows = conn.execute("SELECT * FROM artist_newsletter_waitlist WHERE status = ? ORDER BY created_at DESC LIMIT ?", (status, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM artist_newsletter_waitlist ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_waitlist_status(self, entry_id: int, status: str) -> None:
        conn = self._conn()
        conn.execute("UPDATE artist_newsletter_waitlist SET status = ? WHERE id = ?", (status, entry_id))
        conn.commit()
        conn.close()

    # ---- Edition Sponsors (main sponsors per newsletter x edition) ----

    def get_all_edition_sponsors(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM edition_sponsors WHERE is_active = 1 ORDER BY edition_slug, edition_number"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_edition_sponsor(self, edition_slug: str, edition_number: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM edition_sponsors WHERE edition_slug = ? AND edition_number = ?",
            (edition_slug, edition_number),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def set_edition_sponsor(
        self, edition_slug: str, edition_number: int,
        sponsor_name: str = "", logo_url: str = "", tagline: str = "",
        website_url: str = "", notes: str = "", sponsor_id: Optional[int] = None,
    ) -> int:
        conn = self._conn()
        # Upsert: replace existing sponsor for this slot
        conn.execute(
            "DELETE FROM edition_sponsors WHERE edition_slug = ? AND edition_number = ?",
            (edition_slug, edition_number),
        )
        cur = conn.execute(
            """INSERT INTO edition_sponsors
               (edition_slug, edition_number, sponsor_id, sponsor_name, logo_url, tagline, website_url, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (edition_slug, edition_number, sponsor_id, sponsor_name, logo_url, tagline, website_url, notes),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def remove_edition_sponsor(self, edition_slug: str, edition_number: int) -> None:
        conn = self._conn()
        conn.execute(
            "DELETE FROM edition_sponsors WHERE edition_slug = ? AND edition_number = ?",
            (edition_slug, edition_number),
        )
        conn.commit()
        conn.close()

    # ---- Sponsors (CRM) ----

    def create_sponsor(
        self, name: str, contact_name: str = "", contact_email: str = "",
        website: str = "", notes: str = "",
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO sponsors (name, contact_name, contact_email, website, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (name, contact_name, contact_email, website, notes),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_sponsors(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM sponsors WHERE is_active = 1 ORDER BY name"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_sponsor(self, sponsor_id: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM sponsors WHERE id = ?", (sponsor_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_sponsor(self, sponsor_id: int, **kwargs) -> None:
        if not kwargs:
            return
        self._validate_columns("sponsors", kwargs)
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [sponsor_id]
        conn = self._conn()
        conn.execute(f"UPDATE sponsors SET {sets} WHERE id = ?", vals)
        conn.commit()
        conn.close()

    # ---- Sponsor Bookings ----

    def create_booking(
        self, sponsor_id: int, issue_id: Optional[int] = None,
        position: str = "mid", rate_cents: int = 0, notes: str = "",
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO sponsor_bookings (sponsor_id, issue_id, position, rate_cents, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (sponsor_id, issue_id, position, rate_cents, notes),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_bookings_for_issue(self, issue_id: int) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT b.*, s.name as sponsor_name FROM sponsor_bookings b
               JOIN sponsors s ON b.sponsor_id = s.id
               WHERE b.issue_id = ? ORDER BY b.position""",
            (issue_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_bookings_for_sponsor(self, sponsor_id: int) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT b.*, i.issue_number, i.title as issue_title
               FROM sponsor_bookings b
               LEFT JOIN issues i ON b.issue_id = i.id
               WHERE b.sponsor_id = ? ORDER BY b.booked_at DESC""",
            (sponsor_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_booking_status(self, booking_id: int, status: str) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE sponsor_bookings SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, booking_id),
        )
        conn.commit()
        conn.close()

    def get_sponsor_revenue_summary(self) -> dict:
        conn = self._conn()
        row = conn.execute(
            """SELECT
                COUNT(*) as total_bookings,
                COALESCE(SUM(CASE WHEN status = 'paid' THEN rate_cents ELSE 0 END), 0) as paid_cents,
                COALESCE(SUM(CASE WHEN status IN ('booked','confirmed','delivered','invoiced') THEN rate_cents ELSE 0 END), 0) as pipeline_cents,
                COUNT(CASE WHEN status = 'paid' THEN 1 END) as paid_count
               FROM sponsor_bookings"""
        ).fetchone()
        conn.close()
        return dict(row) if row else {"total_bookings": 0, "paid_cents": 0, "pipeline_cents": 0, "paid_count": 0}

    def get_open_slots(self, limit: int = 10) -> list[dict]:
        """Get upcoming issues with available sponsor slots."""
        conn = self._conn()
        rows = conn.execute(
            """SELECT i.*, COUNT(b.id) as booked_count
               FROM issues i
               LEFT JOIN sponsor_bookings b ON i.id = b.issue_id
               WHERE i.status NOT IN ('published')
               GROUP BY i.id
               ORDER BY i.issue_number DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- AI Agents ----

    def create_agent(
        self, agent_type: str, name: str, persona: str = "",
        system_prompt: str = "", autonomy_level: str = "manual",
        config_json: str = "{}",
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO ai_agents (agent_type, name, persona, system_prompt, autonomy_level, config_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (agent_type, name, persona, system_prompt, autonomy_level, config_json),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_agents(self, active_only: bool = True) -> list[dict]:
        conn = self._conn()
        q = "SELECT * FROM ai_agents"
        if active_only:
            q += " WHERE is_active = 1"
        q += " ORDER BY agent_type"
        rows = conn.execute(q).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_agent(self, agent_id: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM ai_agents WHERE id = ?", (agent_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_agent_by_type(self, agent_type: str) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM ai_agents WHERE agent_type = ? AND is_active = 1 LIMIT 1",
            (agent_type,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_agents_by_type(self, agent_type: str) -> list[dict]:
        """Return all active agents of a given type."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM ai_agents WHERE agent_type = ? AND is_active = 1 ORDER BY name",
            (agent_type,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_writer_for_section(self, section_slug: str) -> Optional[dict]:
        """Find the specialist writer whose config_json covers this section."""
        import json as _json
        writers = self.get_agents_by_type("writer")
        for w in writers:
            try:
                cfg = _json.loads(w.get("config_json") or "{}")
            except (ValueError, TypeError):
                continue
            sections = cfg.get("sections", [])
            if section_slug in sections:
                return w
        # Fallback: check by category
        conn = self._conn()
        row = conn.execute(
            "SELECT category FROM section_definitions WHERE slug = ?", (section_slug,)
        ).fetchone()
        conn.close()
        if row:
            cat = row["category"]
            for w in writers:
                try:
                    cfg = _json.loads(w.get("config_json") or "{}")
                except (ValueError, TypeError):
                    continue
                if cat in cfg.get("categories", []):
                    return w
        # Final fallback: first writer
        return writers[0] if writers else None

    def update_agent(self, agent_id: int, **kwargs) -> None:
        if not kwargs:
            return
        self._validate_columns("ai_agents", kwargs)
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [agent_id]
        conn = self._conn()
        conn.execute(f"UPDATE ai_agents SET {sets} WHERE id = ?", vals)
        conn.commit()
        conn.close()

    # ---- Agent Tasks ----

    def create_agent_task(
        self, agent_id: int, task_type: str, priority: int = 5,
        input_json: str = "{}", issue_id: Optional[int] = None,
        section_slug: str = "",
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO agent_tasks (agent_id, task_type, state, priority, input_json, issue_id, section_slug)
               VALUES (?, ?, 'assigned', ?, ?, ?, ?)""",
            (agent_id, task_type, priority, input_json, issue_id, section_slug),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_agent_tasks(self, agent_id: Optional[int] = None, state: Optional[str] = None, limit: int = 50) -> list[dict]:
        conn = self._conn()
        q = "SELECT t.*, a.name as agent_name, a.agent_type FROM agent_tasks t JOIN ai_agents a ON t.agent_id = a.id WHERE 1=1"
        params: list = []
        if agent_id is not None:
            q += " AND t.agent_id = ?"
            params.append(agent_id)
        if state:
            q += " AND t.state = ?"
            params.append(state)
        q += " ORDER BY t.priority ASC, t.created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(q, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_task_state(self, task_id: int, state: str, output_json: str = "") -> None:
        conn = self._conn()
        if output_json:
            conn.execute(
                "UPDATE agent_tasks SET state = ?, output_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (state, output_json, task_id),
            )
        else:
            conn.execute(
                "UPDATE agent_tasks SET state = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (state, task_id),
            )
        conn.commit()
        conn.close()

    def get_pending_tasks(self) -> list[dict]:
        return self.get_agent_tasks(state="assigned")

    def get_tasks_for_review(self) -> list[dict]:
        return self.get_agent_tasks(state="review")

    def get_task(self, task_id: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT t.*, a.name as agent_name, a.agent_type FROM agent_tasks t JOIN ai_agents a ON t.agent_id = a.id WHERE t.id = ?",
            (task_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def override_task(self, task_id: int, human_notes: str) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE agent_tasks SET human_override = 1, human_notes = ?, state = 'complete', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (human_notes, task_id),
        )
        conn.commit()
        conn.close()

    # ---- Agent Output Log ----

    def log_agent_output(
        self, task_id: int, agent_id: int, output_type: str = "",
        content: str = "", metadata_json: str = "{}", tokens_used: int = 0,
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO agent_output_log (task_id, agent_id, output_type, content, metadata_json, tokens_used)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (task_id, agent_id, output_type, content, metadata_json, tokens_used),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_output_for_task(self, task_id: int) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM agent_output_log WHERE task_id = ? ORDER BY created_at",
            (task_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Guest Contacts ----

    def create_guest_contact(
        self, name: str, email: str = "", organization: str = "",
        role: str = "", website: str = "", notes: str = "",
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO guest_contacts (name, email, organization, role, website, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, email, organization, role, website, notes),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_guest_contacts(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM guest_contacts ORDER BY name").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_guest_contact(self, contact_id: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM guest_contacts WHERE id = ?", (contact_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_guest_contact(self, contact_id: int, **kwargs) -> None:
        if not kwargs:
            return
        self._validate_columns("guest_contacts", kwargs)
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [contact_id]
        conn = self._conn()
        conn.execute(f"UPDATE guest_contacts SET {sets} WHERE id = ?", vals)
        conn.commit()
        conn.close()

    # ---- Guest Articles ----

    def create_guest_article(
        self, contact_id: Optional[int] = None, title: str = "",
        author_name: str = "", author_bio: str = "", original_url: str = "",
        content_full: str = "", content_summary: str = "",
        display_mode: str = "full", permission_state: str = "requested",
        target_issue_id: Optional[int] = None, target_section_slug: str = "",
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO guest_articles
               (contact_id, title, author_name, author_bio, original_url,
                content_full, content_summary, display_mode, permission_state,
                target_issue_id, target_section_slug)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (contact_id, title, author_name, author_bio, original_url,
             content_full, content_summary, display_mode, permission_state,
             target_issue_id, target_section_slug),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_guest_articles(self, permission_state: Optional[str] = None) -> list[dict]:
        conn = self._conn()
        if permission_state:
            rows = conn.execute(
                """SELECT a.*, c.name as contact_name FROM guest_articles a
                   LEFT JOIN guest_contacts c ON a.contact_id = c.id
                   WHERE a.permission_state = ? ORDER BY a.created_at DESC""",
                (permission_state,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT a.*, c.name as contact_name FROM guest_articles a
                   LEFT JOIN guest_contacts c ON a.contact_id = c.id
                   ORDER BY a.created_at DESC""",
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_guest_article(self, article_id: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            """SELECT a.*, c.name as contact_name, c.email as contact_email
               FROM guest_articles a
               LEFT JOIN guest_contacts c ON a.contact_id = c.id
               WHERE a.id = ?""",
            (article_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_guest_article_permission(self, article_id: int, permission_state: str) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE guest_articles SET permission_state = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (permission_state, article_id),
        )
        conn.commit()
        conn.close()

    def update_guest_article(self, article_id: int, **kwargs) -> None:
        if not kwargs:
            return
        self._validate_columns("guest_articles", kwargs)
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [article_id]
        conn = self._conn()
        conn.execute(f"UPDATE guest_articles SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", vals)
        conn.commit()
        conn.close()

    def get_articles_for_issue(self, issue_id: int) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT a.*, c.name as contact_name FROM guest_articles a
               LEFT JOIN guest_contacts c ON a.contact_id = c.id
               WHERE a.target_issue_id = ? ORDER BY a.created_at""",
            (issue_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def count_guest_articles_for_contact(self, contact_id: int) -> int:
        """Count guest articles linked to a contact."""
        conn = self._conn()
        row = conn.execute(
            "SELECT COUNT(*) as c FROM guest_articles WHERE contact_id = ?",
            (contact_id,),
        ).fetchone()
        conn.close()
        return row["c"] if row else 0

    def guest_article_url_exists(self, original_url: str) -> bool:
        """Check if a guest article with this URL already exists."""
        conn = self._conn()
        row = conn.execute(
            "SELECT 1 FROM guest_articles WHERE original_url = ? LIMIT 1",
            (original_url,),
        ).fetchone()
        conn.close()
        return row is not None

    def get_guest_article_by_draft(self, draft_id: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            """SELECT a.*, c.name as contact_name, c.email as contact_email
               FROM guest_articles a
               LEFT JOIN guest_contacts c ON a.contact_id = c.id
               WHERE a.draft_id = ?""",
            (draft_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_submission_by_draft(self, draft_id: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM artist_submissions WHERE draft_id = ?",
            (draft_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    # ---- Artist Submissions ----

    def create_submission(
        self, artist_name: str, title: str = "", description: str = "",
        artist_email: str = "", artist_website: str = "", artist_social: str = "",
        submission_type: str = "new_release", intake_method: str = "web_form",
        release_date: str = "", genre: str = "", links_json: str = "[]",
        attachments_json: str = "[]", api_source: str = "",
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO artist_submissions
               (artist_name, title, description, artist_email, artist_website,
                artist_social, submission_type, intake_method, release_date,
                genre, links_json, attachments_json, api_source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (artist_name, title, description, artist_email, artist_website,
             artist_social, submission_type, intake_method, release_date,
             genre, links_json, attachments_json, api_source),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_submissions(self, review_state: Optional[str] = None, limit: int = 50) -> list[dict]:
        conn = self._conn()
        if review_state:
            rows = conn.execute(
                "SELECT * FROM artist_submissions WHERE review_state = ? ORDER BY created_at DESC LIMIT ?",
                (review_state, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM artist_submissions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_submission(self, submission_id: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM artist_submissions WHERE id = ?", (submission_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_submission_state(self, submission_id: int, review_state: str) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE artist_submissions SET review_state = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (review_state, submission_id),
        )
        conn.commit()
        conn.close()

    def update_submission(self, submission_id: int, **kwargs) -> None:
        if not kwargs:
            return
        self._validate_columns("artist_submissions", kwargs)
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [submission_id]
        conn = self._conn()
        conn.execute(f"UPDATE artist_submissions SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", vals)
        conn.commit()
        conn.close()

    def get_submissions_by_state(self, review_state: str) -> list[dict]:
        return self.get_submissions(review_state=review_state)

    # ---- Editorial Calendar ----

    def create_calendar_entry(
        self, issue_id: Optional[int] = None, planned_date: str = "",
        theme: str = "", notes: str = "", section_assignments: str = "{}",
        agent_assignments: str = "{}", status: str = "draft",
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO editorial_calendar
               (issue_id, planned_date, theme, notes, section_assignments, agent_assignments, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (issue_id, planned_date, theme, notes, section_assignments, agent_assignments, status),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_calendar(self, limit: int = 20) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT c.*, i.issue_number, i.title as issue_title
               FROM editorial_calendar c
               LEFT JOIN issues i ON c.issue_id = i.id
               ORDER BY c.planned_date DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_calendar_entry(self, entry_id: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            """SELECT c.*, i.issue_number, i.title as issue_title
               FROM editorial_calendar c
               LEFT JOIN issues i ON c.issue_id = i.id
               WHERE c.id = ?""",
            (entry_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_calendar_entry(self, entry_id: int, **kwargs) -> None:
        if not kwargs:
            return
        self._validate_columns("editorial_calendar", kwargs)
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [entry_id]
        conn = self._conn()
        conn.execute(f"UPDATE editorial_calendar SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", vals)
        conn.commit()
        conn.close()

    # ---- Growth Metrics ----

    def save_growth_metric(
        self, metric_date: str, total_subscribers: int = 0,
        new_subscribers: int = 0, churned_subscribers: int = 0,
        open_rate_avg: float = 0.0, click_rate_avg: float = 0.0,
        referral_count: int = 0, social_impressions: int = 0,
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO growth_metrics
               (metric_date, total_subscribers, new_subscribers, churned_subscribers,
                open_rate_avg, click_rate_avg, referral_count, social_impressions)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (metric_date, total_subscribers, new_subscribers, churned_subscribers,
             open_rate_avg, click_rate_avg, referral_count, social_impressions),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_growth_metrics(self, limit: int = 30) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM growth_metrics ORDER BY metric_date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_growth_trend(self, days: int = 30) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM growth_metrics ORDER BY metric_date DESC LIMIT ?",
            (days,),
        ).fetchall()
        conn.close()
        return list(reversed([dict(r) for r in rows]))

    # ---- Social Posts ----

    def create_social_post(
        self, platform: str = "twitter", content: str = "",
        issue_id: Optional[int] = None, status: str = "draft",
        scheduled_at: Optional[str] = None, agent_task_id: Optional[int] = None,
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO social_posts (platform, content, issue_id, status, scheduled_at, agent_task_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (platform, content, issue_id, status, scheduled_at, agent_task_id),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_social_posts(self, issue_id: Optional[int] = None, status: Optional[str] = None, limit: int = 50) -> list[dict]:
        conn = self._conn()
        q = "SELECT * FROM social_posts WHERE 1=1"
        params: list = []
        if issue_id is not None:
            q += " AND issue_id = ?"
            params.append(issue_id)
        if status:
            q += " AND status = ?"
            params.append(status)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(q, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_social_post(self, post_id: int, **kwargs) -> None:
        if not kwargs:
            return
        self._validate_columns("social_posts", kwargs)
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [post_id]
        conn = self._conn()
        conn.execute(f"UPDATE social_posts SET {sets} WHERE id = ?", vals)
        conn.commit()
        conn.close()

    # ---- Security Log ----

    def log_security_event(self, event_type: str, ip_address: str = "",
                           user_agent: str = "", detail: str = "") -> int:
        """Insert a security event into the audit log."""
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO security_log (event_type, ip_address, user_agent, detail)
               VALUES (?, ?, ?, ?)""",
            (event_type, ip_address, user_agent, detail),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_security_log(self, limit: int = 50, event_type: str | None = None) -> list[dict]:
        """Retrieve recent security events."""
        conn = self._conn()
        if event_type:
            rows = conn.execute(
                "SELECT * FROM security_log WHERE event_type = ? ORDER BY created_at DESC LIMIT ?",
                (event_type, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM security_log ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Stats ----

    def get_subscriber_by_email(self, email: str) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM subscribers WHERE email = ?", (email,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_subscriber_by_unsubscribe_token(self, token: str) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM subscribers WHERE unsubscribe_token = ?", (token,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_subscriber_by_verification_token(self, token: str) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM subscribers WHERE verification_token = ?", (token,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def verify_subscriber(self, token: str) -> bool:
        conn = self._conn()
        cur = conn.execute(
            "UPDATE subscribers SET email_verified = 1, verification_token = '', status = 'active' WHERE verification_token = ? AND verification_token != ''",
            (token,),
        )
        conn.commit()
        # Check if any row was actually updated
        changed = conn.execute("SELECT changes() as c").fetchone()
        conn.close()
        return (changed["c"] if changed else 0) > 0

    def unsubscribe_by_token(self, token: str) -> bool:
        conn = self._conn()
        cur = conn.execute(
            "UPDATE subscribers SET status = 'unsubscribed' WHERE unsubscribe_token = ? AND unsubscribe_token != ''",
            (token,),
        )
        conn.commit()
        changed = conn.execute("SELECT changes() as c").fetchone()
        conn.close()
        return (changed["c"] if changed else 0) > 0

    def set_subscriber_tokens(self, subscriber_id: int, verification_token: str, unsubscribe_token: str) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE subscribers SET verification_token = ?, unsubscribe_token = ? WHERE id = ?",
            (verification_token, unsubscribe_token, subscriber_id),
        )
        conn.commit()
        conn.close()

    # ---- Editor Articles ----

    def create_editor_article(
        self, title: str, content: str = "", author_name: str = "John",
        edition_slug: str = "", target_issue_id: int = 0,
        target_section_slug: str = "", notes: str = "",
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO editor_articles
               (title, content, author_name, edition_slug, target_issue_id,
                target_section_slug, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (title, content, author_name, edition_slug,
             target_issue_id or None, target_section_slug, notes),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_editor_articles(self, status: str = "") -> list[dict]:
        conn = self._conn()
        if status:
            rows = conn.execute(
                "SELECT * FROM editor_articles WHERE status = ? ORDER BY updated_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM editor_articles ORDER BY updated_at DESC"
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_editor_article(self, article_id: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM editor_articles WHERE id = ?", (article_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_editor_article(self, article_id: int, **fields) -> None:
        if not fields:
            return
        allowed = {
            "title", "content", "author_name", "edition_slug",
            "target_issue_id", "target_section_slug", "status", "notes", "draft_id",
        }
        filtered = {k: v for k, v in fields.items() if k in allowed}
        if not filtered:
            return
        filtered["updated_at"] = "CURRENT_TIMESTAMP"
        set_parts = []
        values = []
        for k, v in filtered.items():
            if v == "CURRENT_TIMESTAMP":
                set_parts.append(f"{k} = CURRENT_TIMESTAMP")
            else:
                set_parts.append(f"{k} = ?")
                values.append(v)
        values.append(article_id)
        conn = self._conn()
        conn.execute(
            f"UPDATE editor_articles SET {', '.join(set_parts)} WHERE id = ?",
            tuple(values),
        )
        conn.commit()
        conn.close()

    def delete_editor_article(self, article_id: int) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM editor_articles WHERE id = ?", (article_id,))
        conn.commit()
        conn.close()

    # ====================================================================
    # Advanced features (v21+) — all inactive by default
    # ====================================================================

    # ---- Email Tracking Events ----

    def record_tracking_event(
        self, subscriber_id: int, issue_id: int, event_type: str,
        link_url: str = "", ip_address: str = "", user_agent: str = "",
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO email_tracking_events
               (subscriber_id, issue_id, event_type, link_url, ip_address, user_agent)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (subscriber_id, issue_id, event_type, link_url, ip_address, user_agent),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_tracking_events(self, issue_id: int, event_type: str = "", limit: int = 500) -> list[dict]:
        conn = self._conn()
        q = "SELECT * FROM email_tracking_events WHERE issue_id = ?"
        params: list = [issue_id]
        if event_type:
            q += " AND event_type = ?"
            params.append(event_type)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(q, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_tracking_stats(self, issue_id: int) -> dict:
        conn = self._conn()
        row = conn.execute(
            """SELECT
                COUNT(DISTINCT CASE WHEN event_type='open' THEN subscriber_id END) as unique_opens,
                COUNT(DISTINCT CASE WHEN event_type='click' THEN subscriber_id END) as unique_clicks,
                COUNT(CASE WHEN event_type='open' THEN 1 END) as total_opens,
                COUNT(CASE WHEN event_type='click' THEN 1 END) as total_clicks
               FROM email_tracking_events WHERE issue_id = ?""",
            (issue_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else {"unique_opens": 0, "unique_clicks": 0, "total_opens": 0, "total_clicks": 0}

    def get_subscriber_last_event(self, subscriber_id: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM email_tracking_events WHERE subscriber_id = ? ORDER BY created_at DESC LIMIT 1",
            (subscriber_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    # ---- A/B Tests ----

    def create_ab_test(
        self, issue_id: int, test_type: str, variant_a: str, variant_b: str,
        sample_size_percent: int = 20, auto_send_winner: bool = True,
        measurement_hours: int = 4,
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO ab_tests
               (issue_id, test_type, variant_a, variant_b, sample_size_percent,
                auto_send_winner, measurement_hours)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (issue_id, test_type, variant_a, variant_b, sample_size_percent,
             int(auto_send_winner), measurement_hours),
        )
        test_id = cur.lastrowid
        # Create result rows for each variant
        conn.execute(
            "INSERT INTO ab_test_results (test_id, variant) VALUES (?, 'a')",
            (test_id,),
        )
        conn.execute(
            "INSERT INTO ab_test_results (test_id, variant) VALUES (?, 'b')",
            (test_id,),
        )
        conn.commit()
        conn.close()
        return test_id

    def get_ab_test(self, test_id: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM ab_tests WHERE id = ?", (test_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_ab_tests(self, issue_id: Optional[int] = None, status: str = "", limit: int = 50) -> list[dict]:
        conn = self._conn()
        q = "SELECT * FROM ab_tests WHERE 1=1"
        params: list = []
        if issue_id is not None:
            q += " AND issue_id = ?"
            params.append(issue_id)
        if status:
            q += " AND status = ?"
            params.append(status)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(q, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_ab_test_results(self, test_id: int) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM ab_test_results WHERE test_id = ? ORDER BY variant",
            (test_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_ab_test_result(self, test_id: int, variant: str, **kwargs) -> None:
        allowed = {"sends", "opens", "clicks", "unsubscribes"}
        filtered = {k: v for k, v in kwargs.items() if k in allowed}
        if not filtered:
            return
        sets = ", ".join(f"{k} = {k} + ?" for k in filtered)
        vals = list(filtered.values()) + [test_id, variant]
        conn = self._conn()
        conn.execute(f"UPDATE ab_test_results SET {sets} WHERE test_id = ? AND variant = ?", vals)
        conn.commit()
        conn.close()

    def update_ab_test(self, test_id: int, **kwargs) -> None:
        allowed = {"status", "winner", "started_at", "completed_at"}
        filtered = {k: v for k, v in kwargs.items() if k in allowed}
        if not filtered:
            return
        sets = ", ".join(f"{k} = ?" for k in filtered)
        vals = list(filtered.values()) + [test_id]
        conn = self._conn()
        conn.execute(f"UPDATE ab_tests SET {sets} WHERE id = ?", vals)
        conn.commit()
        conn.close()

    # ---- Bounce Log ----

    def record_bounce(self, email: str, bounce_type: str, raw_response: str = "",
                      subscriber_id: Optional[int] = None) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO bounce_log (subscriber_id, email, bounce_type, raw_response)
               VALUES (?, ?, ?, ?)""",
            (subscriber_id, email, bounce_type, raw_response),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_bounce_counts(self, email: str) -> dict:
        conn = self._conn()
        row = conn.execute(
            """SELECT
                COUNT(CASE WHEN bounce_type='hard' THEN 1 END) as hard,
                COUNT(CASE WHEN bounce_type='soft' THEN 1 END) as soft,
                COUNT(CASE WHEN bounce_type='complaint' THEN 1 END) as complaint
               FROM bounce_log WHERE email = ?""",
            (email,),
        ).fetchone()
        conn.close()
        return dict(row) if row else {"hard": 0, "soft": 0, "complaint": 0}

    def get_bounce_stats(self) -> dict:
        conn = self._conn()
        row = conn.execute(
            """SELECT
                COUNT(CASE WHEN bounce_type='hard' THEN 1 END) as hard,
                COUNT(CASE WHEN bounce_type='soft' THEN 1 END) as soft,
                COUNT(CASE WHEN bounce_type='complaint' THEN 1 END) as complaint,
                COUNT(*) as total
               FROM bounce_log""",
        ).fetchone()
        conn.close()
        return dict(row) if row else {"hard": 0, "soft": 0, "complaint": 0, "total": 0}

    # ---- Warmup Config ----

    def get_warmup(self, domain: str) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM warmup_config WHERE domain = ? AND is_active = 1",
            (domain,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_warmup_day(self, domain: str) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE warmup_config SET current_day = current_day + 1 WHERE domain = ?",
            (domain,),
        )
        conn.commit()
        conn.close()

    # ---- Scheduled Sends ----

    def create_scheduled_send(
        self, issue_id: int, edition_slug: str, subject: str, scheduled_at: str,
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO scheduled_sends (issue_id, edition_slug, subject, scheduled_at)
               VALUES (?, ?, ?, ?)""",
            (issue_id, edition_slug, subject, scheduled_at),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_pending_scheduled_sends(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT * FROM scheduled_sends
               WHERE status = 'pending' AND scheduled_at <= CURRENT_TIMESTAMP
               ORDER BY scheduled_at""",
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_upcoming_scheduled_sends(self, limit: int = 20) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT ss.*, i.issue_number, i.title as issue_title
               FROM scheduled_sends ss
               LEFT JOIN issues i ON ss.issue_id = i.id
               WHERE ss.status IN ('pending','processing')
               ORDER BY ss.scheduled_at LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_scheduled_send(self, send_id: int, status: str, error_message: str = "") -> None:
        conn = self._conn()
        if status == "sent":
            conn.execute(
                "UPDATE scheduled_sends SET status = ?, sent_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, send_id),
            )
        else:
            conn.execute(
                "UPDATE scheduled_sends SET status = ?, error_message = ? WHERE id = ?",
                (status, error_message, send_id),
            )
        conn.commit()
        conn.close()

    # ---- Webhooks ----

    def create_webhook(
        self, name: str, url: str, direction: str = "outbound",
        event_types: str = "", secret: str = "",
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO webhooks (name, url, direction, event_types, secret)
               VALUES (?, ?, ?, ?, ?)""",
            (name, url, direction, event_types, secret),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_webhooks(self, direction: str = "") -> list[dict]:
        conn = self._conn()
        if direction:
            rows = conn.execute(
                "SELECT * FROM webhooks WHERE direction = ? ORDER BY name",
                (direction,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM webhooks ORDER BY name").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_active_webhooks(self, event_type: str) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM webhooks WHERE is_active = 1 AND direction = 'outbound'",
        ).fetchall()
        conn.close()
        # Filter by event_type match (comma-separated list)
        return [dict(r) for r in rows if event_type in (r["event_types"] or "").split(",")]

    def toggle_webhook(self, webhook_id: int) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE webhooks SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END WHERE id = ?",
            (webhook_id,),
        )
        conn.commit()
        conn.close()

    def log_webhook(self, webhook_id: int, event_type: str, payload_json: str,
                    response_status: int = 0, response_body: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO webhook_log (webhook_id, event_type, payload_json, response_status, response_body)
               VALUES (?, ?, ?, ?, ?)""",
            (webhook_id, event_type, payload_json, response_status, response_body),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_webhook_log(self, webhook_id: Optional[int] = None, limit: int = 50) -> list[dict]:
        conn = self._conn()
        if webhook_id:
            rows = conn.execute(
                "SELECT * FROM webhook_log WHERE webhook_id = ? ORDER BY created_at DESC LIMIT ?",
                (webhook_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM webhook_log ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Referral Codes ----

    def create_referral_code(self, subscriber_id: int, code: str) -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO referral_codes (subscriber_id, code) VALUES (?, ?)",
            (subscriber_id, code),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_referral_code(self, subscriber_id: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM referral_codes WHERE subscriber_id = ?",
            (subscriber_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_referral_by_code(self, code: str) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM referral_codes WHERE code = ?", (code,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def increment_referral_count(self, code: str) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE referral_codes SET referral_count = referral_count + 1 WHERE code = ?",
            (code,),
        )
        conn.commit()
        conn.close()

    def log_referral(self, referrer_code: str, referred_subscriber_id: Optional[int],
                     referred_email: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO referral_log (referrer_code, referred_subscriber_id, referred_email)
               VALUES (?, ?, ?)""",
            (referrer_code, referred_subscriber_id, referred_email),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_top_referrers(self, limit: int = 20) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT rc.*, s.email as subscriber_email
               FROM referral_codes rc
               JOIN subscribers s ON rc.subscriber_id = s.id
               WHERE rc.referral_count > 0
               ORDER BY rc.referral_count DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Subscriber Preferences ----

    def get_subscriber_preferences(self, subscriber_id: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM subscriber_preferences WHERE subscriber_id = ?",
            (subscriber_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def upsert_subscriber_preferences(
        self, subscriber_id: int, content_frequency: str = "all",
        preferred_send_hour: int = -1, timezone: str = "", interests: str = "",
    ) -> None:
        conn = self._conn()
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

    # ---- Welcome Sequence ----

    def get_welcome_steps(self, edition_slug: str = "") -> list[dict]:
        conn = self._conn()
        if edition_slug:
            rows = conn.execute(
                "SELECT * FROM welcome_sequence_steps WHERE edition_slug = ? AND is_active = 1 ORDER BY step_number",
                (edition_slug,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM welcome_sequence_steps WHERE is_active = 1 ORDER BY edition_slug, step_number",
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def create_welcome_step(
        self, edition_slug: str, step_number: int, delay_hours: int,
        subject: str, html_content: str, plain_text: str = "",
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO welcome_sequence_steps
               (edition_slug, step_number, delay_hours, subject, html_content, plain_text)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (edition_slug, step_number, delay_hours, subject, html_content, plain_text),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def log_welcome_send(self, subscriber_id: int, step_id: int) -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO welcome_sequence_log (subscriber_id, step_id) VALUES (?, ?)",
            (subscriber_id, step_id),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_welcome_sends_for_subscriber(self, subscriber_id: int) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT wl.*, ws.step_number, ws.subject
               FROM welcome_sequence_log wl
               JOIN welcome_sequence_steps ws ON wl.step_id = ws.id
               WHERE wl.subscriber_id = ? ORDER BY ws.step_number""",
            (subscriber_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Re-engagement ----

    def create_reengagement_entry(self, subscriber_id: int, campaign_type: str = "winback") -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO reengagement_log (subscriber_id, campaign_type) VALUES (?, ?)",
            (subscriber_id, campaign_type),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def update_reengagement(self, log_id: int, opened: bool = False, clicked: bool = False) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE reengagement_log SET opened = ?, clicked = ? WHERE id = ?",
            (int(opened), int(clicked), log_id),
        )
        conn.commit()
        conn.close()

    def get_inactive_subscribers(self, days: int = 30) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT s.* FROM subscribers s
               WHERE s.status = 'active'
               AND s.id NOT IN (
                   SELECT DISTINCT subscriber_id FROM email_tracking_events
                   WHERE created_at >= datetime('now', ?)
               )""",
            (f"-{days} days",),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_reengagement_stats(self) -> dict:
        conn = self._conn()
        row = conn.execute(
            """SELECT
                COUNT(*) as total_sent,
                COUNT(CASE WHEN opened = 1 THEN 1 END) as opened,
                COUNT(CASE WHEN clicked = 1 THEN 1 END) as clicked
               FROM reengagement_log""",
        ).fetchone()
        conn.close()
        return dict(row) if row else {"total_sent": 0, "opened": 0, "clicked": 0}

    # ---- Reusable Blocks ----

    def create_reusable_block(
        self, name: str, slug: str, block_type: str = "content",
        html_content: str = "", plain_text: str = "",
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO reusable_blocks (name, slug, block_type, html_content, plain_text)
               VALUES (?, ?, ?, ?, ?)""",
            (name, slug, block_type, html_content, plain_text),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_reusable_block(self, slug: str) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM reusable_blocks WHERE slug = ?", (slug,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_reusable_blocks(self, block_type: str = "") -> list[dict]:
        conn = self._conn()
        if block_type:
            rows = conn.execute(
                "SELECT * FROM reusable_blocks WHERE block_type = ? AND is_active = 1 ORDER BY name",
                (block_type,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM reusable_blocks WHERE is_active = 1 ORDER BY block_type, name",
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_reusable_block(self, block_id: int, **kwargs) -> None:
        allowed = {"name", "html_content", "plain_text", "block_type", "is_active"}
        filtered = {k: v for k, v in kwargs.items() if k in allowed}
        if not filtered:
            return
        sets = ", ".join(f"{k} = ?" for k in filtered)
        vals = list(filtered.values()) + [block_id]
        conn = self._conn()
        conn.execute(f"UPDATE reusable_blocks SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", vals)
        conn.commit()
        conn.close()

    def delete_reusable_block(self, block_id: int) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM reusable_blocks WHERE id = ?", (block_id,))
        conn.commit()
        conn.close()

    # ---- User Roles ----

    def create_user_role(
        self, username: str, password_hash: str, role: str = "viewer",
        display_name: str = "", email: str = "",
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO user_roles (username, password_hash, role, display_name, email)
               VALUES (?, ?, ?, ?, ?)""",
            (username, password_hash, role, display_name, email),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_user_by_username(self, username: str) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM user_roles WHERE username = ? AND is_active = 1",
            (username,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_all_users(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT id, username, role, display_name, email, is_active, last_login_at, created_at FROM user_roles ORDER BY username",
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_user_role(self, username: str, role: str) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE user_roles SET role = ? WHERE username = ?",
            (role, username),
        )
        conn.commit()
        conn.close()

    def deactivate_user(self, username: str) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE user_roles SET is_active = 0 WHERE username = ?",
            (username,),
        )
        conn.commit()
        conn.close()

    def update_user_login(self, username: str) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE user_roles SET last_login_at = CURRENT_TIMESTAMP WHERE username = ?",
            (username,),
        )
        conn.commit()
        conn.close()

    # ---- Export Log ----

    def log_export(self, export_type: str, file_path: str = "",
                   file_size_bytes: int = 0, record_count: int = 0) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO export_log (export_type, file_path, file_size_bytes, record_count)
               VALUES (?, ?, ?, ?)""",
            (export_type, file_path, file_size_bytes, record_count),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_export_history(self, limit: int = 20) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM export_log ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Send Time History ----

    def record_send_time(self, subscriber_id: int, issue_id: int, sent_at: str,
                         hour_of_day: int, day_of_week: str) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO send_time_history (subscriber_id, issue_id, sent_at, hour_of_day, day_of_week)
               VALUES (?, ?, ?, ?, ?)""",
            (subscriber_id, issue_id, sent_at, hour_of_day, day_of_week),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def record_open_time(self, subscriber_id: int, issue_id: int) -> None:
        conn = self._conn()
        conn.execute(
            """UPDATE send_time_history SET opened_at = CURRENT_TIMESTAMP
               WHERE subscriber_id = ? AND issue_id = ? AND opened_at IS NULL""",
            (subscriber_id, issue_id),
        )
        conn.commit()
        conn.close()

    def get_optimal_send_hour(self, subscriber_id: int) -> Optional[int]:
        """Get the hour of day when this subscriber most often opens emails."""
        conn = self._conn()
        row = conn.execute(
            """SELECT CAST(strftime('%%H', opened_at) AS INTEGER) as hour, COUNT(*) as cnt
               FROM send_time_history
               WHERE subscriber_id = ? AND opened_at IS NOT NULL
               GROUP BY hour ORDER BY cnt DESC LIMIT 1""",
            (subscriber_id,),
        ).fetchone()
        conn.close()
        return row["hour"] if row else None

    # ====================================================================
    # Music-specific features (v22) — all inactive by default
    # ====================================================================

    # ---- Spotify Cache ----

    def upsert_spotify_artist(
        self, spotify_artist_id: str, artist_name: str = "", genres: str = "",
        followers: int = 0, popularity: int = 0, image_url: str = "",
        monthly_listeners: int = 0, data_json: str = "{}",
    ) -> int:
        conn = self._conn()
        conn.execute(
            """INSERT INTO spotify_artist_cache
               (spotify_artist_id, artist_name, genres, followers, popularity,
                image_url, monthly_listeners, data_json, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(spotify_artist_id) DO UPDATE SET
                   artist_name=excluded.artist_name, genres=excluded.genres,
                   followers=excluded.followers, popularity=excluded.popularity,
                   image_url=excluded.image_url, monthly_listeners=excluded.monthly_listeners,
                   data_json=excluded.data_json, fetched_at=CURRENT_TIMESTAMP""",
            (spotify_artist_id, artist_name, genres, followers, popularity,
             image_url, monthly_listeners, data_json),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM spotify_artist_cache WHERE spotify_artist_id = ?",
            (spotify_artist_id,),
        ).fetchone()
        conn.close()
        return row["id"] if row else 0

    def get_spotify_artist(self, spotify_artist_id: str) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM spotify_artist_cache WHERE spotify_artist_id = ?",
            (spotify_artist_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def search_spotify_cache(self, name: str, limit: int = 10) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM spotify_artist_cache WHERE artist_name LIKE ? ORDER BY popularity DESC LIMIT ?",
            (f"%{name}%", limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Spotify Releases ----

    def upsert_spotify_release(
        self, spotify_artist_id: str, album_id: str, album_name: str = "",
        release_date: str = "", album_type: str = "single",
        image_url: str = "", external_url: str = "",
    ) -> None:
        conn = self._conn()
        conn.execute(
            """INSERT INTO spotify_releases
               (spotify_artist_id, album_id, album_name, release_date, album_type, image_url, external_url)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(spotify_artist_id, album_id) DO UPDATE SET
                   album_name=excluded.album_name, release_date=excluded.release_date,
                   image_url=excluded.image_url, external_url=excluded.external_url""",
            (spotify_artist_id, album_id, album_name, release_date, album_type, image_url, external_url),
        )
        conn.commit()
        conn.close()

    def get_recent_releases(self, limit: int = 20) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT r.*, a.artist_name, a.image_url as artist_image
               FROM spotify_releases r
               JOIN spotify_artist_cache a ON r.spotify_artist_id = a.spotify_artist_id
               ORDER BY r.release_date DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Audio Embeds ----

    def create_audio_embed(
        self, embed_type: str, external_id: str, embed_url: str = "",
        thumbnail_url: str = "", title: str = "", artist_name: str = "",
        draft_id: Optional[int] = None, issue_id: Optional[int] = None,
        section_slug: str = "",
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO audio_embeds
               (draft_id, issue_id, section_slug, embed_type, external_id,
                embed_url, thumbnail_url, title, artist_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (draft_id, issue_id, section_slug, embed_type, external_id,
             embed_url, thumbnail_url, title, artist_name),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_embeds_for_issue(self, issue_id: int) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM audio_embeds WHERE issue_id = ? ORDER BY section_slug",
            (issue_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_embeds_for_draft(self, draft_id: int) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM audio_embeds WHERE draft_id = ?", (draft_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Artist Profiles ----

    def create_artist_profile(
        self, slug: str, artist_name: str, email: str = "", bio: str = "",
        website: str = "", social_links_json: str = "{}", image_url: str = "",
        spotify_artist_id: str = "", genres: str = "", submission_id: Optional[int] = None,
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO artist_profiles
               (slug, artist_name, email, bio, website, social_links_json,
                image_url, spotify_artist_id, genres, submission_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (slug, artist_name, email, bio, website, social_links_json,
             image_url, spotify_artist_id, genres, submission_id),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_artist_profile(self, slug: str) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM artist_profiles WHERE slug = ?", (slug,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_artist_profiles(self, published_only: bool = True, limit: int = 50) -> list[dict]:
        conn = self._conn()
        q = "SELECT * FROM artist_profiles"
        if published_only:
            q += " WHERE is_published = 1"
        q += " ORDER BY artist_name LIMIT ?"
        rows = conn.execute(q, (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_artist_profile(self, profile_id: int, **kwargs) -> None:
        allowed = {
            "artist_name", "email", "bio", "website", "social_links_json",
            "image_url", "spotify_artist_id", "genres", "music_embeds_json",
            "is_published", "is_approved", "self_service_token",
        }
        filtered = {k: v for k, v in kwargs.items() if k in allowed}
        if not filtered:
            return
        sets = ", ".join(f"{k} = ?" for k in filtered)
        vals = list(filtered.values()) + [profile_id]
        conn = self._conn()
        conn.execute(f"UPDATE artist_profiles SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", vals)
        conn.commit()
        conn.close()

    def get_artist_profile_by_token(self, token: str) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM artist_profiles WHERE self_service_token = ? AND self_service_token != ''",
            (token,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    # ---- Artist Followers ----

    def follow_artist(self, subscriber_id: int, artist_profile_id: int) -> None:
        conn = self._conn()
        conn.execute(
            """INSERT INTO artist_followers (subscriber_id, artist_profile_id)
               VALUES (?, ?) ON CONFLICT(subscriber_id, artist_profile_id) DO NOTHING""",
            (subscriber_id, artist_profile_id),
        )
        conn.commit()
        conn.close()

    def unfollow_artist(self, subscriber_id: int, artist_profile_id: int) -> None:
        conn = self._conn()
        conn.execute(
            "DELETE FROM artist_followers WHERE subscriber_id = ? AND artist_profile_id = ?",
            (subscriber_id, artist_profile_id),
        )
        conn.commit()
        conn.close()

    def get_artist_follower_count(self, artist_profile_id: int) -> int:
        conn = self._conn()
        row = conn.execute(
            "SELECT COUNT(*) as c FROM artist_followers WHERE artist_profile_id = ?",
            (artist_profile_id,),
        ).fetchone()
        conn.close()
        return row["c"] if row else 0

    def get_followed_artists(self, subscriber_id: int) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT ap.* FROM artist_profiles ap
               JOIN artist_followers af ON ap.id = af.artist_profile_id
               WHERE af.subscriber_id = ? ORDER BY ap.artist_name""",
            (subscriber_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Artist Features ----

    def link_artist_feature(self, artist_profile_id: int, issue_id: int,
                            section_slug: str = "", draft_id: Optional[int] = None) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO artist_newsletter_features
               (artist_profile_id, issue_id, section_slug, draft_id)
               VALUES (?, ?, ?, ?)""",
            (artist_profile_id, issue_id, section_slug, draft_id),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_artist_features(self, artist_profile_id: int, limit: int = 20) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT anf.*, i.issue_number, i.title as issue_title, i.edition_slug
               FROM artist_newsletter_features anf
               JOIN issues i ON anf.issue_id = i.id
               WHERE anf.artist_profile_id = ?
               ORDER BY anf.featured_at DESC LIMIT ?""",
            (artist_profile_id, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Subscriber Genres ----

    def set_subscriber_genres(self, subscriber_id: int, genres: list[str]) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM subscriber_genres WHERE subscriber_id = ?", (subscriber_id,))
        for i, genre in enumerate(genres):
            conn.execute(
                "INSERT INTO subscriber_genres (subscriber_id, genre, priority) VALUES (?, ?, ?)",
                (subscriber_id, genre.strip().lower(), i + 1),
            )
        conn.commit()
        conn.close()

    def get_subscriber_genres(self, subscriber_id: int) -> list[str]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT genre FROM subscriber_genres WHERE subscriber_id = ? ORDER BY priority",
            (subscriber_id,),
        ).fetchall()
        conn.close()
        return [r["genre"] for r in rows]

    def get_genre_subscriber_counts(self) -> dict:
        conn = self._conn()
        rows = conn.execute(
            "SELECT genre, COUNT(*) as c FROM subscriber_genres GROUP BY genre ORDER BY c DESC",
        ).fetchall()
        conn.close()
        return {r["genre"]: r["c"] for r in rows}

    # ---- Section Genres ----

    def set_section_genres(self, section_slug: str, genres: list[str]) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM section_genres WHERE section_slug = ?", (section_slug,))
        for genre in genres:
            conn.execute(
                "INSERT INTO section_genres (section_slug, genre) VALUES (?, ?)",
                (section_slug, genre.strip().lower()),
            )
        conn.commit()
        conn.close()

    def get_section_genres(self, section_slug: str) -> list[str]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT genre FROM section_genres WHERE section_slug = ?", (section_slug,),
        ).fetchall()
        conn.close()
        return [r["genre"] for r in rows]

    # ---- Section Engagement ----

    def record_section_engagement(
        self, subscriber_id: int, issue_id: int, section_slug: str,
        event_type: str = "click", link_url: str = "",
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO section_engagement_events
               (subscriber_id, issue_id, section_slug, event_type, link_url)
               VALUES (?, ?, ?, ?, ?)""",
            (subscriber_id, issue_id, section_slug, event_type, link_url),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_section_engagement_stats(self, issue_id: Optional[int] = None) -> list[dict]:
        conn = self._conn()
        if issue_id:
            rows = conn.execute(
                """SELECT section_slug,
                    COUNT(*) as total_clicks,
                    COUNT(DISTINCT subscriber_id) as unique_clickers
                   FROM section_engagement_events WHERE issue_id = ?
                   GROUP BY section_slug ORDER BY total_clicks DESC""",
                (issue_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT section_slug,
                    COUNT(*) as total_clicks,
                    COUNT(DISTINCT subscriber_id) as unique_clickers
                   FROM section_engagement_events
                   GROUP BY section_slug ORDER BY total_clicks DESC""",
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_section_performance(self, section_slug: str, limit: int = 20) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT issue_id, COUNT(*) as clicks, COUNT(DISTINCT subscriber_id) as unique_clicks
               FROM section_engagement_events WHERE section_slug = ?
               GROUP BY issue_id ORDER BY issue_id DESC LIMIT ?""",
            (section_slug, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def upsert_subscriber_interest(
        self, subscriber_id: int, section_slug: str,
        engagement_score: float, click_count: int,
    ) -> None:
        conn = self._conn()
        conn.execute(
            """INSERT INTO subscriber_interest_profiles
               (subscriber_id, section_slug, engagement_score, click_count, last_engaged_at, updated_at)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
               ON CONFLICT(subscriber_id, section_slug) DO UPDATE SET
                   engagement_score=excluded.engagement_score,
                   click_count=excluded.click_count,
                   last_engaged_at=CURRENT_TIMESTAMP,
                   updated_at=CURRENT_TIMESTAMP""",
            (subscriber_id, section_slug, engagement_score, click_count),
        )
        conn.commit()
        conn.close()

    def get_subscriber_interests(self, subscriber_id: int) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT * FROM subscriber_interest_profiles
               WHERE subscriber_id = ? ORDER BY engagement_score DESC""",
            (subscriber_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Trivia / Polls ----

    def create_trivia_poll(
        self, question_type: str, question_text: str, options_json: str = "[]",
        correct_option_index: int = -1, explanation: str = "",
        target_issue_id: Optional[int] = None, edition_slug: str = "",
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO trivia_polls
               (question_type, question_text, options_json, correct_option_index,
                explanation, target_issue_id, edition_slug)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (question_type, question_text, options_json, correct_option_index,
             explanation, target_issue_id, edition_slug),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_trivia_poll(self, poll_id: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM trivia_polls WHERE id = ?", (poll_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_trivia_polls(self, status: str = "", limit: int = 50) -> list[dict]:
        conn = self._conn()
        if status:
            rows = conn.execute(
                "SELECT * FROM trivia_polls WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trivia_polls ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_trivia_for_issue(self, issue_id: int) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM trivia_polls WHERE target_issue_id = ? ORDER BY id",
            (issue_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_trivia_poll(self, poll_id: int, **kwargs) -> None:
        allowed = {"status", "closes_at", "results_issue_id", "question_text",
                    "options_json", "correct_option_index", "explanation", "edition_slug"}
        filtered = {k: v for k, v in kwargs.items() if k in allowed}
        if not filtered:
            return
        sets = ", ".join(f"{k} = ?" for k in filtered)
        vals = list(filtered.values()) + [poll_id]
        conn = self._conn()
        conn.execute(f"UPDATE trivia_polls SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", vals)
        conn.commit()
        conn.close()

    def record_trivia_vote(self, poll_id: int, subscriber_id: int,
                           option_index: int, is_correct: bool = False) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO trivia_poll_votes
               (trivia_poll_id, subscriber_id, selected_option_index, is_correct)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(trivia_poll_id, subscriber_id) DO NOTHING""",
            (poll_id, subscriber_id, option_index, int(is_correct)),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id or 0

    def get_trivia_results(self, poll_id: int) -> dict:
        conn = self._conn()
        rows = conn.execute(
            """SELECT selected_option_index, COUNT(*) as votes
               FROM trivia_poll_votes WHERE trivia_poll_id = ?
               GROUP BY selected_option_index ORDER BY selected_option_index""",
            (poll_id,),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) as c FROM trivia_poll_votes WHERE trivia_poll_id = ?",
            (poll_id,),
        ).fetchone()
        conn.close()
        return {
            "votes_by_option": {r["selected_option_index"]: r["votes"] for r in rows},
            "total_votes": total["c"] if total else 0,
        }

    def has_voted(self, poll_id: int, subscriber_id: int) -> bool:
        conn = self._conn()
        row = conn.execute(
            "SELECT 1 FROM trivia_poll_votes WHERE trivia_poll_id = ? AND subscriber_id = ?",
            (poll_id, subscriber_id),
        ).fetchone()
        conn.close()
        return row is not None

    def update_trivia_leaderboard(self, subscriber_id: int, correct: bool) -> None:
        conn = self._conn()
        conn.execute(
            """INSERT INTO trivia_leaderboard (subscriber_id, correct_count, total_answered, streak, score)
               VALUES (?, ?, 1, ?, ?)
               ON CONFLICT(subscriber_id) DO UPDATE SET
                   correct_count = correct_count + ?,
                   total_answered = total_answered + 1,
                   streak = CASE WHEN ? = 1 THEN streak + 1 ELSE 0 END,
                   score = score + CASE WHEN ? = 1 THEN 10 + (CASE WHEN ? = 1 THEN streak ELSE 0 END) ELSE 1 END,
                   updated_at = CURRENT_TIMESTAMP""",
            (subscriber_id, int(correct), int(correct), 10 if correct else 1,
             int(correct), int(correct), int(correct), int(correct)),
        )
        conn.commit()
        conn.close()

    def get_trivia_leaderboard(self, limit: int = 25) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT tl.*, s.email, s.first_name
               FROM trivia_leaderboard tl
               JOIN subscribers s ON tl.subscriber_id = s.id
               ORDER BY tl.score DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ====================================================================
    # Growth & monetization (v23) — all inactive by default
    # ====================================================================

    # ---- Lead Magnets ----

    def create_lead_magnet(self, title: str, slug: str, description: str = "",
                           edition_slug: str = "", file_url: str = "", cover_image_url: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO lead_magnets (title, slug, description, edition_slug, file_url, cover_image_url)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, slug, description, edition_slug, file_url, cover_image_url),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_lead_magnet(self, slug: str) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM lead_magnets WHERE slug = ?", (slug,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_lead_magnets(self, active_only: bool = True) -> list[dict]:
        conn = self._conn()
        q = "SELECT * FROM lead_magnets"
        if active_only:
            q += " WHERE is_active = 1"
        q += " ORDER BY created_at DESC"
        rows = conn.execute(q).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def record_lead_magnet_download(self, lead_magnet_id: int, email: str,
                                    subscriber_id: Optional[int] = None) -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO lead_magnet_downloads (lead_magnet_id, email, subscriber_id) VALUES (?, ?, ?)",
            (lead_magnet_id, email, subscriber_id),
        )
        conn.execute(
            "UPDATE lead_magnets SET download_count = download_count + 1 WHERE id = ?",
            (lead_magnet_id,),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    # ---- Sponsor Inquiries ----

    def create_sponsor_inquiry(self, company_name: str, contact_email: str,
                               contact_name: str = "", website: str = "",
                               budget_range: str = "", message: str = "",
                               editions_interested: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO sponsor_inquiries
               (company_name, contact_name, contact_email, website, budget_range, message, editions_interested)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (company_name, contact_name, contact_email, website, budget_range, message, editions_interested),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_sponsor_inquiries(self, status: str = "", limit: int = 50) -> list[dict]:
        conn = self._conn()
        if status:
            rows = conn.execute(
                "SELECT * FROM sponsor_inquiries WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sponsor_inquiries ORDER BY created_at DESC LIMIT ?", (limit,),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_sponsor_inquiry(self, inquiry_id: int, status: str, notes: str = "") -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE sponsor_inquiries SET status = ?, notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, notes, inquiry_id),
        )
        conn.commit()
        conn.close()

    # ---- Contests ----

    def create_contest(self, title: str, description: str = "", prize_description: str = "",
                       contest_type: str = "referral", entry_requirement: str = "",
                       edition_slug: str = "", start_date: str = "", end_date: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO contests (title, description, prize_description, contest_type,
               entry_requirement, edition_slug, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, description, prize_description, contest_type, entry_requirement,
             edition_slug, start_date, end_date),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_contests(self, status: str = "", limit: int = 20) -> list[dict]:
        conn = self._conn()
        if status:
            rows = conn.execute(
                "SELECT * FROM contests WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM contests ORDER BY created_at DESC LIMIT ?", (limit,),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_contest(self, contest_id: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM contests WHERE id = ?", (contest_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_contest(self, contest_id: int, **kwargs) -> None:
        allowed = {"title", "description", "prize_description", "status",
                    "winner_subscriber_id", "winner_name", "start_date", "end_date"}
        filtered = {k: v for k, v in kwargs.items() if k in allowed}
        if not filtered:
            return
        sets = ", ".join(f"{k} = ?" for k in filtered)
        vals = list(filtered.values()) + [contest_id]
        conn = self._conn()
        conn.execute(f"UPDATE contests SET {sets} WHERE id = ?", vals)
        conn.commit()
        conn.close()

    def enter_contest(self, contest_id: int, subscriber_id: int, email: str = "",
                      entry_data_json: str = "{}") -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO contest_entries (contest_id, subscriber_id, email, entry_data_json)
               VALUES (?, ?, ?, ?) ON CONFLICT(contest_id, subscriber_id) DO NOTHING""",
            (contest_id, subscriber_id, email, entry_data_json),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id or 0

    def get_contest_entry_count(self, contest_id: int) -> int:
        conn = self._conn()
        row = conn.execute(
            "SELECT COUNT(*) as c FROM contest_entries WHERE contest_id = ?", (contest_id,),
        ).fetchone()
        conn.close()
        return row["c"] if row else 0

    # ---- Reader Contributions ----

    def create_reader_contribution(self, email: str, name: str = "", content_type: str = "hot_take",
                                   content: str = "", edition_slug: str = "",
                                   subscriber_id: Optional[int] = None) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO reader_contributions (subscriber_id, email, name, content_type, content, edition_slug)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (subscriber_id, email, name, content_type, content, edition_slug),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_reader_contributions(self, status: str = "", content_type: str = "", limit: int = 50) -> list[dict]:
        conn = self._conn()
        q = "SELECT * FROM reader_contributions WHERE 1=1"
        params: list = []
        if status:
            q += " AND status = ?"
            params.append(status)
        if content_type:
            q += " AND content_type = ?"
            params.append(content_type)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(q, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_reader_contribution(self, contrib_id: int, status: str,
                                   featured_in_issue_id: Optional[int] = None) -> None:
        conn = self._conn()
        if featured_in_issue_id:
            conn.execute(
                "UPDATE reader_contributions SET status = ?, featured_in_issue_id = ? WHERE id = ?",
                (status, featured_in_issue_id, contrib_id),
            )
        else:
            conn.execute(
                "UPDATE reader_contributions SET status = ? WHERE id = ?", (status, contrib_id),
            )
        conn.commit()
        conn.close()

    # ---- Referral Rewards ----

    def get_referral_rewards(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM referral_rewards WHERE is_active = 1 ORDER BY sort_order, referrals_required",
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def create_referral_reward(self, tier_name: str, referrals_required: int,
                               reward_description: str = "", reward_type: str = "badge",
                               sort_order: int = 0) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO referral_rewards (tier_name, referrals_required, reward_description, reward_type, sort_order)
               VALUES (?, ?, ?, ?, ?)""",
            (tier_name, referrals_required, reward_description, reward_type, sort_order),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    # ---- Newsletter Milestones ----

    def get_milestones(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM newsletter_milestones ORDER BY target_subscribers",
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_current_milestone(self, subscriber_count: int) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM newsletter_milestones WHERE target_subscribers > ? ORDER BY target_subscribers LIMIT 1",
            (subscriber_count,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def create_milestone(self, target_subscribers: int, title: str = "",
                         description: str = "", unlock_description: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO newsletter_milestones (target_subscribers, title, description, unlock_description)
               VALUES (?, ?, ?, ?)""",
            (target_subscribers, title, description, unlock_description),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    # ---- Audio Issues ----

    def create_audio_issue(self, issue_id: int, edition_slug: str = "", tts_provider: str = "openai") -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO audio_issues (issue_id, edition_slug, tts_provider) VALUES (?, ?, ?)",
            (issue_id, edition_slug, tts_provider),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_audio_issue(self, issue_id: int):
        conn = self._conn()
        row = conn.execute("SELECT * FROM audio_issues WHERE issue_id = ? ORDER BY id DESC LIMIT 1", (issue_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_audio_issue(self, audio_id: int, **kwargs) -> None:
        if not kwargs:
            return
        allowed = {"audio_url", "duration_seconds", "file_size_bytes", "status"}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        conn = self._conn()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE audio_issues SET {set_clause} WHERE id = ?", (*fields.values(), audio_id))
        conn.commit()
        conn.close()

    def get_audio_issues(self, limit: int = 50) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT ai.*, i.issue_number FROM audio_issues ai LEFT JOIN issues i ON i.id = ai.issue_id ORDER BY ai.id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Subscriber Tiers & Billing ----

    def get_tiers(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM subscriber_tiers WHERE is_active = 1 ORDER BY sort_order").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_tier_by_slug(self, slug: str):
        conn = self._conn()
        row = conn.execute("SELECT * FROM subscriber_tiers WHERE slug = ?", (slug,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def create_billing_record(self, subscriber_id: int, tier_id: int, payment_customer_id: str = "", payment_subscription_id: str = "", payment_provider: str = "manifest") -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO subscriber_billing (subscriber_id, tier_id, payment_customer_id, payment_subscription_id, payment_provider) VALUES (?, ?, ?, ?, ?)",
            (subscriber_id, tier_id, payment_customer_id, payment_subscription_id, payment_provider),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_billing_for_subscriber(self, subscriber_id: int):
        conn = self._conn()
        row = conn.execute(
            """SELECT sb.*, st.slug as tier_slug, st.name as tier_name
               FROM subscriber_billing sb
               JOIN subscriber_tiers st ON st.id = sb.tier_id
               WHERE sb.subscriber_id = ? ORDER BY sb.id DESC LIMIT 1""",
            (subscriber_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_billing_by_payment_id(self, payment_subscription_id: str):
        conn = self._conn()
        row = conn.execute(
            """SELECT sb.*, st.slug as tier_slug, st.name as tier_name
               FROM subscriber_billing sb
               JOIN subscriber_tiers st ON st.id = sb.tier_id
               WHERE sb.payment_subscription_id = ? LIMIT 1""",
            (payment_subscription_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_billing_status(self, payment_subscription_id: str, status: str, current_period_end: str = "") -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE subscriber_billing SET status = ?, current_period_end = ?, updated_at = CURRENT_TIMESTAMP WHERE payment_subscription_id = ?",
            (status, current_period_end, payment_subscription_id),
        )
        conn.commit()
        conn.close()

    def update_dunning_state(self, payment_subscription_id: str, dunning_state: str) -> None:
        conn = self._conn()
        if dunning_state and dunning_state != "":
            conn.execute(
                "UPDATE subscriber_billing SET dunning_state = ?, dunning_started_at = COALESCE(dunning_started_at, CURRENT_TIMESTAMP), updated_at = CURRENT_TIMESTAMP WHERE payment_subscription_id = ?",
                (dunning_state, payment_subscription_id),
            )
        else:
            conn.execute(
                "UPDATE subscriber_billing SET dunning_state = '', dunning_started_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE payment_subscription_id = ?",
                (payment_subscription_id,),
            )
        conn.commit()
        conn.close()

    def get_past_due_subscriptions(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT sb.*, st.slug as tier_slug FROM subscriber_billing sb JOIN subscriber_tiers st ON st.id = sb.tier_id WHERE sb.status = 'past_due' AND sb.dunning_state != 'cancelled'"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Invoices ----

    def create_invoice(self, invoice_number: str, entity_type: str, entity_id: int, amount_cents: int, line_items_json: str = "[]", due_date: str = "", notes: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO invoices (invoice_number, entity_type, entity_id, amount_cents, line_items_json, due_date, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (invoice_number, entity_type, entity_id, amount_cents, line_items_json, due_date, notes),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_invoices(self, entity_type: str = "", entity_id: int = 0, status: str = "") -> list[dict]:
        conn = self._conn()
        sql = "SELECT * FROM invoices WHERE 1=1"
        params: list = []
        if entity_type:
            sql += " AND entity_type = ?"
            params.append(entity_type)
        if entity_id:
            sql += " AND entity_id = ?"
            params.append(entity_id)
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC"
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_invoice(self, invoice_id: int) -> Optional[dict]:
        """Return a single invoice row by id, or None."""
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_invoice_status(self, invoice_id: int, status: str, payment_transaction_id: str = "") -> None:
        conn = self._conn()
        if status == "paid":
            conn.execute(
                "UPDATE invoices SET status = ?, payment_transaction_id = ?, paid_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, payment_transaction_id, invoice_id),
            )
        else:
            conn.execute("UPDATE invoices SET status = ? WHERE id = ?", (status, invoice_id))
        conn.commit()
        conn.close()

    # ---- Coupons ----

    def create_coupon(self, code: str, description: str = "", discount_type: str = "percentage", discount_value: int = 0, applies_to: str = "subscription", max_uses: int = 0, valid_from: str = "", valid_until: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO coupons (code, description, discount_type, discount_value, applies_to, max_uses, valid_from, valid_until) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (code, description, discount_type, discount_value, applies_to, max_uses, valid_from, valid_until),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_coupon_by_code(self, code: str):
        conn = self._conn()
        row = conn.execute("SELECT * FROM coupons WHERE code = ? AND is_active = 1", (code,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_active_coupons(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM coupons WHERE is_active = 1 ORDER BY created_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def redeem_coupon(self, coupon_id: int, subscriber_id: int = 0, licensee_id: int = 0, discount_applied_cents: int = 0) -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO coupon_redemptions (coupon_id, subscriber_id, licensee_id, discount_applied_cents) VALUES (?, ?, ?, ?)",
            (coupon_id, subscriber_id if subscriber_id else None, licensee_id if licensee_id else None, discount_applied_cents),
        )
        conn.execute("UPDATE coupons SET current_uses = current_uses + 1 WHERE id = ?", (coupon_id,))
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    # ---- Community Forum ----

    def get_forum_categories(self, edition_slug: str = "") -> list[dict]:
        conn = self._conn()
        if edition_slug:
            rows = conn.execute(
                "SELECT * FROM forum_categories WHERE is_active = 1 AND edition_slug = ? ORDER BY sort_order",
                (edition_slug,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM forum_categories WHERE is_active = 1 ORDER BY sort_order").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_forum_category_by_slug(self, slug: str):
        conn = self._conn()
        row = conn.execute("SELECT * FROM forum_categories WHERE slug = ?", (slug,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def create_forum_thread(self, category_id: int, subscriber_id: int, title: str, content: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO forum_threads (category_id, subscriber_id, title, content) VALUES (?, ?, ?, ?)",
            (category_id, subscriber_id, title, content),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_forum_threads(self, category_id: int, limit: int = 50) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT ft.*, s.email as author_email, s.first_name as author_name
               FROM forum_threads ft
               LEFT JOIN subscribers s ON s.id = ft.subscriber_id
               WHERE ft.category_id = ?
               ORDER BY ft.is_pinned DESC, ft.last_reply_at DESC NULLS LAST, ft.created_at DESC
               LIMIT ?""",
            (category_id, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_forum_thread(self, thread_id: int):
        conn = self._conn()
        row = conn.execute(
            """SELECT ft.*, s.email as author_email, s.first_name as author_name, fc.name as category_name, fc.slug as category_slug
               FROM forum_threads ft
               LEFT JOIN subscribers s ON s.id = ft.subscriber_id
               LEFT JOIN forum_categories fc ON fc.id = ft.category_id
               WHERE ft.id = ?""",
            (thread_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def create_forum_reply(self, thread_id: int, subscriber_id: int, content: str) -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO forum_replies (thread_id, subscriber_id, content) VALUES (?, ?, ?)",
            (thread_id, subscriber_id, content),
        )
        # Update reply count and last_reply_at
        conn.execute(
            "UPDATE forum_threads SET reply_count = reply_count + 1, last_reply_at = CURRENT_TIMESTAMP WHERE id = ?",
            (thread_id,),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_forum_replies(self, thread_id: int, limit: int = 100) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT fr.*, s.email as author_email, s.first_name as author_name
               FROM forum_replies fr
               LEFT JOIN subscribers s ON s.id = fr.subscriber_id
               WHERE fr.thread_id = ?
               ORDER BY fr.created_at ASC
               LIMIT ?""",
            (thread_id, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Advertiser Portal ----

    def create_advertiser_account(self, sponsor_id: int, email: str, password_hash: str) -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO advertiser_accounts (sponsor_id, email, password_hash) VALUES (?, ?, ?)",
            (sponsor_id, email, password_hash),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_advertiser_by_email(self, email: str):
        conn = self._conn()
        row = conn.execute(
            "SELECT aa.*, s.name as sponsor_name FROM advertiser_accounts aa LEFT JOIN sponsors s ON s.id = aa.sponsor_id WHERE aa.email = ?",
            (email,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_advertiser_campaigns(self, advertiser_id: int) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM advertiser_campaigns WHERE advertiser_id = ? ORDER BY created_at DESC",
            (advertiser_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def create_advertiser_campaign(self, advertiser_id: int, name: str, edition_slug: str = "", position: str = "mid", headline: str = "", body_html: str = "", cta_url: str = "", cta_text: str = "Learn More", image_url: str = "", budget_cents: int = 0) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO advertiser_campaigns
               (advertiser_id, name, edition_slug, position, headline, body_html, cta_url, cta_text, image_url, budget_cents, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft')""",
            (advertiser_id, name, edition_slug, position, headline, body_html, cta_url, cta_text, image_url, budget_cents),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_advertiser_campaign(self, campaign_id: int):
        conn = self._conn()
        row = conn.execute("SELECT * FROM advertiser_campaigns WHERE id = ?", (campaign_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_campaign_status(self, campaign_id: int, status: str) -> None:
        conn = self._conn()
        conn.execute("UPDATE advertiser_campaigns SET status = ? WHERE id = ?", (status, campaign_id))
        conn.commit()
        conn.close()

    def get_pending_campaigns(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT ac.*, aa.email as advertiser_email, s.name as sponsor_name
               FROM advertiser_campaigns ac
               LEFT JOIN advertiser_accounts aa ON aa.id = ac.advertiser_id
               LEFT JOIN sponsors s ON s.id = aa.sponsor_id
               WHERE ac.status = 'submitted'
               ORDER BY ac.created_at""",
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Affiliate Programs ----

    def get_affiliate_programs(self, active_only: bool = True, category: str = "", edition: str = "") -> list[dict]:
        conn = self._conn()
        query = "SELECT * FROM affiliate_programs"
        conditions = []
        params = []
        if active_only:
            conditions.append("is_active = 1")
        if category:
            conditions.append("category = ?")
            params.append(category)
        if edition:
            conditions.append("target_editions LIKE ?")
            params.append(f"%{edition}%")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY name"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_affiliate_by_slug(self, slug: str):
        conn = self._conn()
        row = conn.execute("SELECT * FROM affiliate_programs WHERE slug = ?", (slug,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def record_affiliate_click(self, affiliate_id: int) -> None:
        conn = self._conn()
        conn.execute("UPDATE affiliate_programs SET total_clicks = total_clicks + 1 WHERE id = ?", (affiliate_id,))
        conn.commit()
        conn.close()

    def create_affiliate_placement(self, affiliate_id: int, issue_id: int = 0, edition_slug: str = "", section_slug: str = "", placement_type: str = "inline", anchor_text: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO affiliate_placements (affiliate_id, issue_id, edition_slug, section_slug, placement_type, anchor_text) VALUES (?, ?, ?, ?, ?, ?)",
            (affiliate_id, issue_id or None, edition_slug, section_slug, placement_type, anchor_text),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_affiliate_placements(self, issue_id: int = 0, edition_slug: str = "") -> list[dict]:
        conn = self._conn()
        query = """SELECT ap.*, af.name as affiliate_name, af.affiliate_url, af.commission_rate
                   FROM affiliate_placements ap
                   JOIN affiliate_programs af ON af.id = ap.affiliate_id"""
        if issue_id:
            query += " WHERE ap.issue_id = ?"
            rows = conn.execute(query, (issue_id,)).fetchall()
        elif edition_slug:
            query += " WHERE ap.edition_slug = ?"
            rows = conn.execute(query, (edition_slug,)).fetchall()
        else:
            rows = conn.execute(query).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Revenue Dashboard ----

    def get_revenue_summary(self) -> dict:
        conn = self._conn()
        # Sponsor revenue by status
        row = conn.execute(
            """SELECT
                COALESCE(SUM(CASE WHEN status = 'paid' THEN rate_cents ELSE 0 END), 0) as paid_cents,
                COALESCE(SUM(CASE WHEN status IN ('booked','confirmed','delivered','invoiced') THEN rate_cents ELSE 0 END), 0) as pipeline_cents,
                COUNT(*) as total_bookings
               FROM sponsor_bookings"""
        ).fetchone()
        sponsor = dict(row) if row else {"paid_cents": 0, "pipeline_cents": 0, "total_bookings": 0}

        # Affiliate revenue
        aff_row = conn.execute("SELECT COALESCE(SUM(total_clicks), 0) as total_clicks, COALESCE(SUM(total_revenue_cents), 0) as total_revenue FROM affiliate_programs").fetchone()
        affiliate = dict(aff_row) if aff_row else {"total_clicks": 0, "total_revenue": 0}

        # Tier MRR
        tier_row = conn.execute(
            """SELECT COALESCE(SUM(st.price_cents), 0) as mrr_cents, COUNT(*) as active_subs
               FROM subscriber_billing sb
               JOIN subscriber_tiers st ON st.id = sb.tier_id
               WHERE sb.status = 'active'"""
        ).fetchone()
        tier = dict(tier_row) if tier_row else {"mrr_cents": 0, "active_subs": 0}

        conn.close()
        return {"sponsor": sponsor, "affiliate": affiliate, "tier": tier}

    def get_revenue_by_edition(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT i.edition_slug, COALESCE(SUM(sb.rate_cents), 0) as total_cents, COUNT(sb.id) as booking_count
               FROM sponsor_bookings sb
               LEFT JOIN issues i ON i.id = sb.issue_id
               GROUP BY i.edition_slug
               ORDER BY total_cents DESC"""
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_tier_breakdown(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT st.name, st.price_cents, COUNT(sb.id) as subscriber_count,
                      COUNT(sb.id) * st.price_cents as mrr_cents
               FROM subscriber_tiers st
               LEFT JOIN subscriber_billing sb ON sb.tier_id = st.id AND sb.status = 'active'
               GROUP BY st.id
               ORDER BY st.sort_order"""
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_related_issues(self, edition_slug: str, exclude_id: int, limit: int = 3) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM issues WHERE edition_slug = ? AND id != ? AND status = 'published' ORDER BY publish_date DESC LIMIT ?",
            (edition_slug, exclude_id, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Stats ----

    def get_table_counts(self) -> dict:
        conn = self._conn()
        tables = [
            "issues", "section_definitions", "sources", "raw_content",
            "editorial_inputs", "drafts", "assembled_issues", "subscribers",
        ]
        counts = {}
        for t in tables:
            row = conn.execute(f"SELECT COUNT(*) as c FROM {t}").fetchone()
            counts[t] = row["c"]
        conn.close()
        return counts

    # ---- Mobile App Waitlist ----

    def create_mobile_waitlist(self, email: str, platform: str = "both") -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO mobile_app_waitlist (email, platform) VALUES (?, ?)",
            (email, platform),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_mobile_waitlist(self, limit: int = 100) -> list[dict]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM mobile_app_waitlist ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_mobile_waitlist_count(self) -> int:
        conn = self._conn()
        row = conn.execute("SELECT COUNT(*) as count FROM mobile_app_waitlist").fetchone()
        conn.close()
        return dict(row)["count"] if row else 0

    # ---- Subscriber Segments ----

    def get_subscriber_segments_summary(self) -> dict:
        conn = self._conn()
        # By edition
        by_edition = conn.execute(
            """SELECT ne.slug, ne.name, COUNT(se.id) as count
               FROM newsletter_editions ne
               LEFT JOIN subscriber_editions se ON se.edition_id = ne.id
               LEFT JOIN subscribers s ON s.id = se.subscriber_id AND s.status = 'active'
               WHERE ne.is_active = 1
               GROUP BY ne.id ORDER BY ne.sort_order"""
        ).fetchall()

        # By genre
        by_genre = conn.execute(
            """SELECT sg.genre, COUNT(DISTINCT sg.subscriber_id) as count
               FROM subscriber_genres sg
               JOIN subscribers s ON s.id = sg.subscriber_id AND s.status = 'active'
               GROUP BY sg.genre ORDER BY count DESC"""
        ).fetchall()

        # Total
        total = conn.execute("SELECT COUNT(*) as count FROM subscribers WHERE status = 'active'").fetchone()

        conn.close()
        return {
            "by_edition": [dict(r) for r in by_edition],
            "by_genre": [dict(r) for r in by_genre],
            "total": dict(total)["count"] if total else 0,
        }

    def get_cohort_retention(self, months: int = 6) -> list[dict]:
        # Fetch raw signup rows and bucket by YYYY-MM in Python — avoids
        # relying on SQLite's strftime() which Postgres does not expose.
        conn = self._conn()
        rows = conn.execute(
            """SELECT subscribed_at, status
               FROM subscribers
               WHERE subscribed_at IS NOT NULL"""
        ).fetchall()
        conn.close()

        buckets: dict[str, dict[str, int]] = {}
        for r in rows:
            d = dict(r)
            sub_at = d.get("subscribed_at")
            if not sub_at:
                continue
            # Both SQLite (TEXT) and Postgres (TIMESTAMP) give us something
            # whose str() starts with YYYY-MM — slice is safe for either.
            cohort = str(sub_at)[:7]
            if len(cohort) != 7 or cohort[4] != "-":
                continue
            b = buckets.setdefault(cohort, {"total_signups": 0, "still_active": 0})
            b["total_signups"] += 1
            if (d.get("status") or "") == "active":
                b["still_active"] += 1

        result: list[dict] = []
        for cohort in sorted(buckets.keys(), reverse=True)[:months]:
            b = buckets[cohort]
            total = b["total_signups"]
            result.append({
                "cohort": cohort,
                "total_signups": total,
                "still_active": b["still_active"],
                "retention_pct": round(100 * b["still_active"] / total, 1) if total else 0,
            })
        return result

    def get_at_risk_subscribers(self, days_inactive: int = 30, limit: int = 50) -> list[dict]:
        # SQLite's `datetime('now', ? || ' days')` is not portable to
        # Postgres, and `NULLS FIRST` is only supported on Postgres —
        # compute the cutoff in Python and sort in Python too.
        from datetime import datetime, timedelta
        cutoff = (datetime.utcnow() - timedelta(days=days_inactive)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        conn = self._conn()
        rows = conn.execute(
            """SELECT s.id, s.email, s.subscribed_at,
                      MAX(ete.created_at) as last_activity
               FROM subscribers s
               LEFT JOIN email_tracking_events ete ON ete.subscriber_id = s.id
               WHERE s.status = 'active'
               GROUP BY s.id, s.email, s.subscribed_at"""
        ).fetchall()
        conn.close()

        rows = [dict(r) for r in rows]
        at_risk = [
            r for r in rows
            if r.get("last_activity") is None or str(r["last_activity"]) < cutoff
        ]
        at_risk.sort(key=lambda r: (r.get("last_activity") is not None, str(r.get("last_activity") or "")))
        return at_risk[:limit]

    # ---- Admin Users ----

    def get_admin_users(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM admin_users WHERE is_active = 1 ORDER BY role, display_name"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_admin_user_by_email(self, email: str):
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM admin_users WHERE email = ? AND is_active = 1", (email,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def create_admin_user(
        self, email: str, password_hash: str, display_name: str = "", role: str = "viewer"
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO admin_users (email, password_hash, display_name, role) VALUES (?, ?, ?, ?)",
            (email, password_hash, display_name, role),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def update_admin_user_role(self, user_id: int, role: str) -> None:
        conn = self._conn()
        conn.execute("UPDATE admin_users SET role = ? WHERE id = ?", (role, user_id))
        conn.commit()
        conn.close()

    # ---- Licensing ----

    class TerritoryConflictError(Exception):
        """Raised when a new licensee would overlap an existing exclusive territory."""

    def create_licensee(self, company_name: str, contact_name: str, email: str, password_hash: str, city_market_slug: str = "", edition_slugs: str = "", license_type: str = "monthly", license_fee_cents: int = 0, revenue_share_pct: float = 20.0, allow_territory_overlap: bool = False) -> int:
        # Territory exclusivity — refuse to create a new licensee whose
        # city_market_slug overlaps an existing active or pending licensee
        # for any of the same editions. Pass allow_territory_overlap=True
        # to override (admin escape hatch for special cases).
        if city_market_slug and not allow_territory_overlap:
            existing = self._find_overlapping_licensee(
                city_market_slug=city_market_slug,
                edition_slugs=edition_slugs,
            )
            if existing:
                raise Repository.TerritoryConflictError(
                    f"Territory '{city_market_slug}' for editions "
                    f"'{edition_slugs}' overlaps existing licensee "
                    f"#{existing['id']} ({existing.get('company_name')})"
                )
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO licensees (company_name, contact_name, email, password_hash, city_market_slug, edition_slugs, license_type, license_fee_cents, revenue_share_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (company_name, contact_name, email, password_hash, city_market_slug, edition_slugs, license_type, license_fee_cents, revenue_share_pct),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def _find_overlapping_licensee(
        self, city_market_slug: str, edition_slugs: str
    ) -> Optional[dict]:
        """Return the first existing active/pending licensee whose
        city_market_slug matches AND whose edition_slugs share at least
        one edition with the given list. None if no overlap.
        """
        if not city_market_slug:
            return None
        new_editions = {
            e.strip() for e in (edition_slugs or "").split(",") if e.strip()
        }
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM licensees "
            "WHERE city_market_slug = ? "
            "AND status IN ('active','pending','trialing','past_due')",
            (city_market_slug,),
        ).fetchall()
        conn.close()
        for r in rows:
            d = dict(r)
            existing_eds = {
                e.strip()
                for e in (d.get("edition_slugs") or "").split(",")
                if e.strip()
            }
            if not new_editions:
                # No editions specified on the new licensee — any existing
                # licensee in the same city is treated as a conflict.
                return d
            if existing_eds & new_editions:
                return d
        return None

    def get_licensees(self, status: str = "") -> list[dict]:
        conn = self._conn()
        if status:
            rows = conn.execute("SELECT * FROM licensees WHERE status = ? ORDER BY created_at DESC", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM licensees ORDER BY created_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_licensee(self, licensee_id: int):
        conn = self._conn()
        row = conn.execute("SELECT * FROM licensees WHERE id = ?", (licensee_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_licensee_by_email(self, email: str):
        conn = self._conn()
        row = conn.execute("SELECT * FROM licensees WHERE email = ?", (email,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_licensee_branding(
        self,
        licensee_id: int,
        *,
        custom_domain: Optional[str] = None,
        logo_url: Optional[str] = None,
        primary_color: Optional[str] = None,
        footer_html: Optional[str] = None,
        sender_name: Optional[str] = None,
        reply_to_email: Optional[str] = None,
    ) -> None:
        """Update branding fields on a licensee. Setting custom_domain to a
        new non-empty value clears the verified flag and generates a fresh
        verification token (caller must check for this and surface the
        token in the admin UI for DNS TXT setup).
        """
        sets = []
        params: list = []
        if custom_domain is not None:
            sets.append("custom_domain = ?")
            params.append(custom_domain.strip().lower())
            # Reset verification when domain changes
            sets.append("domain_verified = 0")
            import secrets as _s
            sets.append("domain_verify_token = ?")
            params.append(_s.token_hex(16))
        if logo_url is not None:
            sets.append("logo_url = ?")
            params.append(logo_url)
        if primary_color is not None:
            sets.append("primary_color = ?")
            params.append(primary_color)
        if footer_html is not None:
            sets.append("footer_html = ?")
            params.append(footer_html)
        if sender_name is not None:
            sets.append("sender_name = ?")
            params.append(sender_name)
        if reply_to_email is not None:
            sets.append("reply_to_email = ?")
            params.append(reply_to_email)
        if not sets:
            return
        sets.append("updated_at = CURRENT_TIMESTAMP")
        sql = f"UPDATE licensees SET {', '.join(sets)} WHERE id = ?"
        params.append(licensee_id)
        conn = self._conn()
        conn.execute(sql, tuple(params))
        conn.commit()
        conn.close()

    def mark_licensee_domain_verified(self, licensee_id: int) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE licensees SET domain_verified = 1, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (licensee_id,),
        )
        conn.commit()
        conn.close()

    def update_licensee_status(self, licensee_id: int, status: str) -> None:
        conn = self._conn()
        updates = "status = ?, updated_at = CURRENT_TIMESTAMP"
        params = [status]
        if status == "active":
            updates += ", activated_at = CURRENT_TIMESTAMP"
        conn.execute(f"UPDATE licensees SET {updates} WHERE id = ?", (*params, licensee_id))
        conn.commit()
        conn.close()

    def get_license_revenue(self, licensee_id: int) -> list[dict]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM license_revenue WHERE licensee_id = ? ORDER BY month DESC", (licensee_id,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def create_license_revenue(self, licensee_id: int, month: str, sponsor_cents: int = 0, affiliate_cents: int = 0, subscriber_cents: int = 0, share_pct: float = 20.0) -> int:
        total = sponsor_cents + affiliate_cents + subscriber_cents
        platform_share = int(total * share_pct / 100)
        licensee_share = total - platform_share
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO license_revenue (licensee_id, month, sponsor_revenue_cents, affiliate_revenue_cents, subscriber_revenue_cents, platform_share_cents, licensee_share_cents)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (licensee_id, month, sponsor_cents, affiliate_cents, subscriber_cents, platform_share, licensee_share),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    # ---- Artist Newsletter Product ----

    def get_artist_newsletter(self, newsletter_id: int):
        conn = self._conn()
        row = conn.execute("SELECT * FROM artist_newsletters WHERE id = ?", (newsletter_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_artist_newsletter_by_slug(self, slug: str):
        conn = self._conn()
        row = conn.execute("SELECT * FROM artist_newsletters WHERE slug = ?", (slug,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_artist_newsletters(self, status: str = "") -> list[dict]:
        conn = self._conn()
        if status:
            rows = conn.execute("SELECT * FROM artist_newsletters WHERE status = ? ORDER BY created_at DESC", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM artist_newsletters ORDER BY created_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def create_artist_newsletter(self, artist_name: str, slug: str, artist_profile_id: int = 0, brand_color: str = "#e8645a", tagline: str = "", template_style: str = "minimal") -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO artist_newsletters (artist_name, slug, artist_profile_id, brand_color, tagline, template_style, status) VALUES (?, ?, ?, ?, ?, ?, 'setup')",
            (artist_name, slug, artist_profile_id or None, brand_color, tagline, template_style),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def update_artist_newsletter(self, newsletter_id: int, **kwargs) -> None:
        allowed = {"artist_name", "brand_color", "tagline", "template_style", "schedule", "status", "logo_url"}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        conn = self._conn()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE artist_newsletters SET {set_clause} WHERE id = ?", (*fields.values(), newsletter_id))
        conn.commit()
        conn.close()

    def get_artist_nl_subscriber_count(self, newsletter_id: int) -> int:
        conn = self._conn()
        row = conn.execute("SELECT COUNT(*) as count FROM artist_newsletter_subscribers WHERE newsletter_id = ? AND status = 'active'", (newsletter_id,)).fetchone()
        conn.close()
        return dict(row)["count"] if row else 0

    def add_artist_nl_subscriber(self, newsletter_id: int, email: str, first_name: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT OR IGNORE INTO artist_newsletter_subscribers (newsletter_id, email, first_name) VALUES (?, ?, ?)",
            (newsletter_id, email, first_name),
        )
        conn.commit()
        # Update count
        count = conn.execute("SELECT COUNT(*) FROM artist_newsletter_subscribers WHERE newsletter_id = ? AND status = 'active'", (newsletter_id,)).fetchone()[0]
        conn.execute("UPDATE artist_newsletters SET subscriber_count = ? WHERE id = ?", (count, newsletter_id))
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_artist_nl_issues(self, newsletter_id: int) -> list[dict]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM artist_newsletter_issues WHERE newsletter_id = ? ORDER BY issue_number DESC", (newsletter_id,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def create_artist_nl_issue(self, newsletter_id: int, subject: str, html_content: str = "", plain_text: str = "") -> int:
        conn = self._conn()
        # Get next issue number
        row = conn.execute("SELECT COALESCE(MAX(issue_number), 0) + 1 as next_num FROM artist_newsletter_issues WHERE newsletter_id = ?", (newsletter_id,)).fetchone()
        next_num = dict(row)["next_num"]
        cur = conn.execute(
            "INSERT INTO artist_newsletter_issues (newsletter_id, issue_number, subject, html_content, plain_text) VALUES (?, ?, ?, ?, ?)",
            (newsletter_id, next_num, subject, html_content, plain_text),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_artist_nl_templates(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM artist_newsletter_templates ORDER BY is_default DESC, name").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Artist Newsletter Links & Revenue ----

    def get_artist_nl_links(self, newsletter_id: int) -> list[dict]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM artist_newsletter_links WHERE newsletter_id = ? AND is_active = 1 ORDER BY sort_order", (newsletter_id,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def add_artist_nl_link(self, newsletter_id: int, link_type: str, label: str, url: str, sort_order: int = 0) -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO artist_newsletter_links (newsletter_id, link_type, label, url, sort_order) VALUES (?, ?, ?, ?, ?)",
            (newsletter_id, link_type, label, url, sort_order),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def delete_artist_nl_link(self, link_id: int) -> None:
        conn = self._conn()
        conn.execute("UPDATE artist_newsletter_links SET is_active = 0 WHERE id = ?", (link_id,))
        conn.commit()
        conn.close()

    def get_artist_nl_subscribers(self, newsletter_id: int, limit: int = 100) -> list[dict]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM artist_newsletter_subscribers WHERE newsletter_id = ? ORDER BY subscribed_at DESC LIMIT ?", (newsletter_id, limit)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_artist_nl_revenue(self, newsletter_id: int) -> list[dict]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM artist_newsletter_revenue WHERE newsletter_id = ? ORDER BY month DESC", (newsletter_id,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_artist_nl_revenue_total(self, newsletter_id: int) -> dict:
        conn = self._conn()
        row = conn.execute(
            """SELECT COALESCE(SUM(sponsor_revenue_cents),0) as sponsor,
                      COALESCE(SUM(affiliate_revenue_cents),0) as affiliate,
                      COALESCE(SUM(merch_revenue_cents),0) as merch,
                      COALESCE(SUM(ticket_revenue_cents),0) as tickets,
                      COALESCE(SUM(total_revenue_cents),0) as total
               FROM artist_newsletter_revenue WHERE newsletter_id = ?""",
            (newsletter_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else {"sponsor": 0, "affiliate": 0, "merch": 0, "tickets": 0, "total": 0}

    # ---- Marketing & Promotion ----

    def get_marketing_campaigns(self, campaign_type: str = "", status: str = "", limit: int = 50) -> list[dict]:
        conn = self._conn()
        query = "SELECT * FROM marketing_campaigns"
        conditions, params = [], []
        if campaign_type:
            conditions.append("campaign_type = ?")
            params.append(campaign_type)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def create_marketing_campaign(self, name: str, campaign_type: str, channel: str = "email", target_audience: str = "", goal_description: str = "", goal_target: int = 0, template_content: str = "", notes: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO marketing_campaigns (name, campaign_type, channel, target_audience, goal_description, goal_target, template_content, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, campaign_type, channel, target_audience, goal_description, goal_target, template_content, notes),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def update_campaign_status(self, campaign_id: int, status: str) -> None:
        conn = self._conn()
        updates = "status = ?, updated_at = CURRENT_TIMESTAMP"
        params = [status]
        if status == "active":
            updates += ", started_at = CURRENT_TIMESTAMP"
        elif status == "completed":
            updates += ", completed_at = CURRENT_TIMESTAMP"
        conn.execute(f"UPDATE marketing_campaigns SET {updates} WHERE id = ?", (*params, campaign_id))
        conn.commit()
        conn.close()

    def get_marketing_templates(self, template_type: str = "", category: str = "") -> list[dict]:
        conn = self._conn()
        query = "SELECT * FROM marketing_templates WHERE is_active = 1"
        params = []
        if template_type:
            query += " AND template_type = ?"
            params.append(template_type)
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY category, name"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_marketing_template(self, template_id: int):
        conn = self._conn()
        row = conn.execute("SELECT * FROM marketing_templates WHERE id = ?", (template_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def create_sponsor_prospect(self, company_name: str, contact_name: str = "", contact_email: str = "", contact_phone: str = "", website: str = "", category: str = "general", target_editions: str = "", estimated_budget: str = "", source: str = "manual", notes: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO sponsor_prospects (company_name, contact_name, contact_email, contact_phone, website, category, target_editions, estimated_budget, source, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (company_name, contact_name, contact_email, contact_phone, website, category, target_editions, estimated_budget, source, notes),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_sponsor_prospects(self, status: str = "", limit: int = 50) -> list[dict]:
        conn = self._conn()
        if status:
            rows = conn.execute("SELECT * FROM sponsor_prospects WHERE status = ? ORDER BY updated_at DESC LIMIT ?", (status, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM sponsor_prospects ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_prospect_status(self, prospect_id: int, status: str) -> None:
        conn = self._conn()
        conn.execute("UPDATE sponsor_prospects SET status = ?, updated_at = CURRENT_TIMESTAMP, last_contacted_at = CURRENT_TIMESTAMP WHERE id = ?", (status, prospect_id))
        conn.commit()
        conn.close()

    # ---- Cross-promo partners (PromotionAgent persistence) ----

    def create_cross_promo_partner(self, partner_name: str, partner_type: str = "newsletter", audience_size: str = "", audience_overlap: str = "", pitch_idea: str = "", contact_url: str = "", edition_slug: str = "", source: str = "manual", notes: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO cross_promo_partners (partner_name, partner_type, audience_size, audience_overlap, pitch_idea, contact_url, edition_slug, source, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (partner_name, partner_type, audience_size, audience_overlap, pitch_idea, contact_url, edition_slug, source, notes),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_cross_promo_partners(self, edition_slug: str = "", status: str = "", limit: int = 100) -> list[dict]:
        conn = self._conn()
        sql = "SELECT * FROM cross_promo_partners WHERE 1=1"
        params: list = []
        if edition_slug:
            sql += " AND edition_slug = ?"
            params.append(edition_slug)
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_cross_promo_partner_status(self, partner_id: int, status: str) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE cross_promo_partners SET status = ?, updated_at = CURRENT_TIMESTAMP, last_contacted_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, partner_id),
        )
        conn.commit()
        conn.close()

    # ---- Admin settings (runtime-mutable admin config) ----

    def get_admin_setting(self, key: str) -> str:
        """Return the stored value for `key`, or '' if not set."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT value FROM admin_settings WHERE key = ?", (key,),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return ""
        return row["value"] or ""

    def set_admin_setting(self, key: str, value: str) -> None:
        """Insert or update an admin setting.

        PG branch ends with ``RETURNING key`` to defeat the adapter's
        ``RETURNING id`` auto-append (repository.py:51-52) — this table
        has no ``id`` column, PK is ``key``.
        """
        conn = self._conn()
        try:
            if self._is_pg:
                conn.execute(
                    "INSERT INTO admin_settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, "
                    "updated_at = CURRENT_TIMESTAMP "
                    "RETURNING key",
                    (key, value),
                )
            else:
                conn.execute(
                    "INSERT INTO admin_settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                    "updated_at = CURRENT_TIMESTAMP",
                    (key, value),
                )
            conn.commit()
        finally:
            conn.close()

    # ---- Cost telemetry ----

    def get_cost_stats_by_edition(self, since_days: int = 30) -> list[dict]:
        """Aggregate LLM token usage per edition over a rolling window.

        Joins agent_output_log (tokens_used) → agent_tasks (issue_id) →
        issues (edition_slug). Returns one row per edition with:
          - edition_slug
          - issue_count: DISTINCT issues that had at least one logged call
          - total_tokens: SUM of tokens_used across all agent calls
          - avg_tokens_per_issue: total_tokens / issue_count

        Excludes tasks with no issue_id (orchestrator-level work not
        attributable to a specific edition).
        """
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        conn = self._conn()
        try:
            # Table alias 'at' is reserved in PostgreSQL (used in
            # 'TIMESTAMP AT TIME ZONE' syntax). Use 't' instead —
            # unreserved in both SQLite and Postgres.
            rows = conn.execute(
                "SELECT i.edition_slug AS edition_slug, "
                "       COUNT(DISTINCT i.id) AS issue_count, "
                "       COALESCE(SUM(aol.tokens_used), 0) AS total_tokens "
                "FROM agent_output_log aol "
                "JOIN agent_tasks t ON t.id = aol.task_id "
                "JOIN issues i ON i.id = t.issue_id "
                "WHERE aol.created_at >= ? AND i.edition_slug != '' "
                "GROUP BY i.edition_slug "
                "ORDER BY i.edition_slug",
                (cutoff,),
            ).fetchall()
        finally:
            conn.close()
        out: list[dict] = []
        for r in rows:
            d = dict(r)
            ic = d.get("issue_count") or 0
            d["avg_tokens_per_issue"] = int(d["total_tokens"] / ic) if ic else 0
            out.append(d)
        return out

    def get_subscriber_counts_by_edition(self) -> dict[str, int]:
        """Return {edition_slug: active subscriber count} for all editions.

        An edition with zero subscribers still appears in the output
        (count=0), so the cost dashboard can render every edition
        uniformly without nil-handling downstream.
        """
        conn = self._conn()
        try:
            editions = conn.execute(
                "SELECT slug FROM newsletter_editions"
            ).fetchall()
            counts = conn.execute(
                "SELECT ne.slug AS slug, COUNT(DISTINCT s.id) AS c "
                "FROM subscribers s "
                "JOIN subscriber_editions se ON se.subscriber_id = s.id "
                "JOIN newsletter_editions ne ON ne.id = se.edition_id "
                "WHERE s.status = 'active' "
                "GROUP BY ne.slug"
            ).fetchall()
        finally:
            conn.close()
        by_slug = {r["slug"]: 0 for r in editions}
        for r in counts:
            by_slug[r["slug"]] = r["c"]
        return by_slug

    # ---- Feature flags (runtime-mutable feature toggles) ----
    # Table schema (from db/schema.sql): feature_flags(
    #   name TEXT PK, is_active INTEGER, rollout_percent INTEGER,
    #   description TEXT, updated_at TIMESTAMP
    # ). We expose a simple on/off API here; rollout_percent stays at
    # its default of 100 for now — percentage rollouts are future work.

    def get_feature_flag(self, key: str) -> bool | None:
        """Return the DB-stored flag value, or None if no row exists.

        None distinguishes 'never set' (fall back to config default)
        from 'explicitly set to false'.
        """
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT is_active FROM feature_flags WHERE name = ?", (key,),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return bool(row["is_active"])

    def set_feature_flag(
        self, key: str, enabled: bool, description: str = "", category: str = "",
    ) -> None:
        """Insert or update a feature flag row.

        ``category`` is accepted for API symmetry with the callers but
        the underlying table doesn't store it — category lives in
        :data:`weeklyamp.core.feature_flags.FLAG_METADATA`.

        Important: the PG branch ends with ``RETURNING name``. This
        defeats the ``_PgConnAdapter`` auto-append of ``RETURNING id``
        (repository.py:51-52), which would otherwise reference a
        non-existent column on tables keyed by ``name``.
        """
        del category  # category lives in FLAG_METADATA, not the DB
        conn = self._conn()
        try:
            if self._is_pg:
                conn.execute(
                    "INSERT INTO feature_flags (name, is_active, description) "
                    "VALUES (?, ?, ?) "
                    "ON CONFLICT (name) DO UPDATE SET "
                    "is_active = EXCLUDED.is_active, "
                    "description = EXCLUDED.description, "
                    "updated_at = CURRENT_TIMESTAMP "
                    "RETURNING name",
                    (key, 1 if enabled else 0, description),
                )
            else:
                conn.execute(
                    "INSERT INTO feature_flags (name, is_active, description) "
                    "VALUES (?, ?, ?) "
                    "ON CONFLICT(name) DO UPDATE SET "
                    "is_active = excluded.is_active, "
                    "description = excluded.description, "
                    "updated_at = CURRENT_TIMESTAMP",
                    (key, 1 if enabled else 0, description),
                )
            conn.commit()
        finally:
            conn.close()

    def list_feature_flags(self) -> list[dict]:
        """Return all feature flag rows (for the admin UI)."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT name, is_active, description, updated_at "
                "FROM feature_flags ORDER BY name"
            ).fetchall()
        finally:
            conn.close()
        return [
            {
                "key": r["name"],
                "enabled": bool(r["is_active"]),
                "description": r["description"] or "",
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]

    def log_outreach(self, campaign_id: int = 0, channel: str = "email", recipient_email: str = "", recipient_phone: str = "", recipient_name: str = "", recipient_type: str = "subscriber", status: str = "sent") -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO outreach_log (campaign_id, channel, recipient_email, recipient_phone, recipient_name, recipient_type, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (campaign_id or None, channel, recipient_email, recipient_phone, recipient_name, recipient_type, status),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    # ---- Notifications ----

    def create_notification(self, title: str, message: str = "", notification_type: str = "info", category: str = "system", action_url: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO notifications (title, message, notification_type, category, action_url) VALUES (?, ?, ?, ?, ?)",
            (title, message, notification_type, category, action_url),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_notifications(self, unread_only: bool = False, limit: int = 20) -> list[dict]:
        conn = self._conn()
        query = "SELECT * FROM notifications"
        if unread_only:
            query += " WHERE is_read = 0"
        query += " ORDER BY created_at DESC LIMIT ?"
        rows = conn.execute(query, (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_unread_count(self) -> int:
        conn = self._conn()
        row = conn.execute("SELECT COUNT(*) as count FROM notifications WHERE is_read = 0").fetchone()
        conn.close()
        return dict(row)["count"] if row else 0

    def mark_notification_read(self, notification_id: int) -> None:
        conn = self._conn()
        conn.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notification_id,))
        conn.commit()
        conn.close()

    def mark_all_notifications_read(self) -> None:
        conn = self._conn()
        conn.execute("UPDATE notifications SET is_read = 1 WHERE is_read = 0")
        conn.commit()
        conn.close()

    # ---- Subscriber Milestones ----

    def check_and_create_milestones(self, subscriber_id: int) -> list[str]:
        """Check if subscriber has earned any new milestones. Returns list of new milestone types."""
        conn = self._conn()
        sub = conn.execute("SELECT * FROM subscribers WHERE id = ?", (subscriber_id,)).fetchone()
        if not sub:
            conn.close()
            return []

        sub = dict(sub)
        new_milestones = []
        from datetime import datetime, timedelta
        now = datetime.now()
        subscribed = sub.get("subscribed_at") or sub.get("synced_at") or ""

        if subscribed:
            try:
                sub_date = datetime.fromisoformat(str(subscribed).replace("Z", "+00:00").split("+")[0])
                days = (now - sub_date).days

                milestone_map = [
                    (7, "1_week"), (30, "1_month"), (90, "3_months"),
                    (180, "6_months"), (365, "1_year"),
                ]

                for threshold, mtype in milestone_map:
                    if days >= threshold:
                        existing = conn.execute(
                            "SELECT id FROM subscriber_milestones WHERE subscriber_id = ? AND milestone_type = ?",
                            (subscriber_id, mtype),
                        ).fetchone()
                        if not existing:
                            conn.execute(
                                "INSERT INTO subscriber_milestones (subscriber_id, milestone_type) VALUES (?, ?)",
                                (subscriber_id, mtype),
                            )
                            new_milestones.append(mtype)
            except Exception:
                pass

        conn.commit()
        conn.close()
        return new_milestones

    def get_subscriber_milestones(self, subscriber_id: int) -> list[dict]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM subscriber_milestones WHERE subscriber_id = ? ORDER BY achieved_at", (subscriber_id,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Unsubscribe Surveys ----

    def save_unsubscribe_survey(self, email: str, reason: str, feedback: str = "", subscriber_id: int = 0) -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO unsubscribe_surveys (subscriber_id, email, reason, feedback) VALUES (?, ?, ?, ?)",
            (subscriber_id or None, email, reason, feedback),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_unsubscribe_surveys(self, limit: int = 50) -> list[dict]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM unsubscribe_surveys ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_outreach_stats(self) -> dict:
        conn = self._conn()
        total = conn.execute("SELECT COUNT(*) as count FROM outreach_log").fetchone()
        by_status = conn.execute("SELECT status, COUNT(*) as count FROM outreach_log GROUP BY status ORDER BY count DESC").fetchall()
        by_channel = conn.execute("SELECT channel, COUNT(*) as count FROM outreach_log GROUP BY channel ORDER BY count DESC").fetchall()
        campaigns = conn.execute("SELECT COUNT(*) as count FROM marketing_campaigns").fetchone()
        active = conn.execute("SELECT COUNT(*) as count FROM marketing_campaigns WHERE status = 'active'").fetchone()
        prospects = conn.execute("SELECT COUNT(*) as count FROM sponsor_prospects").fetchone()
        conn.close()
        return {
            "total_outreach": dict(total)["count"] if total else 0,
            "by_status": [dict(r) for r in by_status],
            "by_channel": [dict(r) for r in by_channel],
            "total_campaigns": dict(campaigns)["count"] if campaigns else 0,
            "active_campaigns": dict(active)["count"] if active else 0,
            "total_prospects": dict(prospects)["count"] if prospects else 0,
        }

    # ---- Feature flags ----

    # ---- Admin audit log ----

    def log_admin_action(
        self,
        action: str,
        actor_type: str = "admin",
        actor_id: str = "",
        target_type: str = "",
        target_id: str = "",
        ip_address: str = "",
        user_agent: str = "",
        detail: str = "",
    ) -> None:
        """Record an admin/licensee/system action for audit trail.

        Best-effort: swallow errors so audit logging never blocks the
        underlying operation. A failure to log an action is strictly
        less bad than the action itself failing because logging broke.
        """
        try:
            conn = self._conn()
            conn.execute(
                "INSERT INTO admin_audit_log "
                "(actor_type, actor_id, action, target_type, target_id, "
                " ip_address, user_agent, detail) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    actor_type, actor_id, action, target_type, target_id,
                    ip_address, (user_agent or "")[:500], (detail or "")[:2000],
                ),
            )
            conn.commit()
            conn.close()
        except Exception:
            logger.warning("Failed to write audit log entry", exc_info=True)

    def get_audit_log(
        self,
        limit: int = 100,
        actor_type: str = "",
        action_like: str = "",
    ) -> list[dict]:
        """Return recent audit log entries, optionally filtered."""
        conn = self._conn()
        sql = "SELECT * FROM admin_audit_log WHERE 1=1"
        params: list = []
        if actor_type:
            sql += " AND actor_type = ?"
            params.append(actor_type)
        if action_like:
            sql += " AND action LIKE ?"
            params.append(f"%{action_like}%")
        sql += " ORDER BY occurred_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, tuple(params)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- Webhook idempotency ----

    def has_processed_webhook_event(self, event_id: str) -> bool:
        """Return True if this webhook event_id has already been processed."""
        if not event_id:
            return False
        conn = self._conn()
        row = conn.execute(
            "SELECT 1 FROM payment_webhook_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        conn.close()
        return row is not None

    def record_webhook_event(self, event_id: str, event_type: str = "") -> None:
        """Record that a webhook event_id has been processed.

        Swallows unique-constraint violations so that a double-submit race
        between two workers is harmless — the first write wins and the
        second is silently ignored.
        """
        if not event_id:
            return
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO payment_webhook_events (event_id, event_type) VALUES (?, ?)",
                (event_id, event_type),
            )
            conn.commit()
        except Exception:
            # Most likely a unique constraint violation from a concurrent retry
            conn.rollback()
        finally:
            conn.close()
