"""CRUD operations for all WEEKLYAMP database tables."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Optional

from weeklyamp.core.database import get_connection


class Repository:
    """Central data-access layer for the WEEKLYAMP database."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self.db_path)

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
        send_day: str = "", issue_template: str = "",
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO issues (issue_number, title, week_id, send_day, issue_template)
               VALUES (?, ?, ?, ?, ?)""",
            (issue_number, title, week_id, send_day, issue_template),
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

    def update_assembled_beehiiv(self, assembled_id: int, post_id: str) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE assembled_issues SET beehiiv_post_id = ?, published_at = CURRENT_TIMESTAMP WHERE id = ?",
            (post_id, assembled_id),
        )
        conn.commit()
        conn.close()

    # ---- Subscribers ----

    def upsert_subscriber(self, email: str, beehiiv_id: str = "", status: str = "active") -> None:
        conn = self._conn()
        conn.execute(
            """INSERT INTO subscribers (email, beehiiv_id, status, synced_at)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(email) DO UPDATE SET
                   beehiiv_id = excluded.beehiiv_id,
                   status = excluded.status,
                   synced_at = CURRENT_TIMESTAMP""",
            (email, beehiiv_id, status),
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

    # ---- Engagement Metrics ----

    def save_engagement(
        self, issue_id: int, beehiiv_post_id: str,
        sends: int = 0, opens: int = 0, clicks: int = 0,
        open_rate: float = 0.0, click_rate: float = 0.0,
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO engagement_metrics
               (issue_id, beehiiv_post_id, sends, opens, clicks, open_rate, click_rate)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (issue_id, beehiiv_post_id, sends, opens, clicks, open_rate, click_rate),
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

    def upsert_send_schedule(self, day_of_week: str, label: str = "", section_slugs: str = "") -> int:
        conn = self._conn()
        # Check if exists
        existing = conn.execute(
            "SELECT id FROM send_schedule WHERE day_of_week = ?", (day_of_week,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE send_schedule SET label = ?, section_slugs = ?, is_active = 1 WHERE day_of_week = ?",
                (label, section_slugs, day_of_week),
            )
            conn.commit()
            row_id = existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO send_schedule (day_of_week, label, section_slugs) VALUES (?, ?, ?)",
                (day_of_week, label, section_slugs),
            )
            conn.commit()
            row_id = cur.lastrowid
        conn.close()
        return row_id

    def delete_send_schedule(self, day_of_week: str) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM send_schedule WHERE day_of_week = ?", (day_of_week,))
        conn.commit()
        conn.close()

    # ---- Sponsor Blocks ----

    def create_sponsor_block(
        self, issue_id: int, position: str = "mid", sponsor_name: str = "",
        headline: str = "", body_html: str = "", cta_url: str = "",
        cta_text: str = "Learn More", image_url: str = "",
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO sponsor_blocks
               (issue_id, position, sponsor_name, headline, body_html, cta_url, cta_text, image_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (issue_id, position, sponsor_name, headline, body_html, cta_url, cta_text, image_url),
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

    def update_sponsor_block(self, block_id: int, **kwargs) -> None:
        if not kwargs:
            return
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
                SUM(CASE WHEN status = 'paid' THEN rate_cents ELSE 0 END) as paid_cents,
                SUM(CASE WHEN status IN ('booked','confirmed','delivered','invoiced') THEN rate_cents ELSE 0 END) as pipeline_cents,
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

    def update_agent(self, agent_id: int, **kwargs) -> None:
        if not kwargs:
            return
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
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [post_id]
        conn = self._conn()
        conn.execute(f"UPDATE social_posts SET {sets} WHERE id = ?", vals)
        conn.commit()
        conn.close()

    # ---- Stats ----

    def get_table_counts(self) -> dict[str, int]:
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
