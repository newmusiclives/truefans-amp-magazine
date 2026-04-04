"""Marketing automation agent — AI CMO for subscriber growth and sponsor sales."""

from __future__ import annotations

import json
import logging
from typing import Optional

from weeklyamp.agents.base import AgentBase
from weeklyamp.content.generator import generate_draft

logger = logging.getLogger(__name__)


class MarketingAgent(AgentBase):
    agent_type = "marketing"
    default_name = "Chief Marketing Officer"
    default_persona = "Strategic marketing leader who orchestrates subscriber growth and sponsor sales."
    default_system_prompt = (
        "You are the CMO of TrueFans NEWSLETTERS. "
        "You plan and execute marketing campaigns for subscriber growth "
        "and sponsor sales across email, SMS, voice, and AI channels."
    )

    def _run(self, task_id: int) -> Optional[dict]:
        task = self.repo.get_task(task_id)
        if not task:
            return {"error": "Task not found"}

        task_type = task["task_type"]
        input_data = json.loads(task.get("input_json", "{}"))

        handlers = {
            "identify_prospects": self.identify_prospects,
            "draft_outreach_batch": self.draft_outreach_batch,
            "generate_growth_tactics": self.generate_growth_tactics,
            "draft_social_batch": self.draft_social_batch,
            "identify_at_risk": self.identify_at_risk,
            "draft_winback_batch": self.draft_winback_batch,
            "weekly_marketing_report": self.weekly_marketing_report,
        }

        handler = handlers.get(task_type)
        if handler:
            return handler(task_id)
        return {"error": f"Unknown task type: {task_type}"}

    def identify_prospects(self, task_id: int) -> dict:
        """AI-identify new sponsor prospects based on edition audiences."""
        subscriber_count = self.repo.get_subscriber_count()
        editions = self.repo.get_editions()
        edition_names = ", ".join(e["name"] for e in editions)

        prompt = (
            f"Identify 5 companies that would be ideal sponsors for TrueFans NEWSLETTERS.\n\n"
            f"We have {subscriber_count} subscribers across these editions: {edition_names}.\n"
            f"Our audience: music fans, independent artists, and industry professionals.\n\n"
            f"For each company provide:\n"
            f"1. Company name\n"
            f"2. Why they'd sponsor (audience alignment)\n"
            f"3. Estimated budget range\n"
            f"4. Best edition(s) to target\n"
            f"5. Suggested pitch angle\n\n"
            f"Focus on companies that actively advertise in music/entertainment/creator spaces."
        )

        result, model = generate_draft(prompt, self.config, max_tokens_override=1000)
        self.log_output(task_id, "prospect_list", result)
        return {"prospects": result, "count": 5}

    def draft_outreach_batch(self, task_id: int) -> dict:
        """Draft personalized outreach emails for pending prospects."""
        prospects = self.repo.get_sponsor_prospects(status="identified")
        subscriber_count = self.repo.get_subscriber_count()
        drafted = 0

        for prospect in prospects[:5]:  # Batch of 5
            prompt = (
                f"Write a personalized sponsorship outreach email for TrueFans NEWSLETTERS.\n\n"
                f"Prospect: {prospect['company_name']}\n"
                f"Contact: {prospect.get('contact_name', 'Marketing Team')}\n"
                f"Website: {prospect.get('website', 'N/A')}\n"
                f"Category: {prospect.get('category', 'general')}\n"
                f"Target editions: {prospect.get('target_editions', 'all')}\n\n"
                f"Our stats: {subscriber_count} subscribers, 3 editions (Fan/Artist/Industry), "
                f"3x weekly publication.\n\n"
                f"Write a warm, professional 150-word email. Sign as Grant Sullivan, VP of Sales."
            )

            email, model = generate_draft(prompt, self.config, max_tokens_override=500)
            if email:
                self.repo.log_outreach(
                    campaign_id=0, channel="email",
                    recipient_email=prospect.get("contact_email", ""),
                    recipient_name=prospect.get("contact_name", ""),
                    recipient_type="sponsor_prospect", status="queued",
                )
                self.repo.update_prospect_status(prospect["id"], "contacted")
                drafted += 1

        self.log_output(task_id, "outreach_batch", f"Drafted {drafted} outreach emails")
        return {"drafted": drafted}

    def generate_growth_tactics(self, task_id: int) -> dict:
        """Generate subscriber growth tactics based on current metrics."""
        subscriber_count = self.repo.get_subscriber_count()
        growth = self.repo.get_growth_trend(days=14)

        prompt = (
            f"Generate 5 actionable subscriber growth tactics for TrueFans NEWSLETTERS.\n\n"
            f"Current subscribers: {subscriber_count}\n"
            f"Editions: Fan (music fans), Artist (indie musicians), Industry (music business)\n"
            f"Frequency: 3x weekly per edition\n\n"
            f"Focus on tactics that are:\n"
            f"1. Free or low-cost\n"
            f"2. Can be executed this week\n"
            f"3. Leverage existing content and audience\n"
            f"4. Use available channels: email, SMS, social, cross-promotion\n\n"
            f"For each tactic: name, channel, expected impact, steps to execute."
        )

        tactics, model = generate_draft(prompt, self.config, max_tokens_override=800)
        self.log_output(task_id, "growth_tactics", tactics)
        return {"tactics": tactics}

    def draft_social_batch(self, task_id: int) -> dict:
        """Draft social media posts promoting recent issues."""
        issues = self.repo.get_published_issues(limit=3)
        if not issues:
            return {"drafted": 0, "message": "No published issues to promote"}

        posts_created = 0
        for issue in issues:
            prompt = (
                f"Write 3 social media posts promoting Issue #{issue['issue_number']} "
                f"of TrueFans NEWSLETTERS ({issue.get('edition_slug', '')} edition).\n\n"
                f"1. Twitter/X (max 280 chars, include hashtags)\n"
                f"2. LinkedIn (professional tone, 2-3 paragraphs)\n"
                f"3. Instagram caption (engaging, include emojis)\n\n"
                f"Include a call-to-action to subscribe."
            )

            content, model = generate_draft(prompt, self.config, max_tokens_override=600)
            if content:
                self.repo.create_social_post(
                    platform="twitter", content=content[:500],
                    issue_id=issue["id"], status="draft",
                    scheduled_at="", agent_task_id=task_id,
                )
                posts_created += 1

        self.log_output(task_id, "social_batch", f"Created {posts_created} social post drafts")
        return {"drafted": posts_created}

    def identify_at_risk(self, task_id: int) -> dict:
        """Identify subscribers at risk of churning."""
        at_risk = self.repo.get_at_risk_subscribers(days_inactive=14, limit=50)
        self.log_output(task_id, "at_risk_subscribers", json.dumps({"count": len(at_risk)}))
        return {"at_risk_count": len(at_risk), "subscribers": [s.get("email", "") for s in at_risk[:10]]}

    def draft_winback_batch(self, task_id: int) -> dict:
        """Draft win-back emails for at-risk subscribers."""
        at_risk = self.repo.get_at_risk_subscribers(days_inactive=14, limit=20)
        if not at_risk:
            return {"drafted": 0, "message": "No at-risk subscribers found"}

        prompt = (
            f"Write a win-back email for TrueFans NEWSLETTERS subscribers who haven't "
            f"opened an email in 2+ weeks.\n\n"
            f"The email should:\n"
            f"1. Acknowledge they've been away (no guilt)\n"
            f"2. Highlight 2-3 recent highlights they missed\n"
            f"3. Give them a reason to come back\n"
            f"4. Include an easy one-click 'Stay Subscribed' link\n"
            f"5. Be warm and human, signed by Paul Saunders\n\n"
            f"Keep it under 150 words."
        )

        email, model = generate_draft(prompt, self.config, max_tokens_override=400)
        self.log_output(task_id, "winback_email", email)

        # Log outreach for each at-risk subscriber
        for sub in at_risk:
            self.repo.log_outreach(
                channel="email", recipient_email=sub.get("email", ""),
                recipient_type="subscriber", status="queued",
            )

        return {"drafted": 1, "recipients": len(at_risk), "template": email}

    def weekly_marketing_report(self, task_id: int) -> dict:
        """Generate weekly marketing performance report."""
        stats = self.repo.get_outreach_stats()
        subscriber_count = self.repo.get_subscriber_count()
        prospects = self.repo.get_sponsor_prospects()

        pipeline = {}
        for p in prospects:
            status = p.get("status", "unknown")
            pipeline[status] = pipeline.get(status, 0) + 1

        prompt = (
            f"Write a concise weekly marketing report for TrueFans NEWSLETTERS.\n\n"
            f"Subscriber count: {subscriber_count}\n"
            f"Total outreach sent: {stats.get('total_outreach', 0)}\n"
            f"Active campaigns: {stats.get('active_campaigns', 0)}\n"
            f"Sponsor prospects: {stats.get('total_prospects', 0)}\n"
            f"Pipeline breakdown: {json.dumps(pipeline)}\n\n"
            f"Include: key wins, areas for improvement, and 3 priorities for next week.\n"
            f"Keep it under 300 words. Professional but actionable tone."
        )

        report, model = generate_draft(prompt, self.config, max_tokens_override=600)
        self.log_output(task_id, "weekly_report", report)
        return {"report": report}
