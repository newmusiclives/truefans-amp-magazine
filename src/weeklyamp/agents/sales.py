"""Sales agent — identifies sponsor prospects and drafts outreach."""

from __future__ import annotations

import json
from typing import Optional

from weeklyamp.agents.base import AgentBase
from weeklyamp.content.generator import generate_draft


class SalesAgent(AgentBase):
    agent_type = "sales"
    default_name = "Sales Director"
    default_persona = "Strategic sales professional with deep understanding of the music industry advertising landscape."
    default_system_prompt = (
        "You are the Sales Director for TrueFans AMP Magazine. "
        "You identify potential sponsors, draft outreach emails, "
        "and manage the sponsorship pipeline."
    )

    def _run(self, task_id: int) -> Optional[dict]:
        task = self.repo.get_task(task_id)
        if not task:
            return {"error": "Task not found"}

        task_type = task["task_type"]
        input_data = json.loads(task.get("input_json", "{}"))

        if task_type == "identify_prospects":
            return self.identify_prospects(task_id)
        elif task_type == "draft_outreach":
            return self.draft_outreach(task_id, input_data.get("sponsor_id"))
        elif task_type == "update_pipeline":
            return self.update_pipeline(task_id)
        else:
            return {"error": f"Unknown task type: {task_type}"}

    def identify_prospects(self, task_id: int) -> dict:
        """AI-generate list of potential sponsor companies."""
        subscriber_count = self.repo.get_subscriber_count()

        prompt = (
            f"Suggest 5 types of companies that would be ideal sponsors for "
            f"TrueFans AMP Magazine, a newsletter/magazine for independent artists "
            f"and songwriters with {subscriber_count} subscribers. "
            f"For each, suggest: company type, why they'd sponsor, "
            f"estimated budget range, and a pitch angle."
        )

        prospects, model = generate_draft(prompt, self.config, max_tokens_override=800)
        self.log_output(task_id, "prospects", prospects)

        return {"prospects": prospects}

    def draft_outreach(self, task_id: int, sponsor_id: Optional[int] = None) -> dict:
        """Generate personalized outreach email for a sponsor."""
        if not sponsor_id:
            return {"error": "sponsor_id required"}

        sponsor = self.repo.get_sponsor(sponsor_id)
        if not sponsor:
            return {"error": f"Sponsor {sponsor_id} not found"}

        subscriber_count = self.repo.get_subscriber_count()

        prompt = (
            f"Write a personalized sponsorship outreach email for TrueFans AMP Magazine.\n\n"
            f"Sponsor: {sponsor['name']}\n"
            f"Contact: {sponsor.get('contact_name', 'N/A')}\n"
            f"Website: {sponsor.get('website', 'N/A')}\n"
            f"Notes: {sponsor.get('notes', '')}\n\n"
            f"Our stats: {subscriber_count} subscribers, weekly publication, "
            f"audience of independent artists and songwriters.\n"
            f"Available positions: top, mid, bottom of newsletter.\n\n"
            f"Write a warm, professional email that highlights the alignment "
            f"between their brand and our audience."
        )

        email, model = generate_draft(prompt, self.config, max_tokens_override=800)
        self.log_output(task_id, "outreach_email", email)

        return {"sponsor_id": sponsor_id, "email": email}

    def update_pipeline(self, task_id: int) -> dict:
        """Review booking statuses and suggest follow-up actions."""
        sponsors = self.repo.get_sponsors()
        pipeline_summary = []

        for sponsor in sponsors:
            bookings = self.repo.get_bookings_for_sponsor(sponsor["id"])
            pipeline_summary.append({
                "sponsor": sponsor["name"],
                "bookings": len(bookings),
                "statuses": [b["status"] for b in bookings],
            })

        self.log_output(task_id, "pipeline_review", json.dumps(pipeline_summary))
        return {"sponsors_reviewed": len(sponsors), "pipeline": pipeline_summary}
