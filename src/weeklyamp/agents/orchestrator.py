"""Agent orchestrator — coordinates the AI staff workflow."""

from __future__ import annotations

from typing import Optional

from weeklyamp.agents.editor import EditorInChiefAgent
from weeklyamp.agents.growth import GrowthAgent
from weeklyamp.agents.researcher import ResearcherAgent
from weeklyamp.agents.sales import SalesAgent
from weeklyamp.agents.writer import WriterAgent
from weeklyamp.core.models import AppConfig
from weeklyamp.db.repository import Repository


AGENT_CLASSES = {
    "editor_in_chief": EditorInChiefAgent,
    "writer": WriterAgent,
    "researcher": ResearcherAgent,
    "sales": SalesAgent,
    "growth": GrowthAgent,
}


class AgentOrchestrator:
    """Coordinates the AI staff: runs cycles, triggers agents, manages reviews."""

    def __init__(self, repo: Repository, config: Optional[AppConfig] = None) -> None:
        self.repo = repo
        self.config = config
        self._agents: dict[str, object] = {}

    def _get_agent(self, agent_type: str):
        """Get or create an agent instance."""
        if agent_type not in self._agents:
            cls = AGENT_CLASSES.get(agent_type)
            if not cls:
                raise ValueError(f"Unknown agent type: {agent_type}")
            self._agents[agent_type] = cls(self.repo, self.config)
        return self._agents[agent_type]

    def run_autonomous_cycle(self, issue_id: Optional[int] = None) -> dict:
        """Run one full cycle: Researcher -> Editor -> Writers -> review checkpoint."""
        results = {}

        if not issue_id:
            issue = self.repo.get_current_issue()
            if not issue:
                return {"error": "No current issue found"}
            issue_id = issue["id"]

        # Step 1: Researcher discovers content
        researcher = self._get_agent("researcher")
        task_id = researcher.assign_task("discover_content", issue_id=issue_id)
        try:
            results["research"] = researcher.execute(task_id)
        except Exception as e:
            results["research"] = {"error": str(e)}

        # Step 2: Editor plans the issue
        editor = self._get_agent("editor_in_chief")
        task_id = editor.assign_task("plan_issue", issue_id=issue_id)
        try:
            results["planning"] = editor.execute(task_id)
        except Exception as e:
            results["planning"] = {"error": str(e)}

        # Step 3: Editor assigns sections to writer
        task_id = editor.assign_task("assign_sections", issue_id=issue_id)
        try:
            results["assignments"] = editor.execute(task_id)
        except Exception as e:
            results["assignments"] = {"error": str(e)}

        # Step 4: Writer executes pending tasks
        writer = self._get_agent("writer")
        pending = writer.get_pending_tasks()
        write_results = []
        for task in pending:
            if task.get("issue_id") == issue_id:
                try:
                    r = writer.execute(task["id"])
                    write_results.append(r)
                except Exception as e:
                    write_results.append({"error": str(e), "task_id": task["id"]})

        results["writing"] = {"completed": len(write_results), "details": write_results}

        # Step 5: Review checkpoint — tasks are now in 'review' state
        results["status"] = "review_checkpoint"
        results["pending_reviews"] = len(self.check_pending_reviews())

        return results

    def trigger_agent(self, agent_type: str, task_type: str, **kwargs) -> dict:
        """Manually trigger a specific agent to run a task."""
        agent = self._get_agent(agent_type)
        task_id = agent.assign_task(
            task_type,
            input_data=kwargs.get("input_data"),
            issue_id=kwargs.get("issue_id"),
            section_slug=kwargs.get("section_slug", ""),
        )
        return agent.execute(task_id)

    def check_pending_reviews(self) -> list[dict]:
        """Return tasks awaiting human approval."""
        return self.repo.get_tasks_for_review()

    def get_staff_status(self) -> list[dict]:
        """Overview of all agents and their current state."""
        agents = self.repo.get_agents()
        status = []
        for agent in agents:
            tasks = self.repo.get_agent_tasks(agent_id=agent["id"])
            active = [t for t in tasks if t["state"] in ("assigned", "working")]
            review = [t for t in tasks if t["state"] == "review"]
            complete = [t for t in tasks if t["state"] == "complete"]
            failed = [t for t in tasks if t["state"] == "failed"]
            status.append({
                **agent,
                "active_tasks": len(active),
                "review_tasks": len(review),
                "completed_tasks": len(complete),
                "failed_tasks": len(failed),
                "total_tasks": len(tasks),
            })
        return status
