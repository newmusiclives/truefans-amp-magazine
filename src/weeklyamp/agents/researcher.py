"""Researcher agent — discovers content, compiles briefs, finds guest candidates."""

from __future__ import annotations

import json
from typing import Optional

from weeklyamp.agents.base import AgentBase
from weeklyamp.content.generator import generate_draft


class ResearcherAgent(AgentBase):
    agent_type = "researcher"
    default_name = "Research Analyst"
    default_persona = "Thorough music industry researcher with deep knowledge of trends and emerging artists."
    default_system_prompt = (
        "You are a research analyst for TrueFans AMP Magazine. "
        "You discover relevant content, compile research briefs, "
        "and identify potential guest contributors."
    )

    def _run(self, task_id: int) -> Optional[dict]:
        task = self.repo.get_task(task_id)
        if not task:
            return {"error": "Task not found"}

        task_type = task["task_type"]
        input_data = json.loads(task.get("input_json", "{}"))

        if task_type == "discover_content":
            return self.discover_content(task_id)
        elif task_type == "compile_brief":
            return self.compile_brief(
                task_id,
                task.get("issue_id"),
                task.get("section_slug", ""),
            )
        elif task_type == "find_guest_candidates":
            return self.find_guest_candidates(task_id)
        else:
            return {"error": f"Unknown task type: {task_type}"}

    def discover_content(self, task_id: int) -> dict:
        """Fetch and score content from configured sources."""
        from weeklyamp.research.sources import fetch_all_sources
        from weeklyamp.research.discovery import score_and_tag_content

        sources = self.repo.get_active_sources()
        total_fetched = 0

        for source in sources:
            try:
                items = fetch_all_sources(self.repo, [source])
                total_fetched += len(items)
            except Exception:
                continue

        # Score all unscored content
        unused = self.repo.get_unused_content(limit=100)
        scored = 0
        for item in unused:
            if item.get("relevance_score", 0) == 0:
                score_and_tag_content(self.repo, item["id"], item["title"], item.get("summary", ""))
                scored += 1

        self.log_output(task_id, "discovery", json.dumps({
            "fetched": total_fetched, "scored": scored,
        }))

        return {"fetched": total_fetched, "scored": scored}

    def compile_brief(self, task_id: int, issue_id: Optional[int] = None, section_slug: str = "") -> dict:
        """Aggregate relevant content into a research brief for a section."""
        if not section_slug:
            return {"error": "section_slug required"}

        content_items = self.repo.get_unused_content(section_slug, limit=10)
        if not content_items:
            return {"brief": "No relevant content found.", "items": 0}

        items_text = "\n\n".join(
            f"### {c['title']}\n{c['summary'][:300]}\nSource: {c['url']}"
            for c in content_items
        )

        prompt = (
            f"Compile a research brief for the {section_slug} section of TrueFans AMP Magazine. "
            f"Summarize the key themes, identify the most newsworthy angles, "
            f"and suggest a specific topic/angle for this week's article.\n\n"
            f"Available content:\n{items_text}"
        )

        brief, model = generate_draft(prompt, self.config, max_tokens_override=800)
        self.log_output(task_id, "brief", brief)

        return {"brief": brief, "items": len(content_items), "section": section_slug}

    def find_guest_candidates(self, task_id: int) -> dict:
        """AI-generate a list of potential guest article contributors."""
        sections = self.repo.get_active_sections()
        section_names = ", ".join(s["display_name"] for s in sections[:10])

        prompt = (
            f"Suggest 5 types of guest contributors who would be ideal for "
            f"TrueFans AMP Magazine, a publication for independent artists and songwriters. "
            f"Our sections include: {section_names}. "
            f"For each, suggest: role/title, what they'd write about, "
            f"and why our audience would value their perspective."
        )

        suggestions, model = generate_draft(prompt, self.config, max_tokens_override=800)
        self.log_output(task_id, "guest_candidates", suggestions)

        return {"suggestions": suggestions}
