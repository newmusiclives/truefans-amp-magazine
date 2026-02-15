"""Editor-in-Chief agent — plans issues, assigns sections, reviews drafts."""

from __future__ import annotations

import json
from typing import Optional

from weeklyamp.agents.base import AgentBase
from weeklyamp.content.generator import generate_draft
from weeklyamp.content.rotation import select_rotating_sections


class EditorInChiefAgent(AgentBase):
    agent_type = "editor_in_chief"
    default_name = "Editor-in-Chief"
    default_persona = "Experienced magazine editor with a keen eye for compelling content and audience engagement."
    default_system_prompt = (
        "You are the Editor-in-Chief of TrueFans AMP Magazine. "
        "You plan issues, assign sections to writers, review drafts for quality, "
        "and ensure each issue tells a cohesive story for independent artists."
    )

    def _run(self, task_id: int) -> Optional[dict]:
        task = self.repo.get_task(task_id)
        if not task:
            return {"error": "Task not found"}

        task_type = task["task_type"]
        input_data = json.loads(task.get("input_json", "{}"))

        if task_type == "plan_issue":
            return self.plan_issue(task_id, task.get("issue_id"))
        elif task_type == "assign_sections":
            return self.assign_sections(task_id, task.get("issue_id"))
        elif task_type == "review_drafts":
            return self.review_drafts(task_id, task.get("issue_id"))
        elif task_type == "approve_issue":
            return self.approve_issue(task_id, task.get("issue_id"))
        else:
            return {"error": f"Unknown task type: {task_type}"}

    def plan_issue(self, task_id: int, issue_id: Optional[int] = None) -> dict:
        """Decide which sections to include and create editorial calendar entry."""
        if not issue_id:
            return {"error": "No issue_id provided"}

        issue = self.repo.get_issue(issue_id)
        if not issue:
            return {"error": f"Issue {issue_id} not found"}

        # Select rotating sections
        rotating_slugs = select_rotating_sections(self.repo)
        core_sections = self.repo.get_sections_by_type("core")
        core_slugs = [s["slug"] for s in core_sections]

        all_slugs = core_slugs + rotating_slugs

        # Create calendar entry
        self.repo.create_calendar_entry(
            issue_id=issue_id,
            theme=issue.get("title", ""),
            section_assignments=json.dumps(all_slugs),
            status="planned",
        )

        self.log_output(task_id, "plan", json.dumps({
            "core_sections": core_slugs,
            "rotating_sections": rotating_slugs,
        }))

        return {"sections": all_slugs, "issue_id": issue_id}

    def assign_sections(self, task_id: int, issue_id: Optional[int] = None) -> dict:
        """Create writer tasks for each section in the issue."""
        if not issue_id:
            return {"error": "No issue_id provided"}

        writer = self.repo.get_agent_by_type("writer")
        if not writer:
            return {"error": "No writer agent found"}

        sections = self.repo.get_active_sections()
        created_tasks = []

        for sec in sections:
            t_id = self.repo.create_agent_task(
                agent_id=writer["id"],
                task_type="write_section",
                issue_id=issue_id,
                section_slug=sec["slug"],
                priority=3,
            )
            created_tasks.append({"task_id": t_id, "section": sec["slug"]})

        self.log_output(task_id, "assignments", json.dumps(created_tasks))
        return {"assigned": len(created_tasks), "tasks": created_tasks}

    def review_drafts(self, task_id: int, issue_id: Optional[int] = None) -> dict:
        """AI-review each draft for the issue."""
        if not issue_id:
            return {"error": "No issue_id provided"}

        drafts = self.repo.get_drafts_for_issue(issue_id)
        reviews = []

        for draft in drafts:
            if draft["status"] not in ("pending", "revised"):
                continue

            prompt = (
                f"Review this newsletter section draft. Rate it 1-10 for quality, "
                f"relevance, and tone. Suggest specific improvements if needed.\n\n"
                f"Section: {draft['section_slug']}\n"
                f"Content:\n{draft['content'][:2000]}"
            )

            try:
                review_text, model = generate_draft(prompt, self.config, max_tokens_override=500)
                reviews.append({
                    "draft_id": draft["id"],
                    "section": draft["section_slug"],
                    "review": review_text,
                })
            except Exception as e:
                reviews.append({
                    "draft_id": draft["id"],
                    "section": draft["section_slug"],
                    "error": str(e),
                })

        self.log_output(task_id, "reviews", json.dumps(reviews))
        return {"reviewed": len(reviews), "reviews": reviews}

    def approve_issue(self, task_id: int, issue_id: Optional[int] = None) -> dict:
        """Mark all approved drafts and advance issue status."""
        if not issue_id:
            return {"error": "No issue_id provided"}

        drafts = self.repo.get_drafts_for_issue(issue_id)
        approved = 0
        for draft in drafts:
            if draft["status"] == "pending":
                self.repo.update_draft_status(draft["id"], "approved")
                approved += 1

        self.repo.update_issue_status(issue_id, "reviewing")
        self.log_output(task_id, "approval", json.dumps({"approved": approved}))
        return {"approved": approved, "issue_id": issue_id}
