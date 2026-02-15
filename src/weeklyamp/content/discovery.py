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
