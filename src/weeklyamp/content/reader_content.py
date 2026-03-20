"""Reader-submitted content system for newsletter engagement.

Allows readers to submit hot takes, reviews, tips, questions, stories
which can be reviewed, approved, and featured in newsletter issues.
INACTIVE by default — enable via config.
"""

from __future__ import annotations

import logging
from typing import Optional

from weeklyamp.core.models import ReaderContentConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)

_CONTENT_TYPE_LABELS = {
    "hot_take": "Hot Take",
    "review": "Album Review",
    "tip": "Tip",
    "question": "Question",
    "story": "Story",
}

_CONTENT_TYPE_COLORS = {
    "hot_take": "#EF4444",
    "review": "#8B5CF6",
    "tip": "#10B981",
    "question": "#3B82F6",
    "story": "#F59E0B",
}


class ReaderContentManager:
    """Manage reader-submitted content for newsletters."""

    def __init__(self, repo: Repository, config: ReaderContentConfig) -> None:
        self.repo = repo
        self.config = config

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------

    def submit_contribution(
        self,
        email: str,
        name: str,
        content_type: str,
        content: str,
        edition_slug: str = "",
    ) -> Optional[int]:
        """Create a reader contribution.  Returns the contribution id."""
        if not self.config.enabled:
            logger.info("Reader content disabled — skipping submit_contribution")
            return None

        if content_type not in _CONTENT_TYPE_LABELS:
            raise ValueError(f"Invalid content type: {content_type}")

        # Look up subscriber id by email (optional)
        subscriber_id = None
        conn = self.repo._conn()
        try:
            sub = conn.execute(
                "SELECT id FROM subscribers WHERE email = ?", (email,)
            ).fetchone()
            if sub:
                subscriber_id = sub["id"]

            status = "approved" if self.config.auto_approve else "submitted"

            cur = conn.execute(
                """INSERT INTO reader_contributions
                   (subscriber_id, email, name, content_type, content,
                    edition_slug, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (subscriber_id, email, name, content_type, content,
                 edition_slug, status),
            )
            conn.commit()
            contrib_id = cur.lastrowid
            logger.info("Reader contribution %d from %s (%s)", contrib_id, email, content_type)
            return contrib_id
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Review
    # ------------------------------------------------------------------

    def get_pending(self) -> list[dict]:
        """Get submitted contributions awaiting review."""
        conn = self.repo._conn()
        try:
            rows = conn.execute(
                """SELECT * FROM reader_contributions
                   WHERE status = 'submitted'
                   ORDER BY created_at DESC"""
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_all(self, limit: int = 100) -> list[dict]:
        """Get all contributions."""
        conn = self.repo._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM reader_contributions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_contribution(self, contrib_id: int) -> Optional[dict]:
        """Get a single contribution."""
        conn = self.repo._conn()
        try:
            row = conn.execute(
                "SELECT * FROM reader_contributions WHERE id = ?", (contrib_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def approve(self, contrib_id: int, target_issue_id: Optional[int] = None) -> None:
        """Approve a contribution for potential featuring."""
        conn = self.repo._conn()
        try:
            if target_issue_id:
                conn.execute(
                    "UPDATE reader_contributions SET status = 'approved', target_issue_id = ? WHERE id = ?",
                    (target_issue_id, contrib_id),
                )
            else:
                conn.execute(
                    "UPDATE reader_contributions SET status = 'approved' WHERE id = ?",
                    (contrib_id,),
                )
            conn.commit()
            logger.info("Approved contribution %d", contrib_id)
        finally:
            conn.close()

    def reject(self, contrib_id: int) -> None:
        """Reject a contribution."""
        conn = self.repo._conn()
        try:
            conn.execute(
                "UPDATE reader_contributions SET status = 'rejected' WHERE id = ?",
                (contrib_id,),
            )
            conn.commit()
            logger.info("Rejected contribution %d", contrib_id)
        finally:
            conn.close()

    def feature_in_issue(self, contrib_id: int, issue_id: int) -> None:
        """Mark a contribution as featured in a specific issue."""
        conn = self.repo._conn()
        try:
            conn.execute(
                """UPDATE reader_contributions
                   SET status = 'featured', featured_in_issue_id = ?
                   WHERE id = ?""",
                (issue_id, contrib_id),
            )
            conn.commit()
            logger.info("Featured contribution %d in issue %d", contrib_id, issue_id)
        finally:
            conn.close()

    def get_featured(self, issue_id: int) -> list[dict]:
        """Get featured contributions for an issue."""
        conn = self.repo._conn()
        try:
            rows = conn.execute(
                """SELECT * FROM reader_contributions
                   WHERE featured_in_issue_id = ? AND status = 'featured'
                   ORDER BY created_at""",
                (issue_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Email rendering
    # ------------------------------------------------------------------

    def render_reader_content_html(self, contributions: list[dict]) -> str:
        """Generate email-safe HTML block for reader content in a newsletter.

        Returns inline-styled table HTML with each contribution rendered as a
        reader name, type badge, and their content.
        """
        if not contributions:
            return ""

        rows_html = ""
        for contrib in contributions:
            ctype = contrib.get("content_type", "hot_take")
            badge_label = _CONTENT_TYPE_LABELS.get(ctype, ctype.title())
            badge_color = _CONTENT_TYPE_COLORS.get(ctype, "#6B7280")
            name = contrib.get("name", "Anonymous Reader")
            content = contrib.get("content", "")

            rows_html += f"""
            <tr>
                <td style="padding:12px 24px;border-bottom:1px solid #e5e7eb;">
                    <div style="margin-bottom:6px;">
                        <span style="display:inline-block;padding:2px 8px;
                                     background-color:{badge_color};color:#ffffff;
                                     font-family:Arial,sans-serif;font-size:11px;
                                     font-weight:700;border-radius:4px;
                                     text-transform:uppercase;letter-spacing:0.5px;">
                            {badge_label}
                        </span>
                        <span style="font-family:Arial,sans-serif;font-size:13px;
                                     color:#6B7280;margin-left:8px;">
                            from <strong style="color:#111827;">{name}</strong>
                        </span>
                    </div>
                    <div style="font-family:Arial,sans-serif;font-size:15px;
                                color:#374151;line-height:1.5;">
                        {content}
                    </div>
                </td>
            </tr>"""

        html = f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0"
       style="max-width:560px;margin:20px auto;background-color:#f9fafb;
              border-radius:8px;border:1px solid #e5e7eb;">
    <tr>
        <td style="padding:16px 24px 8px;text-align:center;">
            <span style="font-family:Arial,sans-serif;font-size:12px;
                         font-weight:700;text-transform:uppercase;
                         letter-spacing:1px;color:#e8645a;">
                FROM OUR READERS
            </span>
        </td>
    </tr>
    {rows_html}
    <tr>
        <td style="padding:16px 24px;text-align:center;">
            <a href="{{{{contribute_url}}}}"
               style="display:inline-block;padding:10px 24px;
                      background-color:#e8645a;color:#ffffff;
                      text-decoration:none;border-radius:6px;
                      font-family:Arial,sans-serif;font-size:14px;
                      font-weight:600;">
                Submit Your Own &rarr;
            </a>
        </td>
    </tr>
</table>"""
        return html
