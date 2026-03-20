"""Trivia and poll system for newsletter engagement.

Allows embedding interactive trivia questions and polls in newsletters.
Tracks votes, computes results, and maintains a leaderboard.
INACTIVE by default — enable via config.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from weeklyamp.core.models import TriviaPollsConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


class TriviaManager:
    """Create, manage, and render trivia questions and polls."""

    def __init__(self, repo: Repository, config: TriviaPollsConfig) -> None:
        self.repo = repo
        self.config = config

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def create_trivia(
        self,
        question_text: str,
        options: list[str],
        correct_index: int,
        target_issue_id: int,
        edition_slug: str = "",
        explanation: str = "",
    ) -> Optional[int]:
        """Create a trivia question (has a correct answer).

        *options* is a list of answer strings.  *correct_index* is the
        0-based index of the correct option.  Returns the poll id.
        """
        if not self.config.enabled:
            logger.info("Trivia/polls disabled — skipping create_trivia")
            return None

        if len(options) > self.config.max_options:
            raise ValueError(f"Too many options ({len(options)}), max is {self.config.max_options}")

        options_json = json.dumps(options)
        poll_id = self.repo.create_trivia_poll(
            question_type="trivia",
            question_text=question_text,
            options_json=options_json,
            correct_option_index=correct_index,
            explanation=explanation,
            target_issue_id=target_issue_id,
            edition_slug=edition_slug,
        )
        logger.info("Created trivia question %d for issue %d", poll_id, target_issue_id)
        return poll_id

    def create_poll(
        self,
        question_text: str,
        options: list[str],
        target_issue_id: int,
        edition_slug: str = "",
    ) -> Optional[int]:
        """Create a poll (no correct answer).  Returns the poll id."""
        if not self.config.enabled:
            logger.info("Trivia/polls disabled — skipping create_poll")
            return None

        if len(options) > self.config.max_options:
            raise ValueError(f"Too many options ({len(options)}), max is {self.config.max_options}")

        options_json = json.dumps(options)
        poll_id = self.repo.create_trivia_poll(
            question_type="poll",
            question_text=question_text,
            options_json=options_json,
            correct_option_index=-1,
            explanation="",
            target_issue_id=target_issue_id,
            edition_slug=edition_slug,
        )
        logger.info("Created poll %d for issue %d", poll_id, target_issue_id)
        return poll_id

    # ------------------------------------------------------------------
    # Voting
    # ------------------------------------------------------------------

    def record_vote(
        self, poll_id: int, subscriber_id: int, option_index: int,
    ) -> dict:
        """Record a vote.  For trivia, check correctness and update leaderboard.

        Returns ``{already_voted, is_correct, results}``.
        """
        if not self.config.enabled:
            return {"already_voted": True, "is_correct": False, "results": {}}

        # Check if already voted
        already_voted = self.repo.has_voted(poll_id, subscriber_id)
        if already_voted:
            results = self.get_results(poll_id)
            return {"already_voted": True, "is_correct": False, "results": results}

        poll = self.repo.get_trivia_poll(poll_id)
        if not poll or poll["status"] == "closed":
            return {"already_voted": False, "is_correct": False, "results": {}}

        is_correct = False
        if poll["question_type"] == "trivia" and poll["correct_option_index"] >= 0:
            is_correct = option_index == poll["correct_option_index"]

        self.repo.record_trivia_vote(poll_id, subscriber_id, option_index, is_correct)

        # Update leaderboard for trivia questions
        if poll["question_type"] == "trivia":
            self.repo.update_trivia_leaderboard(subscriber_id, is_correct)

        results = self.get_results(poll_id)
        return {"already_voted": False, "is_correct": is_correct, "results": results}

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    def get_results(self, poll_id: int) -> dict:
        """Get vote counts per option + total + percentages.

        Returns ``{votes_by_option: {idx: count}, total_votes: N,
        percentages: {idx: pct}}``.
        """
        raw = self.repo.get_trivia_results(poll_id)
        total = raw.get("total_votes", 0)
        votes_by_option = raw.get("votes_by_option", {})

        percentages: dict[int, float] = {}
        for idx, count in votes_by_option.items():
            percentages[idx] = round(count / total * 100, 1) if total > 0 else 0.0

        return {
            "votes_by_option": votes_by_option,
            "total_votes": total,
            "percentages": percentages,
        }

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def close_poll(self, poll_id: int) -> None:
        """Set poll status to 'closed'."""
        if not self.config.enabled:
            return
        self.repo.update_trivia_poll(poll_id, status="closed")
        logger.info("Closed poll %d", poll_id)

    # ------------------------------------------------------------------
    # Email rendering
    # ------------------------------------------------------------------

    def render_trivia_email_html(
        self, poll: dict, site_domain: str, issue_id: int,
    ) -> str:
        """Generate email-safe HTML for embedding a trivia/poll in a newsletter.

        Each option links to ``/t/vote/{poll_id}/{option_index}/{{subscriber_id}}``
        where ``{{subscriber_id}}`` is a placeholder replaced per-recipient.
        """
        if not self.config.enabled:
            return ""

        poll_id = poll["id"]
        question_text = poll.get("question_text", "")
        options = json.loads(poll.get("options_json", "[]"))
        is_trivia = poll.get("question_type") == "trivia"

        header = "Test your music knowledge!" if is_trivia else "Have your say!"
        header_color = "#6C3AED" if is_trivia else "#2563EB"

        domain = site_domain.rstrip("/")

        rows_html = ""
        for i, option_text in enumerate(options):
            vote_url = f"{domain}/t/vote/{poll_id}/{i}/{{{{subscriber_id}}}}"
            rows_html += f"""
            <tr>
                <td align="center" style="padding:4px 0;">
                    <a href="{vote_url}"
                       style="display:inline-block;width:90%;padding:12px 20px;
                              background-color:{header_color};color:#ffffff;
                              text-decoration:none;border-radius:6px;
                              font-family:Arial,sans-serif;font-size:15px;
                              font-weight:600;text-align:center;">
                        {option_text}
                    </a>
                </td>
            </tr>"""

        html = f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0"
       style="max-width:560px;margin:20px auto;background-color:#f9fafb;
              border-radius:8px;border:1px solid #e5e7eb;">
    <tr>
        <td style="padding:20px 24px 8px;text-align:center;">
            <span style="font-family:Arial,sans-serif;font-size:12px;
                         font-weight:700;text-transform:uppercase;
                         letter-spacing:1px;color:{header_color};">
                {header}
            </span>
        </td>
    </tr>
    <tr>
        <td style="padding:8px 24px 16px;text-align:center;">
            <span style="font-family:Arial,sans-serif;font-size:18px;
                         font-weight:700;color:#111827;line-height:1.4;">
                {question_text}
            </span>
        </td>
    </tr>
    {rows_html}
    <tr>
        <td style="padding:12px 24px 16px;text-align:center;">
            <span style="font-family:Arial,sans-serif;font-size:11px;color:#9ca3af;">
                Tap your answer above &mdash; results in the next issue!
            </span>
        </td>
    </tr>
</table>"""
        return html

    def render_results_email_html(self, poll: dict, results: dict) -> str:
        """Generate email-safe HTML showing poll/trivia results.

        Displays options with vote-percentage bar charts and highlights
        the correct answer for trivia.
        """
        if not self.config.enabled:
            return ""

        question_text = poll.get("question_text", "")
        options = json.loads(poll.get("options_json", "[]"))
        is_trivia = poll.get("question_type") == "trivia"
        correct_idx = poll.get("correct_option_index", -1)
        total_votes = results.get("total_votes", 0)
        percentages = results.get("percentages", {})
        votes_by_option = results.get("votes_by_option", {})

        rows_html = ""
        for i, option_text in enumerate(options):
            pct = percentages.get(i, 0.0)
            count = votes_by_option.get(i, 0)
            bar_width = max(pct, 2)  # minimum visible width
            is_correct = is_trivia and i == correct_idx

            bg_color = "#10B981" if is_correct else "#E5E7EB"
            text_color = "#065F46" if is_correct else "#374151"
            marker = " &#10003;" if is_correct else ""

            rows_html += f"""
            <tr>
                <td style="padding:6px 24px;">
                    <div style="font-family:Arial,sans-serif;font-size:14px;
                                font-weight:600;color:{text_color};margin-bottom:4px;">
                        {option_text}{marker}
                        <span style="float:right;font-weight:400;font-size:13px;color:#6B7280;">
                            {count} ({pct}%)
                        </span>
                    </div>
                    <div style="background-color:#F3F4F6;border-radius:4px;height:8px;width:100%;">
                        <div style="background-color:{bg_color};border-radius:4px;
                                    height:8px;width:{bar_width}%;"></div>
                    </div>
                </td>
            </tr>"""

        html = f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0"
       style="max-width:560px;margin:20px auto;background-color:#f9fafb;
              border-radius:8px;border:1px solid #e5e7eb;">
    <tr>
        <td style="padding:20px 24px 8px;text-align:center;">
            <span style="font-family:Arial,sans-serif;font-size:12px;
                         font-weight:700;text-transform:uppercase;
                         letter-spacing:1px;color:#6C3AED;">
                Results
            </span>
        </td>
    </tr>
    <tr>
        <td style="padding:8px 24px 12px;text-align:center;">
            <span style="font-family:Arial,sans-serif;font-size:16px;
                         font-weight:700;color:#111827;line-height:1.4;">
                {question_text}
            </span>
        </td>
    </tr>
    {rows_html}
    <tr>
        <td style="padding:12px 24px 16px;text-align:center;">
            <span style="font-family:Arial,sans-serif;font-size:12px;color:#9ca3af;">
                {total_votes} total vote{"s" if total_votes != 1 else ""}
            </span>
        </td>
    </tr>
</table>"""
        return html

    # ------------------------------------------------------------------
    # Leaderboard
    # ------------------------------------------------------------------

    def get_leaderboard(self, limit: int = 25) -> list[dict]:
        """Return the trivia leaderboard from the repository."""
        if not self.config.enabled:
            return []
        return self.repo.get_trivia_leaderboard(limit=limit)
