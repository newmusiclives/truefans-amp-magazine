"""RSS/Atom feed parser."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import feedparser

from weeklyamp.utils.text import clean_html


@dataclass
class FeedItem:
    title: str
    url: str
    author: str
    summary: str
    published_at: Optional[str]  # ISO format string


def parse_feed(url: str) -> list[FeedItem]:
    """Parse an RSS/Atom feed and return a list of FeedItems."""
    feed = feedparser.parse(url)
    items: list[FeedItem] = []

    for entry in feed.entries:
        # Extract published date
        published = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                published = datetime(*entry.published_parsed[:6]).isoformat()
            except (TypeError, ValueError):
                pass
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            try:
                published = datetime(*entry.updated_parsed[:6]).isoformat()
            except (TypeError, ValueError):
                pass

        # Extract summary
        summary = ""
        if hasattr(entry, "summary"):
            summary = clean_html(entry.summary)
        elif hasattr(entry, "description"):
            summary = clean_html(entry.description)

        items.append(FeedItem(
            title=getattr(entry, "title", ""),
            url=getattr(entry, "link", ""),
            author=getattr(entry, "author", ""),
            summary=summary[:1000],
            published_at=published,
        ))

    return items
