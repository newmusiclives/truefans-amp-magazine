"""Submission review workflow."""

from __future__ import annotations

from typing import Optional

from weeklyamp.content.generator import generate_draft
from weeklyamp.core.config import load_config
from weeklyamp.core.models import AppConfig
from weeklyamp.db.repository import Repository


class SubmissionReviewer:
    """Manages the submission review lifecycle."""

    def __init__(self, repo: Repository, config: Optional[AppConfig] = None) -> None:
        self.repo = repo
        self.config = config or load_config()

    def review_submission(self, submission_id: int) -> None:
        """Mark a submission as reviewed."""
        self.repo.update_submission_state(submission_id, "reviewed")

    def approve_submission(self, submission_id: int) -> None:
        """Approve a submission."""
        self.repo.update_submission_state(submission_id, "approved")

    def reject_submission(self, submission_id: int, notes: str = "") -> None:
        """Reject a submission with optional notes."""
        self.repo.update_submission_state(submission_id, "rejected")

    def schedule_submission(
        self, submission_id: int, issue_id: int,
        section_slug: str = "artist_spotlight",
    ) -> None:
        """Assign a submission to an issue."""
        self.repo.update_submission(
            submission_id,
            review_state="scheduled",
            target_issue_id=issue_id,
            target_section_slug=section_slug,
        )

    def create_draft_from_submission(self, submission_id: int) -> int:
        """Generate a draft from submission content."""
        sub = self.repo.get_submission(submission_id)
        if not sub:
            raise ValueError(f"Submission {submission_id} not found")

        issue_id = sub.get("target_issue_id")
        if not issue_id:
            raise ValueError("Submission has no target issue assigned")

        section_slug = sub.get("target_section_slug", "artist_spotlight")

        prompt = (
            f"Write a newsletter section about this artist submission for "
            f"TrueFans AMP Magazine.\n\n"
            f"Artist: {sub['artist_name']}\n"
            f"Title: {sub['title']}\n"
            f"Type: {sub['submission_type']}\n"
            f"Genre: {sub.get('genre', 'N/A')}\n"
            f"Description: {sub['description']}\n"
            f"Website: {sub.get('artist_website', 'N/A')}\n"
            f"Release Date: {sub.get('release_date', 'N/A')}\n\n"
            f"Write a compelling feature that introduces this artist to our audience "
            f"of independent musicians and songwriters. Highlight what makes them "
            f"interesting and include a call-to-action for readers."
        )

        content, model = generate_draft(prompt, self.config)

        draft_id = self.repo.create_draft(
            issue_id=issue_id,
            section_slug=section_slug,
            content=content,
            ai_model=model,
            prompt_used=f"Artist submission: {sub['artist_name']}",
        )

        self.repo.update_submission(submission_id, draft_id=draft_id, review_state="published")
        return draft_id
