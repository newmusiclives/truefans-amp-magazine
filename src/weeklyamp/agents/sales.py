"""Sales agent — per-edition specialist that identifies sponsor prospects,
drafts personalized outreach, and manages the sponsorship pipeline.

Multiple SalesAgent rows live in the database — one Sales lead per
edition (Kyle/Fan, Dana/Artist, Talia/Industry) plus a cross-newsletter
VP of Sales (Grant). Each row's `config_json` carries an `edition` (or
`editions` for the VP) that scopes the prompts and any rows written
back to the database.

The agent reads its own edition off the agent row at construction
time, so the orchestrator's fan-out pattern (one agent per row, like
Writers) works without extra plumbing — see
`MarketingAgent.identify_prospects` for the coordinator side.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from weeklyamp.agents.base import AgentBase
from weeklyamp.content.generator import generate_draft

logger = logging.getLogger(__name__)


class SalesAgent(AgentBase):
    agent_type = "sales"
    default_name = "Sales Director"
    default_persona = "Strategic sales professional with deep understanding of the music industry advertising landscape."
    default_system_prompt = (
        "You are a Sales lead for TrueFans SIGNAL. "
        "You identify potential sponsors, draft outreach emails, "
        "and manage the sponsorship pipeline."
    )

    # ---- Edition awareness ----

    def _edition_scope(self) -> tuple[str, list[str]]:
        """Return (primary_edition, all_editions) for the loaded agent row.

        - Single-edition specialists (Kyle/Dana/Talia) return ("fan", ["fan"])
          with the primary edition mirrored in the list.
        - The cross-newsletter VP (Grant) returns ("", ["fan","artist","industry"])
          and uses the empty primary as the signal that this instance acts
          across all editions.
        """
        agent = self._ensure_agent()
        try:
            cfg = json.loads(agent.get("config_json") or "{}")
        except (ValueError, TypeError):
            cfg = {}
        edition = cfg.get("edition", "") or ""
        editions = cfg.get("editions", []) or ([edition] if edition else [])
        return edition, list(editions)

    # ---- Task dispatch ----

    def _run(self, task_id: int) -> Optional[dict]:
        task = self.repo.get_task(task_id)
        if not task:
            return {"error": "Task not found"}

        task_type = task["task_type"]
        input_data = json.loads(task.get("input_json", "{}"))

        if task_type == "identify_prospects":
            return self.identify_prospects(task_id, count=input_data.get("count", 5))
        if task_type == "draft_outreach":
            return self.draft_outreach(task_id, prospect_id=input_data.get("prospect_id"))
        if task_type == "draft_outreach_batch":
            return self.draft_outreach_batch(task_id, batch_size=input_data.get("batch_size", 5))
        if task_type == "update_pipeline":
            return self.update_pipeline(task_id)
        return {"error": f"Unknown task type: {task_type}"}

    # ---- Tasks ----

    def identify_prospects(self, task_id: int, count: int = 5) -> dict:
        """AI-generate sponsor prospects scoped to this agent's edition,
        parse the LLM response as JSON, and persist each prospect into
        sponsor_prospects.

        Returns {"created": [ids], "raw": str} so the caller can both
        act on the new rows and audit the LLM output.
        """
        primary, editions = self._edition_scope()
        subscriber_count = self.repo.get_subscriber_count()
        edition_label = primary or "all editions"
        target_editions_csv = ",".join(editions) if editions else ""

        prompt = (
            f"Identify {count} companies that would be ideal sponsors for "
            f"the {edition_label} edition of TrueFans SIGNAL "
            f"({subscriber_count} subscribers across Fan/Artist/Industry).\n\n"
            f"Respond with ONLY a JSON array. No prose, no markdown fences. "
            f"Each element must be an object with these exact keys:\n"
            f'  "company_name" (string)\n'
            f'  "category" (string — e.g. "music_gear", "streaming", "fintech")\n'
            f'  "estimated_budget" (string — e.g. "$5k-$15k/mo")\n'
            f'  "pitch_angle" (string — one sentence)\n'
            f'  "website" (string, may be empty)\n\n'
            f"Focus on companies that actively advertise to music audiences."
        )

        raw, _model = generate_draft(prompt, self.config, max_tokens_override=900)
        self.log_output(task_id, "prospect_list_raw", raw)

        prospects = _parse_json_array(raw)
        created_ids: list[int] = []
        for p in prospects:
            if not isinstance(p, dict):
                continue
            company = (p.get("company_name") or "").strip()
            if not company:
                continue
            try:
                pid = self.repo.create_sponsor_prospect(
                    company_name=company,
                    website=(p.get("website") or "").strip(),
                    category=(p.get("category") or "general").strip(),
                    target_editions=target_editions_csv,
                    estimated_budget=(p.get("estimated_budget") or "").strip(),
                    source=f"agent:sales:{primary or 'cross'}",
                    notes=(p.get("pitch_angle") or "").strip(),
                )
                created_ids.append(pid)
            except Exception:
                # One bad row should not poison the batch — log and continue.
                logger.exception("create_sponsor_prospect failed for %s", company)

        return {"created": created_ids, "edition": primary, "raw": raw}

    def draft_outreach(self, task_id: int, prospect_id: Optional[int] = None) -> dict:
        """Draft a single personalized outreach email for one prospect."""
        if not prospect_id:
            return {"error": "prospect_id required"}

        prospects = self.repo.get_sponsor_prospects(limit=1000)
        prospect = next((p for p in prospects if p["id"] == prospect_id), None)
        if not prospect:
            return {"error": f"Prospect {prospect_id} not found"}

        primary, _editions = self._edition_scope()
        subscriber_count = self.repo.get_subscriber_count()
        edition_label = primary or "all editions"

        prompt = (
            f"Write a personalized sponsorship outreach email for TrueFans SIGNAL "
            f"({edition_label} edition).\n\n"
            f"Prospect: {prospect['company_name']}\n"
            f"Category: {prospect.get('category', 'general')}\n"
            f"Notes: {prospect.get('notes', '')}\n\n"
            f"Audience: {subscriber_count} engaged music subscribers, 3x weekly.\n"
            f"Write a warm, professional ~150-word email. End with a soft "
            f"call-to-action to schedule a 15-minute intro call."
        )

        email, _model = generate_draft(prompt, self.config, max_tokens_override=600)
        self.log_output(task_id, "outreach_email", email)
        if email:
            self.repo.update_prospect_status(prospect_id, "contacted")
            self.repo.log_outreach(
                channel="email",
                recipient_email=prospect.get("contact_email", ""),
                recipient_name=prospect.get("contact_name", ""),
                recipient_type="sponsor_prospect",
                status="queued",
            )
        return {"prospect_id": prospect_id, "email": email}

    def draft_outreach_batch(self, task_id: int, batch_size: int = 5) -> dict:
        """Draft outreach for the next N prospects this agent's edition
        owns that are still in 'identified' state.

        Cross-newsletter agents (no primary edition) draft for any
        prospect that hasn't been claimed by an edition.
        """
        primary, editions = self._edition_scope()
        all_prospects = self.repo.get_sponsor_prospects(status="identified", limit=200)

        def _belongs(p: dict) -> bool:
            tags = (p.get("target_editions") or "")
            if not primary:
                # Cross-newsletter VP picks up anything
                return True
            return primary in tags.split(",")

        scoped = [p for p in all_prospects if _belongs(p)][:batch_size]
        drafted = 0
        for prospect in scoped:
            result = self.draft_outreach(task_id, prospect_id=prospect["id"])
            if not result.get("error"):
                drafted += 1
        return {"drafted": drafted, "edition": primary}

    def update_pipeline(self, task_id: int) -> dict:
        """Snapshot prospect statuses for this edition. Lightweight — the
        actual pipeline UI reads sponsor_prospects directly; this task
        just produces an auditable summary blob in agent_outputs."""
        primary, _editions = self._edition_scope()
        prospects = self.repo.get_sponsor_prospects(limit=500)

        if primary:
            prospects = [
                p for p in prospects
                if primary in (p.get("target_editions") or "").split(",")
            ]

        by_status: dict[str, int] = {}
        for p in prospects:
            s = p.get("status", "unknown") or "unknown"
            by_status[s] = by_status.get(s, 0) + 1

        summary = {"edition": primary, "total": len(prospects), "by_status": by_status}
        self.log_output(task_id, "pipeline_snapshot", json.dumps(summary))
        return summary


# ---- Helpers ----


_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def _parse_json_array(raw: str) -> list:
    """Parse a JSON array from an LLM response, tolerating markdown
    fences and trailing prose.

    Returns [] on failure rather than raising — the caller logs the raw
    text via log_output so failures are debuggable from the audit trail.
    """
    if not raw:
        return []
    text = raw.strip()
    # Strip ``` fences if the model added them.
    if text.startswith("```"):
        text = text.strip("`")
        # After stripping ticks the first line may be a language tag.
        lines = text.splitlines()
        if lines and lines[0].lower() in ("json", "javascript"):
            text = "\n".join(lines[1:])
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    # Last-ditch: extract the first [...] block.
    m = _JSON_ARRAY_RE.search(raw)
    if not m:
        return []
    try:
        return json.loads(m.group(0))
    except (ValueError, TypeError):
        return []
