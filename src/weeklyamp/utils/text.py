"""Text formatting helpers."""

from __future__ import annotations

import re
from html import unescape


def clean_html(html: str) -> str:
    """Strip HTML tags and decode entities."""
    text = re.sub(r"<[^>]+>", "", html)
    return unescape(text).strip()


def truncate(text: str, max_length: int = 300, suffix: str = "...") -> str:
    """Truncate text to max_length, breaking at word boundary."""
    if len(text) <= max_length:
        return text
    truncated = text[: max_length - len(suffix)]
    # Break at last space
    last_space = truncated.rfind(" ")
    if last_space > max_length // 2:
        truncated = truncated[:last_space]
    return truncated + suffix


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")
