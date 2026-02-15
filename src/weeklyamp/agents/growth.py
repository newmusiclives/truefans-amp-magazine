"""Growth agent — analyzes metrics, suggests tactics, drafts social posts."""

from __future__ import annotations

import json
from typing import Optional

from weeklyamp.agents.base import AgentBase
from weeklyamp.content.generator import generate_draft


class GrowthAgent(AgentBase):
    agent_type = "growth"
    default_name = "Growth Manager"
    default_persona = "Data-driven growth strategist specializing in newsletter and community growth."
    default_system_prompt = (
        "You are the Growth Manager for TrueFans AMP Magazine. "
        "You analyze subscriber metrics, suggest growth tactics, "
        "create social media content, and plan referral campaigns."
    )

    def _run(self, task_id: int) -> Optional[dict]:
        task = self.repo.get_task(task_id)
        if not task:
            return {"error": "Task not found"}

        task_type = task["task_type"]
        input_data = json.loads(task.get("input_json", "{}"))

        if task_type == "analyze_metrics":
            return self.analyze_metrics(task_id)
        elif task_type == "suggest_tactics":
            return self.suggest_tactics(task_id)
        elif task_type == "draft_social_posts":
            return self.draft_social_posts(task_id, task.get("issue_id"))
        elif task_type == "plan_referral":
            return self.plan_referral(task_id)
        else:
            return {"error": f"Unknown task type: {task_type}"}

    def analyze_metrics(self, task_id: int) -> dict:
        """Pull stats and identify patterns."""
        subscriber_count = self.repo.get_subscriber_count()
        trend = self.repo.get_growth_trend(days=30)

        summary = {
            "current_subscribers": subscriber_count,
            "data_points": len(trend),
        }

        if trend:
            latest = trend[-1] if trend else {}
            summary.update({
                "latest_open_rate": latest.get("open_rate_avg", 0),
                "latest_new_subs": latest.get("new_subscribers", 0),
                "latest_churned": latest.get("churned_subscribers", 0),
            })

        self.log_output(task_id, "metrics_analysis", json.dumps(summary))
        return summary

    def suggest_tactics(self, task_id: int) -> dict:
        """AI-generate growth strategy recommendations."""
        subscriber_count = self.repo.get_subscriber_count()
        trend = self.repo.get_growth_trend(days=14)

        trend_text = ""
        if trend:
            trend_text = "\n".join(
                f"- {t['metric_date']}: {t['total_subscribers']} subs, "
                f"{t['open_rate_avg']:.1%} open rate"
                for t in trend[-7:]
            )

        prompt = (
            f"Suggest 5 growth tactics for TrueFans AMP Magazine, "
            f"a newsletter for independent artists with {subscriber_count} subscribers.\n\n"
            f"Recent trends:\n{trend_text or 'No data yet'}\n\n"
            f"Focus on: subscriber acquisition, retention, engagement, "
            f"and referral strategies specific to the music creator audience."
        )

        tactics, model = generate_draft(prompt, self.config, max_tokens_override=800)
        self.log_output(task_id, "growth_tactics", tactics)

        return {"tactics": tactics}

    def draft_social_posts(self, task_id: int, issue_id: Optional[int] = None) -> dict:
        """Create social media posts promoting an issue."""
        if not issue_id:
            return {"error": "issue_id required"}

        issue = self.repo.get_issue(issue_id)
        if not issue:
            return {"error": f"Issue {issue_id} not found"}

        drafts = self.repo.get_drafts_for_issue(issue_id)
        sections_text = ", ".join(d["section_slug"].replace("_", " ").title() for d in drafts[:5])

        prompt = (
            f"Create social media posts promoting Issue #{issue['issue_number']} "
            f"of TrueFans AMP Magazine.\n\n"
            f"Issue title: {issue.get('title', 'Latest Issue')}\n"
            f"Sections: {sections_text}\n\n"
            f"Write one post each for: Twitter (280 chars), Instagram (caption), "
            f"LinkedIn (professional), and Threads (conversational). "
            f"Include relevant hashtags."
        )

        posts_text, model = generate_draft(prompt, self.config, max_tokens_override=1000)

        # Save posts
        platforms = ["twitter", "instagram", "linkedin", "threads"]
        created_ids = []
        for platform in platforms:
            post_id = self.repo.create_social_post(
                platform=platform,
                content=posts_text,
                issue_id=issue_id,
                agent_task_id=task_id,
            )
            created_ids.append(post_id)

        self.log_output(task_id, "social_posts", posts_text)
        return {"posts_created": len(created_ids), "content": posts_text}

    def plan_referral(self, task_id: int) -> dict:
        """Design referral campaign ideas."""
        subscriber_count = self.repo.get_subscriber_count()

        prompt = (
            f"Design a referral campaign for TrueFans AMP Magazine "
            f"({subscriber_count} current subscribers). "
            f"Our audience: independent artists, songwriters, music creators.\n\n"
            f"Include: campaign concept, reward tiers, messaging, "
            f"and implementation steps. Keep it practical for a small team."
        )

        plan, model = generate_draft(prompt, self.config, max_tokens_override=800)
        self.log_output(task_id, "referral_plan", plan)

        return {"plan": plan}
