"""Cross-edition promotional content generator.

Generates "Also from TrueFans" HTML blocks showing teaser snippets
from the other two editions. INACTIVE by default — returns empty
string when referrals/cross-promo is not configured.
"""

from __future__ import annotations

import logging
from html import escape

from weeklyamp.core.models import AppConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)

# Edition display metadata
_EDITION_META = {
    "fan": {
        "label": "Fan Edition",
        "color": "#e8645a",
        "emoji": "&#127911;",
    },
    "artist": {
        "label": "Artist Edition",
        "color": "#7c5cfc",
        "emoji": "&#127928;",
    },
    "industry": {
        "label": "Industry Edition",
        "color": "#f59e0b",
        "emoji": "&#128200;",
    },
}


def _get_latest_issue_snippet(repo: Repository, edition_slug: str) -> dict | None:
    """Fetch the latest assembled/published issue for an edition and return a snippet.

    Returns a dict with keys: edition_slug, title, snippet, issue_number, or None.
    """
    conn = repo._conn()
    try:
        row = conn.execute(
            """SELECT i.id, i.issue_number, i.subject_line
               FROM issues i
               JOIN editions e ON i.edition_id = e.id
               WHERE e.slug = ? AND i.status IN ('assembled', 'published')
               ORDER BY i.created_at DESC
               LIMIT 1""",
            (edition_slug,),
        ).fetchone()
        conn.close()
        if not row:
            return None

        title = row["subject_line"] or f"Issue #{row['issue_number']}"

        # Try to get a short preview from the first draft section
        conn2 = repo._conn()
        draft_row = conn2.execute(
            """SELECT d.content
               FROM drafts d
               WHERE d.issue_id = ? AND d.status = 'approved'
               ORDER BY d.section_order ASC, d.created_at ASC
               LIMIT 1""",
            (row["id"],),
        ).fetchone()
        conn2.close()

        snippet = ""
        if draft_row and draft_row["content"]:
            # Extract first meaningful line as snippet
            lines = draft_row["content"].split("\n")
            for line in lines:
                clean = line.strip()
                if clean and not clean.startswith("#") and not clean.startswith("**") and not clean.startswith("*By "):
                    # Strip markdown
                    import re
                    clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', clean)
                    clean = clean.replace("**", "").replace("*", "")
                    if len(clean) > 120:
                        clean = clean[:120].rsplit(" ", 1)[0] + "..."
                    snippet = clean
                    break

        if not snippet:
            snippet = "Check out the latest insights in this edition."

        return {
            "edition_slug": edition_slug,
            "title": title,
            "snippet": snippet,
            "issue_number": row["issue_number"],
        }
    except Exception:
        logger.exception("Failed to get snippet for edition %s", edition_slug)
        try:
            conn.close()
        except Exception:
            pass
        return None


def generate_cross_promo_html(
    current_edition_slug: str,
    repo: Repository,
    config: AppConfig,
) -> str:
    """Generate 'Also from TrueFans' HTML block for the other editions.

    Returns email-safe HTML with inline CSS and table layout.
    Returns empty string if no other editions have content to show.
    """
    all_slugs = ["fan", "artist", "industry"]
    other_slugs = [s for s in all_slugs if s != current_edition_slug]

    snippets = []
    for slug in other_slugs:
        snippet = _get_latest_issue_snippet(repo, slug)
        if snippet:
            snippets.append(snippet)

    if not snippets:
        return ""

    site_domain = config.site_domain.rstrip("/")

    # Build email-safe HTML
    rows_html = ""
    for s in snippets:
        meta = _EDITION_META.get(s["edition_slug"], {})
        color = meta.get("color", "#6b7280")
        emoji = meta.get("emoji", "")
        label = meta.get("label", s["edition_slug"].title())
        title_esc = escape(s["title"])
        snippet_esc = escape(s["snippet"])
        subscribe_url = f"{site_domain}/subscribe"

        rows_html += f"""
            <tr>
                <td style="padding: 16px; border-bottom: 1px solid #e5e7eb;">
                    <table cellpadding="0" cellspacing="0" border="0" width="100%">
                        <tr>
                            <td>
                                <span style="display: inline-block; background: {color}; color: #ffffff; font-size: 11px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; padding: 3px 10px; border-radius: 12px; margin-bottom: 8px;">{emoji} {label}</span>
                                <p style="font-size: 15px; font-weight: 600; color: #1f2937; margin: 8px 0 4px;">{title_esc}</p>
                                <p style="font-size: 13px; color: #6b7280; margin: 0 0 8px; line-height: 1.5;">{snippet_esc}</p>
                                <a href="{subscribe_url}" style="font-size: 13px; color: {color}; text-decoration: none; font-weight: 600;">Subscribe to {label} &rarr;</a>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>"""

    html = f"""
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top: 24px; margin-bottom: 24px; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden;">
            <tr>
                <td style="padding: 16px 16px 8px; background: #f9fafb;">
                    <h3 style="font-size: 16px; font-weight: 700; color: #1f2937; margin: 0;">Also from TrueFans</h3>
                    <p style="font-size: 13px; color: #6b7280; margin: 4px 0 0;">Explore our other editions</p>
                </td>
            </tr>
            {rows_html}
        </table>"""

    return html
