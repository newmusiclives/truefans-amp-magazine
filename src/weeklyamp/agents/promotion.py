"""Promotion agent — grows subscriber base through campaigns and partnerships."""

from __future__ import annotations

import json
from typing import Optional

from weeklyamp.agents.base import AgentBase
from weeklyamp.content.generator import generate_draft


class PromotionAgent(AgentBase):
    agent_type = "promotion"
    default_name = "Promotion Lead"
    default_persona = "Creative growth marketer specializing in newsletter subscriber acquisition and community building."
    default_system_prompt = (
        "You are the Promotion Lead for TrueFans NEWSLETTERS. "
        "You design subscriber growth campaigns, craft referral programs, "
        "run cross-promotions, and build partnerships that drive sign-ups."
    )

    def _run(self, task_id: int) -> Optional[dict]:
        task = self.repo.get_task(task_id)
        if not task:
            return {"error": "Task not found"}

        task_type = task["task_type"]
        input_data = json.loads(task.get("input_json", "{}"))

        if task_type == "identify_partners":
            return self.identify_partners(task_id)
        elif task_type == "draft_campaign":
            return self.draft_campaign(task_id, input_data.get("campaign_type", "referral"))
        elif task_type == "draft_cross_promo":
            return self.draft_cross_promo(task_id, input_data.get("partner_name"))
        elif task_type == "analyze_growth":
            return self.analyze_growth(task_id)
        else:
            return {"error": f"Unknown task type: {task_type}"}

    def identify_partners(self, task_id: int) -> dict:
        """AI-generate list of potential cross-promotion partners."""
        subscriber_count = self.repo.get_subscriber_count()

        prompt = (
            f"Suggest 5 newsletters, podcasts, or communities that would be ideal "
            f"cross-promotion partners for TrueFans NEWSLETTERS, a music newsletter "
            f"with {subscriber_count} subscribers across three editions (Fan, Artist, Industry). "
            f"For each, suggest: partner name/type, their likely audience size, "
            f"why the audiences overlap, and a specific cross-promotion idea."
        )

        partners, model = generate_draft(prompt, self.config, max_tokens_override=800)
        self.log_output(task_id, "partners", partners)

        return {"partners": partners}

    def draft_campaign(self, task_id: int, campaign_type: str = "referral") -> dict:
        """Generate a subscriber acquisition campaign plan."""
        subscriber_count = self.repo.get_subscriber_count()

        prompt = (
            f"Design a {campaign_type} campaign for TrueFans NEWSLETTERS to acquire "
            f"new subscribers. Current subscriber count: {subscriber_count}.\n\n"
            f"Include:\n"
            f"1. Campaign concept and hook\n"
            f"2. Target audience and channels\n"
            f"3. Incentive structure (if referral)\n"
            f"4. Timeline and milestones\n"
            f"5. Success metrics and goals\n"
            f"6. Sample copy for the main CTA"
        )

        campaign, model = generate_draft(prompt, self.config, max_tokens_override=1000)
        self.log_output(task_id, "campaign_plan", campaign)

        return {"campaign_type": campaign_type, "campaign": campaign}

    def draft_cross_promo(self, task_id: int, partner_name: Optional[str] = None) -> dict:
        """Generate a cross-promotion pitch for a partner."""
        if not partner_name:
            return {"error": "partner_name required"}

        subscriber_count = self.repo.get_subscriber_count()

        prompt = (
            f"Write a cross-promotion outreach email to {partner_name} on behalf of "
            f"TrueFans NEWSLETTERS ({subscriber_count} subscribers, music-focused).\n\n"
            f"Propose a mutual promotion swap: we feature them to our audience, "
            f"they feature us to theirs. Be specific about what we'd offer and "
            f"what we'd ask for. Keep it casual and collaborative, not salesy."
        )

        email, model = generate_draft(prompt, self.config, max_tokens_override=800)
        self.log_output(task_id, "cross_promo_email", email)

        return {"partner_name": partner_name, "email": email}

    def analyze_growth(self, task_id: int) -> dict:
        """Analyze current growth metrics and suggest next actions."""
        subscriber_count = self.repo.get_subscriber_count()

        prompt = (
            f"Analyze the growth situation for TrueFans NEWSLETTERS "
            f"({subscriber_count} subscribers) and suggest 3 immediate actions "
            f"to accelerate subscriber acquisition this week. Focus on tactics "
            f"that are free or low-cost, leverage existing content, and can be "
            f"executed quickly. Be specific and actionable."
        )

        analysis, model = generate_draft(prompt, self.config, max_tokens_override=800)
        self.log_output(task_id, "growth_analysis", analysis)

        return {"subscriber_count": subscriber_count, "analysis": analysis}
