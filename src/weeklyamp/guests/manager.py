"""Guest article management — requests, permissions, and draft creation."""

from __future__ import annotations

from typing import Optional

from weeklyamp.content.generator import generate_draft
from weeklyamp.core.config import load_config
from weeklyamp.core.models import AppConfig
from weeklyamp.db.repository import Repository


class GuestArticleManager:
    """Manages the guest article lifecycle."""

    def __init__(self, repo: Repository, config: Optional[AppConfig] = None) -> None:
        self.repo = repo
        self.config = config or load_config()

    def request_article(
        self, contact_id: int, topic: str = "", notes: str = "",
        target_section_slug: str = "guest_column",
    ) -> int:
        """Create a guest article record with permission_state='requested'."""
        contact = self.repo.get_guest_contact(contact_id)
        if not contact:
            raise ValueError(f"Contact {contact_id} not found")

        return self.repo.create_guest_article(
            contact_id=contact_id,
            title=topic,
            author_name=contact["name"],
            permission_state="requested",
            target_section_slug=target_section_slug,
        )

    def track_permission(self, article_id: int, new_state: str, notes: str = "") -> None:
        """Update the permission state machine."""
        valid_transitions = {
            "requested": ["received", "declined"],
            "received": ["approved", "declined"],
            "approved": ["published", "declined"],
            "published": [],
            "declined": ["requested"],
        }

        article = self.repo.get_guest_article(article_id)
        if not article:
            raise ValueError(f"Article {article_id} not found")

        current = article["permission_state"]
        allowed = valid_transitions.get(current, [])
        if new_state not in allowed:
            raise ValueError(f"Cannot transition from '{current}' to '{new_state}'. Allowed: {allowed}")

        self.repo.update_guest_article_permission(article_id, new_state)

    def approve_article(
        self, article_id: int, issue_id: Optional[int] = None,
        section_slug: str = "guest_column",
    ) -> None:
        """Move to approved and optionally assign to an issue."""
        self.repo.update_guest_article_permission(article_id, "approved")
        updates = {}
        if issue_id:
            updates["target_issue_id"] = issue_id
        if section_slug:
            updates["target_section_slug"] = section_slug
        if updates:
            self.repo.update_guest_article(article_id, **updates)

    def create_draft_from_guest(self, article_id: int) -> int:
        """Create a draft record from guest article content."""
        article = self.repo.get_guest_article(article_id)
        if not article:
            raise ValueError(f"Article {article_id} not found")

        issue_id = article.get("target_issue_id")
        if not issue_id:
            raise ValueError("Article has no target issue assigned")

        section_slug = article.get("target_section_slug", "guest_column")
        display_mode = article.get("display_mode", "full")

        if display_mode == "full":
            content = article.get("content_full", "")
        elif display_mode == "summary":
            content = article.get("content_summary", "")
            if not content and article.get("content_full"):
                # AI-summarize
                prompt = (
                    f"Summarize this guest article for TrueFans AMP Magazine in 200-300 words. "
                    f"Preserve the author's key points and voice.\n\n"
                    f"Title: {article['title']}\n"
                    f"Author: {article['author_name']}\n\n"
                    f"{article['content_full'][:3000]}"
                )
                content, _ = generate_draft(prompt, self.config, max_tokens_override=800)
        else:
            # excerpt mode
            content = (article.get("content_full", "") or "")[:500]

        # Add attribution
        attribution = f"\n\n---\n*By {article['author_name']}"
        if article.get("author_bio"):
            attribution += f" — {article['author_bio']}"
        attribution += "*"
        content += attribution

        draft_id = self.repo.create_draft(
            issue_id=issue_id,
            section_slug=section_slug,
            content=content,
            ai_model="guest",
            prompt_used=f"Guest article by {article['author_name']}",
        )

        self.repo.update_guest_article(article_id, draft_id=draft_id)
        return draft_id
