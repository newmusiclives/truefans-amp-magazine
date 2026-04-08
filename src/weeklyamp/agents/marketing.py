"""Marketing automation agent — Chief Marketing Officer that orchestrates
the per-edition Sales and Promotion specialists.

This agent does not directly draft prospects, partners, or outreach.
Those tasks live on `SalesAgent` and `PromotionAgent`, which exist as
named per-edition staff (Kyle/Dana/Talia for Sales, Jess/Cody/Ryan for
Promotion) seeded into the database. MarketingAgent fans tasks out to
those specialists — one task per agent row, the same pattern the
orchestrator uses for Writers.

Marketing keeps the cross-functional tasks that don't belong to a
single edition specialist:
  - draft_social_batch        — promotes published issues across all editions
  - identify_at_risk          — churn detection across all subscribers
  - draft_winback_batch       — re-engagement copy
  - weekly_marketing_report   — portfolio-level performance summary

The fan-out tasks (`identify_prospects`, `draft_outreach_batch`)
return per-edition results aggregated into a single response so the
caller can see what each specialist produced without needing to know
the team structure.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from weeklyamp.agents.base import AgentBase
from weeklyamp.agents.promotion import PromotionAgent
from weeklyamp.agents.sales import SalesAgent
from weeklyamp.content.generator import generate_draft

logger = logging.getLogger(__name__)


class MarketingAgent(AgentBase):
    agent_type = "marketing"
    default_name = "Chief Marketing Officer"
    default_persona = "Strategic marketing leader who orchestrates subscriber growth and sponsor sales."
    default_system_prompt = (
        "You are the CMO of TrueFans SIGNAL. "
        "You coordinate the Sales and Promotion leads across all editions, "
        "set portfolio-level priorities, and report on results."
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
            "identify_partners": self.identify_partners,
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

    # ---- Coordinator: fan out to per-edition specialists ----

    def identify_prospects(self, task_id: int) -> dict:
        """Fan out prospect identification to every Sales agent on the
        roster. Each Sales lead identifies prospects scoped to their
        own edition and persists them to sponsor_prospects.
        """
        return self._fanout_sales("identify_prospects", task_id)

    def draft_outreach_batch(self, task_id: int) -> dict:
        """Fan out outreach drafting to every Sales agent. Each lead
        drafts emails for the prospects their edition owns.
        """
        return self._fanout_sales("draft_outreach_batch", task_id)

    def identify_partners(self, task_id: int) -> dict:
        """Fan out cross-promo partner identification to every
        Promotion agent. Each lead identifies partners for their edition.
        """
        return self._fanout_promotion("identify_partners", task_id)

    def _fanout_sales(self, task_type: str, parent_task_id: int) -> dict:
        rows = self.repo.get_agents_by_type("sales")
        results = []
        for row in rows:
            agent = SalesAgent(self.repo, self.config, agent_id=row["id"])
            sub_task = agent.assign_task(task_type)
            try:
                result = agent.execute(sub_task)
            except Exception as e:  # specialist failure must not abort the fan-out
                logger.exception("Sales fanout failed for agent %s", row.get("name"))
                result = {"error": str(e)}
            results.append({"agent": row.get("name"), "edition": _edition_of(row), "result": result})

        self.log_output(parent_task_id, f"fanout_sales_{task_type}", json.dumps({"count": len(results)}))
        return {"task": task_type, "fanned_out_to": len(results), "results": results}

    def _fanout_promotion(self, task_type: str, parent_task_id: int) -> dict:
        rows = self.repo.get_agents_by_type("promotion")
        results = []
        for row in rows:
            agent = PromotionAgent(self.repo, self.config, agent_id=row["id"])
            sub_task = agent.assign_task(task_type)
            try:
                result = agent.execute(sub_task)
            except Exception as e:
                logger.exception("Promotion fanout failed for agent %s", row.get("name"))
                result = {"error": str(e)}
            results.append({"agent": row.get("name"), "edition": _edition_of(row), "result": result})

        self.log_output(parent_task_id, f"fanout_promotion_{task_type}", json.dumps({"count": len(results)}))
        return {"task": task_type, "fanned_out_to": len(results), "results": results}

    def generate_growth_tactics(self, task_id: int) -> dict:
        """Generate subscriber growth tactics based on current metrics."""
        subscriber_count = self.repo.get_subscriber_count()
        growth = self.repo.get_growth_trend(days=14)

        prompt = (
            f"Generate 5 actionable subscriber growth tactics for TrueFans SIGNAL.\n\n"
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
                f"of TrueFans SIGNAL ({issue.get('edition_slug', '')} edition).\n\n"
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
            f"Write a win-back email for TrueFans SIGNAL subscribers who haven't "
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
            f"Write a concise weekly marketing report for TrueFans SIGNAL.\n\n"
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


def _edition_of(agent_row: dict) -> str:
    """Extract the primary edition slug from an agent row's config_json."""
    try:
        cfg = json.loads(agent_row.get("config_json") or "{}")
    except (ValueError, TypeError):
        return ""
    return cfg.get("edition", "") or ""
