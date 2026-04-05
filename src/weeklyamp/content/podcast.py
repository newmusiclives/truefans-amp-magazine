"""Podcast generation — convert newsletter issues into podcast episodes.

Extends the audio.py TTS foundation to generate full podcast episodes
with intro, section content, and outro segments.
INACTIVE by default — requires podcast.enabled=true.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional
from xml.etree.ElementTree import Element, SubElement, tostring

from weeklyamp.core.models import AppConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


class PodcastGenerator:
    """Generate podcast episodes from newsletter content and manage RSS feed."""

    def __init__(self, repo: Repository, config: AppConfig) -> None:
        self.repo = repo
        self.config = config

    def generate_episode(self, issue_id: int, edition_slug: str = "") -> Optional[int]:
        """Generate a podcast episode from a published issue.

        Uses the audio.py TTS engine to convert assembled newsletter content
        into a podcast episode with intro and outro segments.
        Returns the podcast_episode id, or None on failure.
        """
        if not self.config.podcast.enabled:
            return None

        issue = self.repo.get_issue(issue_id)
        if not issue:
            logger.warning("Issue %d not found", issue_id)
            return None

        assembled = self.repo.get_assembled(issue_id)
        if not assembled:
            logger.warning("No assembled content for issue %d", issue_id)
            return None

        # Build script: intro + content + outro
        intro = self.config.podcast.intro_text
        outro = self.config.podcast.outro_text
        content = assembled.get("plain_text", "")
        if not content:
            # Strip HTML to get plain text
            from weeklyamp.content.assembly import strip_html
            content = strip_html(assembled.get("html_content", ""))

        full_script = f"{intro}\n\n{content}\n\n{outro}"

        title = f"Issue #{issue.get('issue_number', '?')}"
        if edition_slug:
            title += f" — {edition_slug.capitalize()} Edition"

        # Create episode record
        conn = self.repo._conn()
        cur = conn.execute(
            """INSERT INTO podcast_episodes (issue_id, edition_slug, title, description, status)
               VALUES (?, ?, ?, ?, 'generating')""",
            (issue_id, edition_slug, title, content[:500]),
        )
        conn.commit()
        episode_id = cur.lastrowid
        conn.close()

        # Generate audio via TTS
        try:
            from weeklyamp.content.audio import generate_tts
            audio_result = generate_tts(full_script, self.config)
            if audio_result and audio_result.get("url"):
                conn = self.repo._conn()
                conn.execute(
                    """UPDATE podcast_episodes SET audio_url = ?, duration_seconds = ?,
                       file_size_bytes = ?, status = 'ready' WHERE id = ?""",
                    (audio_result["url"], audio_result.get("duration", 0),
                     audio_result.get("file_size", 0), episode_id),
                )
                conn.commit()
                conn.close()
                logger.info("Podcast episode %d generated for issue %d", episode_id, issue_id)
                return episode_id
            else:
                conn = self.repo._conn()
                conn.execute("UPDATE podcast_episodes SET status = 'failed' WHERE id = ?", (episode_id,))
                conn.commit()
                conn.close()
                return None
        except Exception:
            logger.exception("Podcast generation failed for issue %d", issue_id)
            conn = self.repo._conn()
            conn.execute("UPDATE podcast_episodes SET status = 'failed' WHERE id = ?", (episode_id,))
            conn.commit()
            conn.close()
            return None

    def get_episodes(self, edition_slug: str = "", limit: int = 50) -> list[dict]:
        """Get published podcast episodes."""
        conn = self.repo._conn()
        if edition_slug:
            rows = conn.execute(
                "SELECT * FROM podcast_episodes WHERE edition_slug = ? AND status IN ('ready', 'published') ORDER BY created_at DESC LIMIT ?",
                (edition_slug, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM podcast_episodes WHERE status IN ('ready', 'published') ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def publish_episode(self, episode_id: int) -> bool:
        """Mark an episode as published."""
        conn = self.repo._conn()
        conn.execute(
            "UPDATE podcast_episodes SET status = 'published', published_at = CURRENT_TIMESTAMP WHERE id = ?",
            (episode_id,),
        )
        conn.commit()
        conn.close()
        return True

    def generate_rss_feed(self, edition_slug: str = "") -> str:
        """Generate a podcast RSS feed (XML) for distribution.

        Compatible with Apple Podcasts, Spotify, Google Podcasts, etc.
        """
        if not self.config.podcast.rss_enabled:
            return ""

        episodes = self.get_episodes(edition_slug=edition_slug)
        if not episodes:
            return ""

        rss = Element("rss", version="2.0")
        rss.set("xmlns:itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
        channel = SubElement(rss, "channel")

        title = f"{self.config.newsletter.name} Podcast"
        if edition_slug:
            title += f" — {edition_slug.capitalize()}"

        SubElement(channel, "title").text = title
        SubElement(channel, "link").text = self.config.site_domain
        SubElement(channel, "description").text = self.config.newsletter.tagline
        SubElement(channel, "language").text = "en"

        itunes_author = SubElement(channel, "itunes:author")
        itunes_author.text = self.config.newsletter.name

        for ep in episodes:
            item = SubElement(channel, "item")
            SubElement(item, "title").text = ep.get("title", "")
            SubElement(item, "description").text = ep.get("description", "")

            audio_url = ep.get("audio_url", "")
            if audio_url:
                enclosure = SubElement(item, "enclosure")
                enclosure.set("url", audio_url)
                enclosure.set("type", "audio/mpeg")
                enclosure.set("length", str(ep.get("file_size_bytes", 0)))

            if ep.get("duration_seconds"):
                dur = ep["duration_seconds"]
                SubElement(item, "itunes:duration").text = f"{dur // 60}:{dur % 60:02d}"

            if ep.get("published_at"):
                SubElement(item, "pubDate").text = str(ep["published_at"])

        return tostring(rss, encoding="unicode", xml_declaration=True)
