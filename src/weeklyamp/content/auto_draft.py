"""Auto-generate drafts from research content."""

from __future__ import annotations

import logging
from typing import Optional

from weeklyamp.content.generator import generate_draft
from weeklyamp.core.models import AppConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


def auto_draft_from_research(
    repo: Repository, config: AppConfig, issue_id: int, section_slug: str
) -> Optional[int]:
    """Generate a draft for a section using top-scored research content.

    Returns the draft ID on success, None on failure.
    """
    # Get the section definition for prompt template
    sections = repo.get_all_sections()
    section = None
    for s in sections:
        if s.get("slug") == section_slug:
            section = s
            break

    if not section:
        logger.warning("Section %s not found", section_slug)
        return None

    # Get top research content
    content_items = repo.get_unused_content(section_slug=section_slug, limit=5)
    if not content_items:
        logger.info("No research content available for %s", section_slug)
        return None

    # Build context
    context_parts = []
    for item in content_items:
        title = item.get("title", "Untitled")
        summary = item.get("summary", "")
        url = item.get("url", "")
        context_parts.append(f"Title: {title}\nSummary: {summary}\nURL: {url}\n")

    research_context = "\n---\n".join(context_parts)

    # Use section's prompt template if available, otherwise generic
    prompt_template = section.get("prompt_template", "")
    target_words = section.get("target_word_count", 300)
    display_name = section.get("display_name", section_slug)

    prompt = (
        f"Write a newsletter section called '{display_name}' for TrueFans NEWSLETTERS.\n\n"
    )
    if prompt_template:
        prompt += f"Section guidelines: {prompt_template}\n\n"
    prompt += (
        f"Use the following research sources as inspiration and reference:\n\n"
        f"{research_context}\n\n"
        f"Write approximately {target_words} words. Be engaging, informative, and cite sources where relevant."
    )

    content, model_used = generate_draft(prompt, config)
    if not content:
        logger.warning("AI generation returned empty content for %s", section_slug)
        return None

    # Save draft
    draft_id = repo.create_draft(
        issue_id, section_slug, content, ai_model=model_used, prompt_used=prompt[:500]
    )

    # Mark research content as used
    for item in content_items:
        repo.mark_content_used(item["id"])

    logger.info(
        "Auto-generated draft %d for section %s (issue %d)",
        draft_id,
        section_slug,
        issue_id,
    )
    return draft_id
