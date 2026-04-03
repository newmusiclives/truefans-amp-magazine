"""Audio newsletter generation via Text-to-Speech.

DISABLED by default — requires audio.enabled=true and configured TTS provider.
Supports OpenAI TTS API. ElevenLabs support is placeholder for future.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from weeklyamp.core.models import AppConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)

AUDIO_DIR = Path(__file__).parent.parent.parent.parent / "data" / "audio"


def generate_audio_newsletter(
    repo: Repository, config: AppConfig, issue_id: int
) -> Optional[int]:
    """Convert assembled newsletter plain text to speech.

    Uses OpenAI TTS API to generate an MP3 file.
    Creates an audio_issues record in the database.
    Returns the audio_issue ID on success, None on failure.
    """
    if not config.audio.enabled:
        logger.warning("Audio generation is disabled")
        return None

    # Get assembled content
    assembled = repo.get_assembled(issue_id)
    if not assembled:
        logger.warning("No assembled content for issue %d", issue_id)
        return None

    plain_text = assembled.get("plain_text", "")
    if not plain_text:
        logger.warning("No plain text content for issue %d", issue_id)
        return None

    issue = repo.get_issue(issue_id)
    edition_slug = issue.get("edition_slug", "") if issue else ""

    # Create DB record
    audio_id = repo.create_audio_issue(issue_id, edition_slug, config.audio.tts_provider)

    try:
        # Ensure audio directory exists
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)

        # Truncate text if too long for TTS (OpenAI limit is ~4096 chars per request)
        max_chars = 4000
        if len(plain_text) > max_chars:
            plain_text = plain_text[:max_chars] + "\n\n...Content truncated for audio version."

        if config.audio.tts_provider == "openai":
            audio_path = _generate_openai_tts(plain_text, issue_id, config)
        else:
            logger.warning("Unknown TTS provider: %s", config.audio.tts_provider)
            repo.update_audio_issue(audio_id, status="failed")
            return None

        if audio_path and audio_path.exists():
            file_size = audio_path.stat().st_size
            audio_url = f"/audio/{issue_id}"
            repo.update_audio_issue(
                audio_id,
                audio_url=audio_url,
                file_size_bytes=file_size,
                status="complete",
            )
            logger.info("Audio generated for issue %d: %s (%d bytes)", issue_id, audio_path, file_size)
            return audio_id
        else:
            repo.update_audio_issue(audio_id, status="failed")
            return None

    except Exception:
        logger.exception("Audio generation failed for issue %d", issue_id)
        repo.update_audio_issue(audio_id, status="failed")
        return None


def _generate_openai_tts(text: str, issue_id: int, config: AppConfig) -> Optional[Path]:
    """Generate audio using OpenAI's TTS API."""
    try:
        import openai
        client = openai.OpenAI()
        voice = config.audio.voice_id or "alloy"

        response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text,
        )

        output_path = AUDIO_DIR / f"issue_{issue_id}.mp3"
        response.stream_to_file(str(output_path))
        return output_path

    except Exception:
        logger.exception("OpenAI TTS generation failed")
        return None


def get_audio_file_path(issue_id: int) -> Optional[Path]:
    """Get the file path for an audio issue if it exists."""
    path = AUDIO_DIR / f"issue_{issue_id}.mp3"
    return path if path.exists() else None
