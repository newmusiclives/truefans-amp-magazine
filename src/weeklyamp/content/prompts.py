"""Prompt builder — loads templates and fills in variables."""

from __future__ import annotations

from typing import Optional

from weeklyamp.core.config import get_prompt_template


def build_prompt(
    section_slug: str,
    topic: str = "",
    notes: str = "",
    reference_content: str = "",
    newsletter_name: str = "TrueFans AMP",
    target_word_count: Optional[int] = None,
    word_count_label: Optional[str] = None,
) -> str:
    """Build a complete prompt for a section by loading its template and filling variables."""
    template = get_prompt_template(section_slug)

    if not template:
        # Fallback generic prompt
        template = _fallback_prompt(section_slug)

    # Replace template variables — provide sensible defaults when empty
    prompt = template.replace("{{topic}}", topic if topic else "(Choose an engaging topic appropriate for this section)")
    prompt = prompt.replace("{{notes}}", notes if notes else "(No specific notes — use your best judgment)")
    prompt = prompt.replace("{{reference_content}}", reference_content if reference_content else "(No reference material provided — draw on your own knowledge)")
    prompt = prompt.replace("{{newsletter_name}}", newsletter_name)

    # Append word count instruction
    if target_word_count and word_count_label:
        prompt += f"\n\nIMPORTANT: Target length is {target_word_count} words ({word_count_label}). Stay within this range."

    # Ensure the AI always generates content, never asks for input
    prompt += "\n\nCRITICAL: You must write the actual section content now. Do NOT ask for more information, request clarification, or output a template. Generate the finished article directly."

    return prompt.strip()


def _fallback_prompt(section_slug: str) -> str:
    """Generic fallback prompt when no template file exists."""
    display = section_slug.replace("_", " ").upper()
    return f"""You are writing the {display} section of the {{{{newsletter_name}}}} newsletter,
a weekly newsletter for independent artists and songwriters.

Topic: {{{{topic}}}}

Notes: {{{{notes}}}}

Reference material:
{{{{reference_content}}}}

Write an engaging, concise section (200-400 words) that provides value to independent musicians.
Use a warm, encouraging tone. Include specific, actionable insights where appropriate.
Format in Markdown."""
