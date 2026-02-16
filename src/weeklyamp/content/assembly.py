"""Combine approved drafts into final newsletter HTML."""

from __future__ import annotations

import markdown

from weeklyamp.content.sections import get_section_map
from weeklyamp.web.sanitize import sanitize_html
from weeklyamp.core.models import AppConfig
from weeklyamp.db.repository import Repository
from weeklyamp.delivery.templates import (
    render_guest_section,
    render_newsletter,
    render_section,
    render_sponsor_block,
    render_submission_section,
)


def assemble_newsletter(repo: Repository, issue_id: int, config: AppConfig) -> tuple[str, str]:
    """Assemble approved drafts into final HTML.

    Returns (html_content, plain_text).
    """
    issue = repo.get_issue(issue_id)
    if not issue:
        raise ValueError(f"Issue {issue_id} not found")

    drafts = repo.get_drafts_for_issue(issue_id)
    section_map = get_section_map(repo)

    # Sort drafts by section sort_order
    def sort_key(d: dict) -> int:
        sec = section_map.get(d["section_slug"], {})
        return sec.get("sort_order", 99)

    drafts.sort(key=sort_key)

    # Render each section
    sections_html: list[dict] = []
    plain_parts: list[str] = []

    for draft in drafts:
        if draft["status"] not in ("approved", "revised"):
            continue

        slug = draft["section_slug"]
        sec = section_map.get(slug, {})
        display_name = sec.get("display_name", slug.upper())

        # Convert markdown content to HTML (sanitized against XSS)
        content_html = sanitize_html(markdown.markdown(draft["content"], extensions=["extra"]))

        # Check if this draft came from a guest article or artist submission
        guest = repo.get_guest_article_by_draft(draft["id"])
        submission = repo.get_submission_by_draft(draft["id"])

        if guest:
            section_html = render_guest_section(
                content_html,
                author_name=guest.get("author_name", ""),
                author_bio=guest.get("author_bio", ""),
                original_url=guest.get("original_url", ""),
            )
        elif submission:
            section_html = render_submission_section(
                content_html,
                section_title=display_name,
                artist_name=submission.get("artist_name", ""),
                artist_website=submission.get("artist_website", ""),
                artist_social=submission.get("artist_social", ""),
            )
        else:
            section_html = render_section(display_name, content_html)

        sections_html.append({"html": section_html})

        # Plain text version
        plain_parts.append(f"=== {display_name} ===\n\n{draft['content']}\n")

    # Fetch and inject sponsor blocks
    sponsor_blocks = repo.get_sponsor_blocks_for_issue(issue_id)
    if sponsor_blocks:
        top_blocks = [b for b in sponsor_blocks if b["position"] == "top"]
        mid_blocks = [b for b in sponsor_blocks if b["position"] == "mid"]
        bottom_blocks = [b for b in sponsor_blocks if b["position"] == "bottom"]

        # Render sponsor block HTML
        top_html = [{"html": render_sponsor_block(b)} for b in top_blocks]
        mid_html = [{"html": render_sponsor_block(b)} for b in mid_blocks]
        bottom_html = [{"html": render_sponsor_block(b)} for b in bottom_blocks]

        # Inject: top before first section, mid at midpoint, bottom after last
        midpoint = len(sections_html) // 2
        injected: list[dict] = []
        injected.extend(top_html)
        injected.extend(sections_html[:midpoint])
        injected.extend(mid_html)
        injected.extend(sections_html[midpoint:])
        injected.extend(bottom_html)
        sections_html = injected

        # Add sponsor text to plain text
        for b in sponsor_blocks:
            plain_parts.append(f"--- SPONSORED: {b['sponsor_name']} ---\n{b['headline']}\n{b['cta_url']}\n")

    # Render full newsletter
    html = render_newsletter(
        newsletter_name=config.newsletter.name,
        tagline=config.newsletter.tagline,
        issue_number=issue["issue_number"],
        title=issue.get("title", ""),
        sections=sections_html,
        header_image_url=config.newsletter.header_image_url,
        intro_copy=config.newsletter.intro_copy,
        footer_html=config.newsletter.footer_html,
    )

    plain_text = "\n\n".join(plain_parts)

    return html, plain_text
