"""Tests for newsletter assembly."""
import pytest
from unittest.mock import patch


def test_assemble_newsletter_basic(repo):
    """Test basic newsletter assembly with approved drafts."""
    # Create an issue
    issue_id = repo.create_issue_with_schedule(issue_number=100, week_id="2026-W14", send_day="monday", edition_slug="fan")

    # Create and approve a draft
    draft_id = repo.create_draft(issue_id, "backstage_pass", "Test content for backstage pass.", ai_model="test")
    repo.update_draft_status(draft_id, "approved")

    # Mock AI generation to avoid actual API calls
    with patch("weeklyamp.content.assembly._generate_welcome_intro", return_value="Welcome!"):
        with patch("weeklyamp.content.assembly._generate_ps_closing", return_value="Thanks for reading!"):
            from weeklyamp.content.assembly import assemble_newsletter
            from weeklyamp.core.config import load_config
            config = load_config()
            html, plain = assemble_newsletter(repo, issue_id, config)

    assert "backstage_pass" in plain.lower() or "BACKSTAGE" in plain


def test_get_subscriber_segments(repo):
    """Test subscriber segmentation function."""
    from weeklyamp.content.assembly import get_subscriber_segments
    segments = get_subscriber_segments(repo)
    assert isinstance(segments, dict)
