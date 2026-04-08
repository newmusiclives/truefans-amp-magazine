"""Promotion agent — per-edition specialist that grows the subscriber base
through cross-promotions, partnerships, and referral campaigns.

Like SalesAgent, multiple PromotionAgent rows live in the database — one
Promotion lead per edition (Jess/Fan, Cody/Artist, Ryan/Industry). Each
row's `config_json` carries an `edition` that scopes prompts and the
cross-promo partner pipeline this agent owns.

Identified partners are persisted to the `cross_promo_partners` table
(see migration v43) so the rest of the platform — and a future UI —
can act on them.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from weeklyamp.agents.base import AgentBase
from weeklyamp.agents.sales import _parse_json_array
from weeklyamp.content.generator import generate_draft

logger = logging.getLogger(__name__)


class PromotionAgent(AgentBase):
    agent_type = "promotion"
    default_name = "Promotion Lead"
    default_persona = "Creative growth marketer specializing in newsletter subscriber acquisition and community building."
    default_system_prompt = (
        "You are a Promotion lead for TrueFans SIGNAL. "
        "You design subscriber growth campaigns, craft referral programs, "
        "run cross-promotions, and build partnerships that drive sign-ups."
    )

    # ---- Edition awareness ----

    def _edition(self) -> str:
        agent = self._ensure_agent()
        try:
            cfg = json.loads(agent.get("config_json") or "{}")
        except (ValueError, TypeError):
            cfg = {}
        return cfg.get("edition", "") or ""

    # ---- Task dispatch ----

    def _run(self, task_id: int) -> Optional[dict]:
        task = self.repo.get_task(task_id)
        if not task:
            return {"error": "Task not found"}

        task_type = task["task_type"]
        input_data = json.loads(task.get("input_json", "{}"))

        if task_type == "identify_partners":
            return self.identify_partners(task_id, count=input_data.get("count", 5))
        if task_type == "draft_campaign":
            return self.draft_campaign(task_id, campaign_type=input_data.get("campaign_type", "referral"))
        if task_type == "draft_cross_promo":
            return self.draft_cross_promo(task_id, partner_id=input_data.get("partner_id"))
        if task_type == "analyze_growth":
            return self.analyze_growth(task_id)
        return {"error": f"Unknown task type: {task_type}"}

    # ---- Tasks ----

    def identify_partners(self, task_id: int, count: int = 5) -> dict:
        """AI-generate cross-promo partner candidates for this edition,
        parse the response as JSON, and persist each into
        cross_promo_partners.
        """
        edition = self._edition()
        subscriber_count = self.repo.get_subscriber_count()
        edition_label = edition or "all editions"

        prompt = (
            f"Suggest {count} newsletters, podcasts, or communities that would "
            f"be ideal cross-promotion partners for the {edition_label} edition "
            f"of TrueFans SIGNAL ({subscriber_count} subscribers).\n\n"
            f"Respond with ONLY a JSON array. No prose, no markdown fences. "
            f"Each element must be an object with these exact keys:\n"
            f'  "partner_name" (string)\n'
            f'  "partner_type" (one of: "newsletter", "podcast", "community", "social", "other")\n'
            f'  "audience_size" (string — e.g. "10k subscribers")\n'
            f'  "audience_overlap" (string — one sentence on why audiences fit)\n'
            f'  "pitch_idea" (string — one specific cross-promo concept)\n'
            f'  "contact_url" (string, may be empty)\n'
        )

        raw, _model = generate_draft(prompt, self.config, max_tokens_override=900)
        self.log_output(task_id, "partner_list_raw", raw)

        partners = _parse_json_array(raw)
        created_ids: list[int] = []
        valid_types = {"newsletter", "podcast", "community", "social", "other"}
        for p in partners:
            if not isinstance(p, dict):
                continue
            name = (p.get("partner_name") or "").strip()
            if not name:
                continue
            ptype = (p.get("partner_type") or "newsletter").strip().lower()
            if ptype not in valid_types:
                ptype = "other"
            try:
                pid = self.repo.create_cross_promo_partner(
                    partner_name=name,
                    partner_type=ptype,
                    audience_size=(p.get("audience_size") or "").strip(),
                    audience_overlap=(p.get("audience_overlap") or "").strip(),
                    pitch_idea=(p.get("pitch_idea") or "").strip(),
                    contact_url=(p.get("contact_url") or "").strip(),
                    edition_slug=edition,
                    source=f"agent:promotion:{edition or 'cross'}",
                )
                created_ids.append(pid)
            except Exception:
                logger.exception("create_cross_promo_partner failed for %s", name)

        return {"created": created_ids, "edition": edition, "raw": raw}

    def draft_campaign(self, task_id: int, campaign_type: str = "referral") -> dict:
        """Generate a subscriber acquisition campaign plan. Free-text
        output — campaign plans live in `agent_outputs` for human
        editing rather than a structured campaigns table, since each
        plan is a one-off creative artifact rather than CRM data.
        """
        edition = self._edition()
        subscriber_count = self.repo.get_subscriber_count()
        edition_label = edition or "all editions"

        prompt = (
            f"Design a {campaign_type} campaign for the {edition_label} edition "
            f"of TrueFans SIGNAL ({subscriber_count} subscribers).\n\n"
            f"Include:\n"
            f"1. Campaign concept and hook\n"
            f"2. Target audience and channels\n"
            f"3. Incentive structure (if referral)\n"
            f"4. Timeline and milestones\n"
            f"5. Success metrics and goals\n"
            f"6. Sample copy for the main CTA"
        )

        campaign, _model = generate_draft(prompt, self.config, max_tokens_override=1000)
        self.log_output(task_id, "campaign_plan", campaign)
        return {"campaign_type": campaign_type, "edition": edition, "campaign": campaign}

    def draft_cross_promo(self, task_id: int, partner_id: Optional[int] = None) -> dict:
        """Draft a cross-promotion outreach email for one stored partner.

        Pulls the partner row by id, generates a tailored pitch using
        the partner's pitch_idea + audience_overlap as anchors, and
        flips the partner's status to 'contacted'.
        """
        if not partner_id:
            return {"error": "partner_id required"}

        partners = self.repo.get_cross_promo_partners(limit=1000)
        partner = next((p for p in partners if p["id"] == partner_id), None)
        if not partner:
            return {"error": f"Partner {partner_id} not found"}

        edition = self._edition()
        subscriber_count = self.repo.get_subscriber_count()
        edition_label = edition or "all editions"

        prompt = (
            f"Write a cross-promotion outreach email to {partner['partner_name']} "
            f"({partner.get('partner_type', 'newsletter')}) on behalf of "
            f"the {edition_label} edition of TrueFans SIGNAL "
            f"({subscriber_count} subscribers).\n\n"
            f"Audience overlap angle: {partner.get('audience_overlap', '')}\n"
            f"Specific cross-promo idea: {partner.get('pitch_idea', '')}\n\n"
            f"Propose a mutual swap. Be specific about what we offer and what "
            f"we ask. Casual, collaborative, not salesy. Under 150 words."
        )

        email, _model = generate_draft(prompt, self.config, max_tokens_override=600)
        self.log_output(task_id, "cross_promo_email", email)
        if email:
            self.repo.update_cross_promo_partner_status(partner_id, "contacted")
        return {"partner_id": partner_id, "edition": edition, "email": email}

    def analyze_growth(self, task_id: int) -> dict:
        """Analyze current growth and suggest 3 immediate actions."""
        edition = self._edition()
        subscriber_count = self.repo.get_subscriber_count()

        prompt = (
            f"Analyze the growth situation for the {edition or 'all'} edition "
            f"of TrueFans SIGNAL ({subscriber_count} subscribers) and suggest "
            f"3 immediate actions to accelerate subscriber acquisition this week. "
            f"Free or low-cost tactics that leverage existing content. "
            f"Be specific and actionable."
        )

        analysis, _model = generate_draft(prompt, self.config, max_tokens_override=700)
        self.log_output(task_id, "growth_analysis", analysis)
        return {"subscriber_count": subscriber_count, "edition": edition, "analysis": analysis}
