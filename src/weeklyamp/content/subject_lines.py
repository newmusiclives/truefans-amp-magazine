"""AI-powered subject line generator with heuristic scoring.

Generates multiple subject line options for a newsletter issue using AI,
then scores them with a heuristic model to recommend the best candidates.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from weeklyamp.core.models import AppConfig

logger = logging.getLogger(__name__)


class SubjectLineGenerator:
    """Generate and score newsletter subject lines."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate_options(
        self,
        issue: dict,
        section_summaries: list[dict],
        edition_name: str = "",
        count: int = 5,
    ) -> list[dict]:
        """Use AI to generate *count* subject line options.

        Each item in the returned list is a dict with keys:
        - ``text``: the subject line string
        - ``style``: one of question / teaser / number / direct / emoji

        Returns an empty list on failure.
        """
        from weeklyamp.content.generator import generate_draft

        highlights = "\n".join(
            f"- {s['display_name']}: {s['summary']}" for s in section_summaries[:6]
        ) or "- A fresh collection of music industry insights"

        edition_clause = f" ({edition_name} edition)" if edition_name else ""

        prompt = (
            f"Generate exactly {count} email subject lines for Issue "
            f"#{issue.get('issue_number', '?')}{edition_clause} of a music-industry "
            f"newsletter called \"{self.config.newsletter.name}\".\n\n"
            f"Highlights from this issue:\n{highlights}\n\n"
            "Requirements:\n"
            "- Each subject line should be attention-grabbing and specific to the content above.\n"
            "- Use VARIED styles across the options. Include at least one of each:\n"
            "  * Question style (asks the reader something)\n"
            "  * Teaser style (creates curiosity)\n"
            "  * Number style (uses a specific number, e.g. '5 ways...')\n"
            "  * Direct style (straightforward value proposition)\n"
            "- Keep each subject line between 30 and 60 characters when possible.\n"
            "- Do NOT use all caps. Emojis are allowed sparingly (max 1 per line).\n\n"
            "Return the result as a numbered list. On each line, put the style tag "
            "in square brackets FIRST, then the subject line. Example:\n"
            "1. [question] Is your release strategy outdated?\n"
            "2. [teaser] The streaming trick labels don't want you to know\n"
        )

        try:
            content, _ = generate_draft(prompt, self.config, max_tokens_override=400)
            return self._parse_options(content)
        except Exception:
            logger.exception("Failed to generate subject line options")
            return []

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_options(raw: str) -> list[dict]:
        """Parse the numbered list returned by the AI into structured dicts."""
        options: list[dict] = []
        for line in raw.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            # Strip leading number + dot/paren
            line = re.sub(r"^\d+[\.\)]\s*", "", line)
            # Extract [style] tag
            style_match = re.match(r"\[(\w+)\]\s*(.+)", line)
            if style_match:
                style = style_match.group(1).lower()
                text = style_match.group(2).strip()
            else:
                style = "direct"
                text = line
            if text:
                options.append({"text": text, "style": style})
        return options

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    @staticmethod
    def score_subject_line(text: str) -> float:
        """Heuristic score for a subject line (0-100).

        Factors:
        - Length penalty for too short (<30) or too long (>60)
        - Bonus for emoji presence
        - Bonus for question mark
        - Bonus for a number in the text
        - Bonus for urgency words
        """
        score = 50.0  # baseline

        length = len(text)
        if length < 30:
            score -= (30 - length) * 1.0
        elif length > 60:
            score -= (length - 60) * 0.8
        else:
            # Sweet spot bonus
            score += 10.0

        # Emoji bonus (simple check for non-ASCII chars that are likely emoji)
        if re.search(r"[\U0001f300-\U0001f9ff]", text):
            score += 8.0

        # Question bonus
        if "?" in text:
            score += 10.0

        # Number bonus
        if re.search(r"\d+", text):
            score += 8.0

        # Urgency words bonus
        urgency_words = {"now", "today", "breaking", "just", "new", "exclusive", "secret", "don't miss"}
        text_lower = text.lower()
        for word in urgency_words:
            if word in text_lower:
                score += 5.0
                break  # only count once

        return max(0.0, min(100.0, round(score, 1)))

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def get_best(self, options: list[dict]) -> list[dict]:
        """Score all options and return the top 3 by score."""
        for opt in options:
            opt["score"] = self.score_subject_line(opt["text"])
        ranked = sorted(options, key=lambda o: o["score"], reverse=True)
        return ranked[:3]
