"""Writer agent — generates and rewrites section drafts."""

from __future__ import annotations

import json
from typing import Optional

from weeklyamp.agents.base import AgentBase
from weeklyamp.content.generator import generate_draft
from weeklyamp.core.config import get_prompt_template
from weeklyamp.core.models import WORD_COUNT_MAX_TOKENS


class WriterAgent(AgentBase):
    agent_type = "writer"
    default_name = "Staff Writer"
    default_persona = "Versatile music journalist who can adapt tone and style to any section."
    default_system_prompt = (
        "You are a staff writer for TrueFans AMP Magazine. "
        "You write compelling, accurate content for independent artists and songwriters. "
        "Match the tone and style specified for each section."
    )

    def _run(self, task_id: int) -> Optional[dict]:
        task = self.repo.get_task(task_id)
        if not task:
            return {"error": "Task not found"}

        task_type = task["task_type"]
        input_data = json.loads(task.get("input_json", "{}"))

        if task_type == "write_section":
            return self.write_section(
                task_id,
                task.get("issue_id"),
                task.get("section_slug", ""),
            )
        elif task_type == "rewrite":
            return self.rewrite(
                task_id,
                input_data.get("draft_id"),
                input_data.get("feedback", ""),
            )
        elif task_type == "adapt_tone":
            return self.adapt_tone(
                task_id,
                input_data.get("draft_id"),
                input_data.get("tone_direction", ""),
            )
        else:
            return {"error": f"Unknown task type: {task_type}"}

    def write_section(self, task_id: int, issue_id: Optional[int] = None, section_slug: str = "") -> dict:
        """Write a section draft using prompt template and generate_draft."""
        if not issue_id or not section_slug:
            return {"error": "issue_id and section_slug required"}

        section = self.repo.get_section(section_slug)
        if not section:
            return {"error": f"Section {section_slug} not found"}

        # Load prompt template
        template = get_prompt_template(section_slug)
        if not template:
            template = f"Write the {section['display_name']} section for the newsletter."

        # Get editorial inputs
        inputs = self.repo.get_editorial_inputs(issue_id, section_slug)
        topic = inputs[0]["topic"] if inputs else ""
        notes = inputs[0]["notes"] if inputs else ""
        refs = inputs[0].get("reference_urls", "") if inputs else ""

        # Get relevant research content
        content_items = self.repo.get_unused_content(section_slug, limit=3)
        reference_content = "\n".join(
            f"- {c['title']}: {c['summary'][:200]}" for c in content_items
        )

        # Build prompt
        prompt = template.replace("{{newsletter_name}}", self.config.newsletter.name)
        prompt = prompt.replace("{{topic}}", topic)
        prompt = prompt.replace("{{notes}}", notes)
        prompt = prompt.replace("{{reference_content}}", reference_content or refs)

        # Determine max tokens from word count label
        wc_label = section.get("word_count_label", "medium")
        max_tokens = WORD_COUNT_MAX_TOKENS.get(wc_label, 1500)

        # Generate
        content, model = generate_draft(prompt, self.config, max_tokens_override=max_tokens)

        # Save draft
        draft_id = self.repo.create_draft(
            issue_id=issue_id,
            section_slug=section_slug,
            content=content,
            ai_model=model,
            prompt_used=prompt[:500],
        )

        # Mark content as used
        for c in content_items:
            self.repo.mark_content_used(c["id"])

        self.log_output(task_id, "draft", content, tokens_used=max_tokens)

        return {"draft_id": draft_id, "section": section_slug, "word_count": len(content.split())}

    def rewrite(self, task_id: int, draft_id: Optional[int] = None, feedback: str = "") -> dict:
        """Incorporate feedback and regenerate a draft."""
        if not draft_id:
            return {"error": "draft_id required"}

        # Get existing draft
        conn = self.repo._conn()
        row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        conn.close()
        if not row:
            return {"error": f"Draft {draft_id} not found"}

        draft = dict(row)
        prompt = (
            f"Rewrite the following newsletter section incorporating this feedback:\n\n"
            f"Feedback: {feedback}\n\n"
            f"Original content:\n{draft['content']}"
        )

        content, model = generate_draft(prompt, self.config)
        self.repo.update_draft_content(draft_id, content)
        self.log_output(task_id, "rewrite", content)

        return {"draft_id": draft_id, "rewritten": True}

    def adapt_tone(self, task_id: int, draft_id: Optional[int] = None, tone_direction: str = "") -> dict:
        """Adjust tone without full rewrite."""
        if not draft_id:
            return {"error": "draft_id required"}

        conn = self.repo._conn()
        row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        conn.close()
        if not row:
            return {"error": f"Draft {draft_id} not found"}

        draft = dict(row)
        prompt = (
            f"Adjust the tone of this newsletter section. Direction: {tone_direction}\n"
            f"Keep the core content the same but shift the voice/tone as directed.\n\n"
            f"Content:\n{draft['content']}"
        )

        content, model = generate_draft(prompt, self.config, max_tokens_override=1500)
        self.repo.update_draft_content(draft_id, content)
        self.log_output(task_id, "tone_adapt", content)

        return {"draft_id": draft_id, "tone_adapted": True}
