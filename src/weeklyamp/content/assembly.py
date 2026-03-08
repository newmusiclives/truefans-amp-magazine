"""Combine approved drafts into final newsletter HTML."""

from __future__ import annotations

import logging
import re
from datetime import datetime

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

logger = logging.getLogger(__name__)


def _get_issue_date_context(issue: dict) -> dict:
    """Extract day, date, and week context from an issue."""
    # Try to get the publish date or send_day from the issue
    publish_date = issue.get("publish_date")
    send_day = issue.get("send_day", "")

    if publish_date:
        if isinstance(publish_date, str):
            try:
                dt = datetime.fromisoformat(publish_date.replace("Z", "+00:00"))
            except ValueError:
                dt = datetime.now()
        else:
            dt = publish_date
    else:
        dt = datetime.now()

    day_name = send_day.capitalize() if send_day else dt.strftime("%A")
    week_number = dt.isocalendar()[1]
    month_name = dt.strftime("%B")
    year = dt.year
    date_str = dt.strftime("%B %d, %Y")

    return {
        "day_name": day_name,
        "week_number": week_number,
        "month_name": month_name,
        "year": year,
        "date_str": date_str,
    }


def _generate_welcome_intro(
    issue: dict,
    section_summaries: list[dict],
    config: AppConfig,
    edition_name: str = "",
) -> str:
    """Generate an AI-written welcome intro specific to this issue."""
    from weeklyamp.content.generator import generate_draft

    date_ctx = _get_issue_date_context(issue)

    # Build highlights from the first few section summaries
    highlights = []
    for s in section_summaries[:3]:
        highlights.append(f"- {s['display_name']}: {s['summary']}")
    highlights_text = "\n".join(highlights) if highlights else "- A fresh collection of insights and stories"

    audience_note = ""
    if edition_name:
        if "fan" in edition_name.lower():
            audience_note = "Your readers are music fans and listeners who love discovering stories behind the music."
        elif "artist" in edition_name.lower():
            audience_note = "Your readers are independent artists and songwriters looking to level up their craft and career."
        elif "industry" in edition_name.lower():
            audience_note = "Your readers are music industry professionals who need actionable insights and data."

    prompt = f"""Write a warm, engaging welcome intro for the {edition_name + ' of ' if edition_name else ''}{config.newsletter.name}.

This is Issue #{issue['issue_number']}, going out on {date_ctx['day_name']}, {date_ctx['date_str']} (Week {date_ctx['week_number']} of {date_ctx['year']}).
{audience_note}

Here are the highlights from this issue:
{highlights_text}

Requirements:
- Write exactly 2 short paragraphs (3-4 sentences total)
- First paragraph: greet readers warmly, reference the specific day and time of week naturally (not robotically)
{f'- Mention this is the {edition_name} so readers know which edition they are reading' if edition_name else ''}
- Second paragraph: tease 1-2 highlights from this issue to hook the reader
- Tone: friendly, conversational, energetic — like a trusted friend who's excited to share
- Do NOT use generic filler. Be specific to THIS issue.
- Do NOT include any heading or title — just the two paragraphs
- Write in plain text (no markdown formatting)"""

    try:
        content, _ = generate_draft(prompt, config, max_tokens_override=300)
        return content.strip()
    except Exception:
        logger.warning("Failed to generate welcome intro — using fallback", exc_info=True)
        ed_label = f" ({edition_name})" if edition_name else ""
        return f"Welcome to Issue #{issue['issue_number']} of {config.newsletter.name}{ed_label}! Here's what we've got for you this {date_ctx['day_name']}."


def _generate_ps_closing(
    issue: dict,
    section_summaries: list[dict],
    config: AppConfig,
    edition_name: str = "",
) -> str:
    """Generate an AI-written PS closing from Paul Saunders, unique to this issue."""
    from weeklyamp.content.generator import generate_draft

    date_ctx = _get_issue_date_context(issue)

    # Provide section context for the PS to reference
    sections_context = []
    for s in section_summaries:
        sections_context.append(f"- {s['display_name']}: {s['summary']}")
    sections_text = "\n".join(sections_context) if sections_context else "- General music industry coverage"

    edition_context = f" ({edition_name})" if edition_name else ""

    audience_note = ""
    if edition_name:
        if "fan" in edition_name.lower():
            audience_note = "Your audience is music fans and listeners — speak to their passion and curiosity."
        elif "artist" in edition_name.lower():
            audience_note = "Your audience is independent artists and songwriters — speak to their creative journey and career growth."
        elif "industry" in edition_name.lower():
            audience_note = "Your audience is music industry professionals — speak to business insights and staying ahead."

    prompt = f"""Write a brief, personal PS closing note from Paul Saunders, Founder of TrueFans CONNECT, for this specific issue of {config.newsletter.name}{edition_context}.

This is Issue #{issue['issue_number']}, {date_ctx['day_name']} {date_ctx['date_str']}.
{audience_note}

The sections covered in this issue:
{sections_text}

Requirements:
- Start with "PS —" (the signature sign-off)
- Sign off as "Paul Saunders, Founder — TrueFans CONNECT"
- Write 2-3 sentences maximum between the opening PS and the sign-off
- Make it feel personal and specific to THIS issue — reference or reflect on one thing from the content
- Can include: a personal thought, a call to action, a question for readers, or a behind-the-scenes note
- Tone: genuine, warm, slightly informal — like a handwritten note at the bottom of a letter
- Each issue's PS must feel different and unique — never generic
- Do NOT repeat the section titles verbatim
- Write in plain text (no markdown)"""

    try:
        content, _ = generate_draft(prompt, config, max_tokens_override=200)
        # Ensure it starts with "PS"
        content = content.strip()
        if not content.upper().startswith("PS"):
            content = "PS — " + content
        return content
    except Exception:
        logger.warning("Failed to generate PS closing — using fallback", exc_info=True)
        return f"PS — Thanks for reading Issue #{issue['issue_number']}{edition_context}. See you next time."


def assemble_newsletter(repo: Repository, issue_id: int, config: AppConfig) -> tuple[str, str]:
    """Assemble approved drafts into final HTML.

    Returns (html_content, plain_text).
    """
    issue = repo.get_issue(issue_id)
    if not issue:
        raise ValueError(f"Issue {issue_id} not found")

    # Resolve edition name for edition-aware prompts
    edition_slug = issue.get("edition_slug", "")
    edition_name = ""
    if edition_slug:
        edition = repo.get_edition_by_slug(edition_slug)
        if edition:
            edition_name = edition.get("name", "")

    drafts = repo.get_drafts_for_issue(issue_id)
    section_map = get_section_map(repo)

    # Sort drafts by section sort_order
    def sort_key(d: dict) -> int:
        sec = section_map.get(d["section_slug"], {})
        return sec.get("sort_order", 99)

    drafts.sort(key=sort_key)

    # Render each section and collect summaries for intro/PS generation
    sections_html: list[dict] = []
    plain_parts: list[str] = []
    section_summaries: list[dict] = []

    for draft in drafts:
        if draft["status"] not in ("approved", "revised"):
            continue

        slug = draft["section_slug"]
        sec = section_map.get(slug, {})
        display_name = sec.get("display_name", slug.upper())

        # Collect a short summary for the welcome intro and PS
        content_text = draft["content"] or ""
        # First 100 chars of content as a summary
        summary = " ".join(content_text.split()[:20])
        if len(content_text.split()) > 20:
            summary += "..."
        section_summaries.append({"display_name": display_name, "summary": summary})

        # Convert markdown content to HTML (sanitized against XSS)
        content_html = sanitize_html(markdown.markdown(draft["content"], extensions=["extra"]))
        # Strip the first heading if it duplicates the section title
        content_html = re.sub(r"^\s*<h[1-3][^>]*>.*?</h[1-3]>\s*", "", content_html, count=1)

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

    # Generate AI welcome intro and PS closing (edition-aware)
    welcome_intro = _generate_welcome_intro(issue, section_summaries, config, edition_name)
    ps_closing = _generate_ps_closing(issue, section_summaries, config, edition_name)

    # Convert welcome intro to HTML
    welcome_html = sanitize_html(markdown.markdown(welcome_intro, extensions=["extra"]))

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
        intro_copy=welcome_html,
        footer_html=config.newsletter.footer_html,
        ps_closing=ps_closing,
    )

    # Build plain text with intro and PS
    plain_intro = f"{welcome_intro}\n\n{'=' * 40}\n"
    plain_ps = f"\n{'=' * 40}\n\n{ps_closing}\n"
    plain_text = plain_intro + "\n\n".join(plain_parts) + plain_ps

    return html, plain_text
