"""XSS sanitization for markdown-to-HTML output."""

from __future__ import annotations

import bleach

# Tags safe for newsletter content rendering
_ALLOWED_TAGS = [
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "a", "strong", "em", "b", "i", "u",
    "ul", "ol", "li",
    "blockquote", "br", "hr",
    "img",
    "code", "pre",
    "table", "thead", "tbody", "tr", "th", "td",
    "div", "span",
    "dl", "dt", "dd",
    "sup", "sub",
    "abbr",
]

_ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "td": ["colspan", "rowspan", "align"],
    "th": ["colspan", "rowspan", "align"],
    "abbr": ["title"],
}

_ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def sanitize_html(raw_html: str) -> str:
    """Sanitize HTML, stripping dangerous tags/attributes while keeping safe content markup."""
    return bleach.clean(
        raw_html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
    )
