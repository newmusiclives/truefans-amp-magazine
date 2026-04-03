"""CRUD operations for all WEEKLYAMP database tables."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Optional

from weeklyamp.core.database import get_connection


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

    def get_subscriber_count(self) -> int:
        conn = self._conn()
        row = conn.execute("SELECT COUNT(*) as c FROM subscribers WHERE status = 'active'").fetchone()
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
               GROUP BY sb.id
               ORDER BY clicks DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

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

    def create_billing_record(self, subscriber_id: int, tier_id: int, stripe_customer_id: str = "", stripe_subscription_id: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO subscriber_billing (subscriber_id, tier_id, stripe_customer_id, stripe_subscription_id) VALUES (?, ?, ?, ?)",
            (subscriber_id, tier_id, stripe_customer_id, stripe_subscription_id),
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

    def update_billing_status(self, stripe_subscription_id: str, status: str, current_period_end: str = "") -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE subscriber_billing SET status = ?, current_period_end = ?, updated_at = CURRENT_TIMESTAMP WHERE stripe_subscription_id = ?",
            (status, current_period_end, stripe_subscription_id),
        )
        conn.commit()
        conn.close()

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
