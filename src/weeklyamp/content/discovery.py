"""AI-powered section discovery — suggests new newsletter sections."""

from __future__ import annotations

import json
from typing import Optional

from weeklyamp.core.models import AppConfig
from weeklyamp.db.repository import Repository


def suggest_sections(
    repo: Repository, config: AppConfig, count: int = 3,
) -> list[dict]:
    """Use AI to generate section ideas based on existing sections + content.

    Returns list of dicts: [{slug, display_name, reason, word_count_label, target_word_count}]
    """
    existing = repo.get_active_sections()
    existing_names = ", ".join(s["display_name"] for s in existing)

    prompt = f"""You are an expert newsletter editor for "{config.newsletter.name}",
a newsletter about: {config.newsletter.tagline}.

Current sections: {existing_names}

Suggest {count} new section ideas that would complement the existing sections.
For each, provide:
- slug (lowercase, underscores, like "new_section")
- display_name (uppercase section title)
- reason (1 sentence on why this adds value)
- word_count_label (short/medium/long)
- target_word_count (number)

Respond ONLY with a JSON array of objects. No other text."""

    from weeklyamp.content.generator import generate_draft
    content, _ = generate_draft(prompt, config, max_tokens_override=1500)

    # Parse JSON from response
    try:
        # Try to find JSON array in the response
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        suggestions = json.loads(text)
        if not isinstance(suggestions, list):
            suggestions = []
    except (json.JSONDecodeError, ValueError):
        suggestions = []

    return suggestions[:count]


def save_suggestions(repo: Repository, suggestions: list[dict]) -> int:
    """Store AI-suggested sections in the database as section_type='suggested', is_active=0."""
    saved = 0
    for s in suggestions:
        slug = s.get("slug", "").strip()
        display_name = s.get("display_name", "").strip()
        if not slug or not display_name:
            continue

        # Check if slug already exists
        existing = repo.get_section(slug)
        if existing:
            continue

        conn = repo._conn()
        try:
            conn.execute(
                """INSERT INTO section_definitions
                   (slug, display_name, sort_order, section_type, is_active,
                    word_count_label, target_word_count, suggested_reason, suggested_at)
                   VALUES (?, ?, 99, 'suggested', 0, ?, ?, ?, CURRENT_TIMESTAMP)""",
                (
                    slug, display_name,
                    s.get("word_count_label", "medium"),
                    s.get("target_word_count", 300),
                    s.get("reason", ""),
                ),
            )
            conn.commit()
            saved += 1
        except Exception:
            pass
        finally:
            conn.close()

    return saved


def generate_research_brief(repo, config, issue_id: int, section_slug: str) -> str:
    """Generate an AI-powered research brief from top raw content for a section."""
    from weeklyamp.content.generator import generate_draft

    # Get top content items for this section
    content_items = repo.get_unused_content(section_slug=section_slug, limit=5)
    if not content_items:
        return "No research content available for this section."

    # Build context from raw content
    context_parts = []
    for item in content_items:
        title = item.get("title", "Untitled")
        url = item.get("url", "")
        summary = item.get("summary", "")
        author = item.get("author", "")
        context_parts.append(
            f"- {title}"
            + (f" by {author}" if author else "")
            + (f"\n  {summary}" if summary else "")
            + (f"\n  Source: {url}" if url else "")
        )

    context = "\n".join(context_parts)

    prompt = (
        f"Based on the following research sources, write a concise editorial brief "
        f"for the newsletter section '{section_slug}'. Summarize the key themes, "
        f"highlight the most interesting angles, and suggest a focus for this week's article.\n\n"
        f"Sources:\n{context}\n\n"
        f"Write a 200-300 word brief."
    )

    brief, _ = generate_draft(prompt, config, max_tokens_override=500)
    return brief or "Brief generation failed — check AI provider configuration."
