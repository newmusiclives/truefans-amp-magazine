"""Ensure every generated draft carries at least N Creative Commons
images, matched to content keywords when possible.

Usage from the writer agent after generate_draft returns:

    from weeklyamp.content.images import ensure_images
    content = ensure_images(content, section_slug, section_title, min_images=2)

The helper:

1. Counts ``<img>`` tags already present in the draft.
2. If fewer than ``min_images``, picks images from a curated CC-licensed
   pool, keyed on the section slug / title. Falls back to generic music
   imagery when no specific match fits — placed near any ``<poll>`` /
   survey block in the draft per Paul's direction.
3. Inserts the missing images as ``<figure>`` blocks with proper
   attribution links back to Unsplash.

We deliberately use Unsplash's published CC0 photo URLs directly rather
than an API — no key to manage, no rate limits at embed time, and the
attribution links point at the canonical photo page for compliance.
"""

from __future__ import annotations

import random
import re
from typing import Optional


# ---- Curated CC0 image pool ----
#
# Each entry: (photo_id, direct_url, alt_text, photographer, keywords).
# Selected from Unsplash's CC0 catalog. Keywords are the signals we
# match against section slug / title / content when picking a photo.
_POOL: list[dict] = [
    # Concert / live music — broad Fan-edition content
    {
        "url": "https://images.unsplash.com/photo-1501386761578-eac5c94b800a?auto=format&fit=crop&w=1200&q=75",
        "alt": "Crowd at an outdoor concert with stage lights",
        "credit": "Aditya Chinchure / Unsplash",
        "credit_url": "https://unsplash.com/photos/people-at-concert-eF7HN40WbAQ",
        "keywords": ("concert", "live", "backstage", "tour", "stage", "arena", "fan"),
    },
    # Vinyl / records — music appreciation
    {
        "url": "https://images.unsplash.com/photo-1459749411175-04bf5292ceea?auto=format&fit=crop&w=1200&q=75",
        "alt": "Vinyl record spinning on a turntable",
        "credit": "Markus Spiske / Unsplash",
        "credit_url": "https://unsplash.com/photos/person-holding-vinyl-records-yj3ukR2_Y2o",
        "keywords": ("vinyl", "record", "turntable", "classic", "album", "catalog"),
    },
    # Songwriter / guitar — Artist-edition craft
    {
        "url": "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?auto=format&fit=crop&w=1200&q=75",
        "alt": "Songwriter in a home studio with guitar and notebook",
        "credit": "Jefferson Santos / Unsplash",
        "credit_url": "https://unsplash.com/photos/person-playing-guitar-TDzUYMukLSE",
        "keywords": ("songwriter", "songcraft", "guitar", "writing", "acoustic", "lyrics"),
    },
    # Studio / microphone — Artist production
    {
        "url": "https://images.unsplash.com/photo-1520523839897-bd0b52f945a0?auto=format&fit=crop&w=1200&q=75",
        "alt": "Recording studio condenser microphone and mixing desk",
        "credit": "Israel Palacio / Unsplash",
        "credit_url": "https://unsplash.com/photos/black-and-gray-condenser-microphone-AvVFATyr4-c",
        "keywords": ("studio", "recording", "production", "microphone", "vocals", "vocal", "mix"),
    },
    # Charts / data — Industry analytics
    {
        "url": "https://images.unsplash.com/photo-1590602847861-f357a9332bbc?auto=format&fit=crop&w=1200&q=75",
        "alt": "Charts and analytics on a laptop screen",
        "credit": "Campaign Creators / Unsplash",
        "credit_url": "https://unsplash.com/photos/charts-on-laptop-screen-9Nup6uk03gQ",
        "keywords": ("chart", "analytics", "streaming", "pulse", "data", "money", "royalt", "market"),
    },
    # (Removed: record-label/catalog entry had a 404 URL. Its keyword
    # coverage is now folded into the mixing-desk entry below, which
    # doubles as Industry production context.)
    # Festival / crowd — live & events
    {
        "url": "https://images.unsplash.com/photo-1470229722913-7c0e2dbbafd3?auto=format&fit=crop&w=1200&q=75",
        "alt": "Crowd silhouetted against bright festival stage lights",
        "credit": "Anthony Delanoix / Unsplash",
        "credit_url": "https://unsplash.com/photos/people-standing-on-front-of-stage-QAwciFlS1g4",
        "keywords": ("festival", "event", "crowd", "touring"),
    },
    # Headphones / listening — fan engagement, playlists
    {
        "url": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=1200&q=75",
        "alt": "Close-up of headphones on a warm background",
        "credit": "Blocks Fletcher / Unsplash",
        "credit_url": "https://unsplash.com/photos/black-and-silver-headphones-on-black-textile-4xe-yVFJCvw",
        "keywords": ("playlist", "discovery", "listen", "streaming", "spotify", "headphones", "fan"),
    },
    # Mixing desk / console — production depth + label/catalog
    # context for Industry-edition pieces. Keywords merged from the
    # removed record-label entry.
    {
        "url": "https://images.unsplash.com/photo-1487215078519-e21cc028cb29?auto=format&fit=crop&w=1200&q=75",
        "alt": "Hands on a mixing console in a recording studio",
        "credit": "Lee Campbell / Unsplash",
        "credit_url": "https://unsplash.com/photos/person-using-audio-mixer-TK6iM8b-0BE",
        "keywords": (
            "engineer", "mixing", "console", "mastering", "studio",
            "label", "catalog", "rights", "licensing", "publishing", "independent",
        ),
    },
    # Generic music silhouette — fallback for polls/surveys
    {
        "url": "https://images.unsplash.com/photo-1510915361894-db8b60106cb1?auto=format&fit=crop&w=1200&q=75",
        "alt": "Musician silhouette against warm stage light",
        "credit": "Andrik Langfield / Unsplash",
        "credit_url": "https://unsplash.com/photos/silhouette-of-person-playing-guitar-hsPFuudRg5I",
        "keywords": ("music", "generic", "artist", "silhouette"),
    },
]


_FALLBACK_KEYWORD = "generic"


def _pool_by_keyword(text: str, exclude_urls: set[str]) -> Optional[dict]:
    """Return the best-matching pool entry for ``text``, or None.

    Scores each entry by keyword match count; returns highest score
    among entries not already in ``exclude_urls`` (so we don't double-
    insert the same photo in one draft).
    """
    if not text:
        return None
    low = text.lower()
    best: tuple[int, Optional[dict]] = (0, None)
    for entry in _POOL:
        if entry["url"] in exclude_urls:
            continue
        score = sum(1 for kw in entry["keywords"] if kw in low)
        if score > best[0]:
            best = (score, entry)
    return best[1]


def _generic_fallback(exclude_urls: set[str]) -> dict:
    """Return a generic music image — used when no keyword match fits.

    Preference order: the explicitly-tagged 'generic' entry first; any
    other music-tagged entry if already used; as a last resort, a
    random pool pick."""
    for entry in _POOL:
        if _FALLBACK_KEYWORD in entry["keywords"] and entry["url"] not in exclude_urls:
            return entry
    remaining = [e for e in _POOL if e["url"] not in exclude_urls]
    if remaining:
        return random.choice(remaining)
    # Exhausted: fine to reuse the first entry rather than crash
    return _POOL[0]


def _existing_image_urls(content: str) -> set[str]:
    return set(re.findall(r'<img[^>]+src="([^"]+)"', content))


def _render_figure(entry: dict) -> str:
    return (
        f'<figure style="margin:20px 0;text-align:center;">'
        f'<img src="{entry["url"]}" alt="{entry["alt"]}" '
        f'style="width:100%;height:auto;border-radius:8px;display:block;">'
        f'<figcaption style="font-size:11px;color:#9ca3af;margin-top:8px;font-style:italic;">'
        f'Photo: <a href="{entry["credit_url"]}" style="color:#9ca3af;" target="_blank" rel="noopener">'
        f'{entry["credit"]} / Unsplash (CC0)</a></figcaption>'
        f'</figure>'
    )


# Patterns marking poll / survey / trivia blocks where generic
# fallback images should be placed per product direction.
_POLL_MARKERS = (
    re.compile(r'<!--\s*Poll[^>]*-->', re.IGNORECASE),
    re.compile(r'<!--\s*Trivia[^>]*-->', re.IGNORECASE),
    re.compile(r'QUICK POLL', re.IGNORECASE),
    re.compile(r"This Week's Trivia", re.IGNORECASE),
)


def _first_poll_index(content: str) -> int:
    """Character index of the first poll/survey marker, or -1."""
    for pat in _POLL_MARKERS:
        m = pat.search(content)
        if m:
            return m.start()
    return -1


def ensure_images(
    content: str,
    section_slug: str = "",
    section_title: str = "",
    *,
    min_images: int = 2,
) -> str:
    """Ensure ``content`` has at least ``min_images`` images.

    Best-effort: tries to keyword-match section context first. Falls
    back to generic music imagery, preferentially placed near poll /
    survey blocks when present.

    Existing images in the content are preserved and counted toward
    the minimum — so a draft that already includes 2+ images is
    returned unchanged.
    """
    if not content:
        return content

    existing = _existing_image_urls(content)
    needed = max(0, min_images - len(existing))
    if needed == 0:
        return content

    context_text = f"{section_slug} {section_title} {content[:1500]}"

    figures: list[tuple[str, bool]] = []  # (html, is_fallback)
    for i in range(needed):
        entry = _pool_by_keyword(context_text, existing)
        is_fallback = False
        if entry is None:
            entry = _generic_fallback(existing)
            is_fallback = True
        existing.add(entry["url"])
        figures.append((_render_figure(entry), is_fallback))

    # Placement:
    # - First figure goes at the top of the content (prepend).
    # - Second (or further) figures go near the first poll/survey
    #   block if one exists, else appended to the end.
    out = content
    if figures:
        top_html, _top_is_fallback = figures[0]
        out = top_html + "\n" + out
    for fig_html, is_fallback in figures[1:]:
        if is_fallback:
            idx = _first_poll_index(out)
            if idx >= 0:
                out = out[:idx] + fig_html + "\n" + out[idx:]
                continue
        out = out + "\n" + fig_html
    return out
