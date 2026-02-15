"""Base agent class with state machine and task management."""

from __future__ import annotations

import json
from typing import Optional

from weeklyamp.core.config import load_config
from weeklyamp.core.models import AppConfig
from weeklyamp.db.repository import Repository


class AgentBase:
    """Base class for all AI agents.

    State machine: idle -> assigned -> working -> review -> complete (or failed/cancelled)
    """

    agent_type: str = ""
    default_name: str = ""
    default_persona: str = ""
    default_system_prompt: str = ""

    def __init__(self, repo: Repository, config: Optional[AppConfig] = None) -> None:
        self.repo = repo
        self.config = config or load_config()
        self._agent_row: Optional[dict] = None

    def _ensure_agent(self) -> dict:
        """Get or create this agent's database record."""
        if self._agent_row:
            return self._agent_row

        agent = self.repo.get_agent_by_type(self.agent_type)
        if not agent:
            agent_id = self.repo.create_agent(
                agent_type=self.agent_type,
                name=self.default_name,
                persona=self.default_persona,
                system_prompt=self.default_system_prompt,
                autonomy_level=self.config.agents.default_autonomy,
            )
            agent = self.repo.get_agent(agent_id)

        self._agent_row = agent
        return agent

    @property
    def agent_id(self) -> int:
        return self._ensure_agent()["id"]

    def assign_task(
        self, task_type: str, input_data: Optional[dict] = None,
        issue_id: Optional[int] = None, section_slug: str = "",
        priority: int = 5,
    ) -> int:
        """Create an assigned task for this agent."""
        self._ensure_agent()
        input_json = json.dumps(input_data or {})
        return self.repo.create_agent_task(
            agent_id=self.agent_id,
            task_type=task_type,
            priority=priority,
            input_json=input_json,
            issue_id=issue_id,
            section_slug=section_slug,
        )

    def execute(self, task_id: int) -> dict:
        """Run the agent's logic for a task. Override in subclasses."""
        self.repo.update_task_state(task_id, "working")
        try:
            result = self._run(task_id)
            output_json = json.dumps(result or {})

            if self.config.agents.review_required:
                self.repo.update_task_state(task_id, "review", output_json)
            else:
                self.repo.update_task_state(task_id, "complete", output_json)

            return result or {}
        except Exception as e:
            self.repo.update_task_state(task_id, "failed", json.dumps({"error": str(e)}))
            raise

    def _run(self, task_id: int) -> Optional[dict]:
        """Subclass-specific logic. Override this."""
        raise NotImplementedError

    def submit_for_review(self, task_id: int) -> None:
        """Move task to review state for human checkpoint."""
        self.repo.update_task_state(task_id, "review")

    def mark_complete(self, task_id: int) -> None:
        """Mark a task as complete (after review approval)."""
        self.repo.update_task_state(task_id, "complete")

    def override(self, task_id: int, human_notes: str) -> None:
        """Human override of a task."""
        self.repo.override_task(task_id, human_notes)

    def log_output(
        self, task_id: int, output_type: str = "",
        content: str = "", metadata: Optional[dict] = None,
        tokens_used: int = 0,
    ) -> int:
        """Log agent output for auditing."""
        return self.repo.log_agent_output(
            task_id=task_id,
            agent_id=self.agent_id,
            output_type=output_type,
            content=content,
            metadata_json=json.dumps(metadata or {}),
            tokens_used=tokens_used,
        )

    def get_pending_tasks(self) -> list[dict]:
        """Get tasks assigned to this agent."""
        return self.repo.get_agent_tasks(agent_id=self.agent_id, state="assigned")
