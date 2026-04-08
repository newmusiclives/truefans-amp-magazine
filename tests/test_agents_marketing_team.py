"""Tests for the Sales / Promotion / Marketing agent trio.

Covers the reframed architecture from the AI staff overhaul:

  - SalesAgent and PromotionAgent are per-edition specialists. Their
    `identify_*` tasks parse LLM JSON output and persist rows into
    sponsor_prospects / cross_promo_partners.
  - MarketingAgent acts as a coordinator: its `identify_prospects`,
    `draft_outreach_batch`, and `identify_partners` tasks fan out to
    every Sales / Promotion agent on the roster.

The LLM is always mocked. We assert (a) DB persistence, (b) edition
scoping, (c) state-machine transitions on the parent task row, and
(d) that one specialist failure does not abort the whole fan-out.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from weeklyamp.agents.marketing import MarketingAgent
from weeklyamp.agents.promotion import PromotionAgent
from weeklyamp.agents.sales import SalesAgent, _parse_json_array


# ---- _parse_json_array — defensive parsing helper ----


def test_parse_json_array_plain():
    assert _parse_json_array('[{"company_name": "Acme"}]') == [{"company_name": "Acme"}]


def test_parse_json_array_with_markdown_fence():
    raw = "```json\n[{\"partner_name\": \"Foo\"}]\n```"
    assert _parse_json_array(raw) == [{"partner_name": "Foo"}]


def test_parse_json_array_extracts_block_from_prose():
    raw = "Sure! Here are the prospects:\n[{\"company_name\": \"Bar\"}]\nLet me know!"
    assert _parse_json_array(raw) == [{"company_name": "Bar"}]


def test_parse_json_array_returns_empty_on_garbage():
    assert _parse_json_array("not json at all") == []
    assert _parse_json_array("") == []


# ---- Fixtures ----


@pytest.fixture()
def fan_sales_agent_id(repo):
    """Create a Fan-edition Sales lead and return the agent row id."""
    return repo.create_agent(
        agent_type="sales",
        name="Test Fan Sales",
        persona="test persona",
        system_prompt="test prompt",
        autonomy_level="manual",
        config_json='{"edition": "fan"}',
    )


@pytest.fixture()
def artist_sales_agent_id(repo):
    return repo.create_agent(
        agent_type="sales",
        name="Test Artist Sales",
        persona="test persona",
        system_prompt="test prompt",
        autonomy_level="manual",
        config_json='{"edition": "artist"}',
    )


@pytest.fixture()
def fan_promo_agent_id(repo):
    return repo.create_agent(
        agent_type="promotion",
        name="Test Fan Promo",
        persona="test persona",
        system_prompt="test prompt",
        autonomy_level="manual",
        config_json='{"edition": "fan"}',
    )


# ---- SalesAgent.identify_prospects ----


def test_sales_identify_prospects_persists_rows(repo, fan_sales_agent_id):
    """LLM returns a JSON array → rows get written to sponsor_prospects
    with the correct edition tag and source."""
    fake_llm_output = json.dumps([
        {
            "company_name": "Acme Music Gear",
            "category": "music_gear",
            "estimated_budget": "$5k-$15k/mo",
            "pitch_angle": "Reach indie producers buying their first interface",
            "website": "acme.example",
        },
        {
            "company_name": "StreamCo",
            "category": "streaming",
            "estimated_budget": "$10k/mo",
            "pitch_angle": "Promote artist tools",
            "website": "",
        },
    ])

    agent = SalesAgent(repo, agent_id=fan_sales_agent_id)
    task_id = agent.assign_task("identify_prospects", input_data={"count": 2})

    with patch(
        "weeklyamp.agents.sales.generate_draft",
        return_value=(fake_llm_output, "test-model"),
    ):
        result = agent.execute(task_id)

    assert len(result["created"]) == 2
    assert result["edition"] == "fan"

    rows = repo.get_sponsor_prospects()
    by_name = {r["company_name"]: r for r in rows}
    assert "Acme Music Gear" in by_name
    assert by_name["Acme Music Gear"]["target_editions"] == "fan"
    assert by_name["Acme Music Gear"]["category"] == "music_gear"
    assert by_name["Acme Music Gear"]["source"] == "agent:sales:fan"
    # Pitch angle is stored in notes for downstream outreach prompts
    assert "indie producers" in by_name["Acme Music Gear"]["notes"]


def test_sales_identify_prospects_handles_garbage_llm_output(repo, fan_sales_agent_id):
    """A non-JSON LLM response should not raise — the task should
    complete with zero created rows and the raw output captured for
    debugging via log_output."""
    agent = SalesAgent(repo, agent_id=fan_sales_agent_id)
    task_id = agent.assign_task("identify_prospects")

    with patch(
        "weeklyamp.agents.sales.generate_draft",
        return_value=("I cannot help with that request.", "test-model"),
    ):
        result = agent.execute(task_id)

    assert result["created"] == []
    assert repo.get_sponsor_prospects() == []


def test_sales_draft_outreach_marks_prospect_contacted(repo, fan_sales_agent_id):
    prospect_id = repo.create_sponsor_prospect(
        company_name="Test Co",
        contact_email="contact@test.example",
        category="music_gear",
        target_editions="fan",
    )

    agent = SalesAgent(repo, agent_id=fan_sales_agent_id)
    task_id = agent.assign_task("draft_outreach", input_data={"prospect_id": prospect_id})

    with patch(
        "weeklyamp.agents.sales.generate_draft",
        return_value=("Hi Test Co, here's why we'd love to partner...", "test-model"),
    ):
        agent.execute(task_id)

    refreshed = repo.get_sponsor_prospects(limit=10)
    target = next(p for p in refreshed if p["id"] == prospect_id)
    assert target["status"] == "contacted"


def test_sales_draft_outreach_batch_only_picks_up_own_edition(
    repo, fan_sales_agent_id, artist_sales_agent_id
):
    """A Fan Sales agent's batch should only draft outreach for prospects
    tagged with the Fan edition, not Artist prospects."""
    fan_id = repo.create_sponsor_prospect(company_name="FanCorp", target_editions="fan")
    artist_id = repo.create_sponsor_prospect(company_name="ArtistCorp", target_editions="artist")

    agent = SalesAgent(repo, agent_id=fan_sales_agent_id)
    task_id = agent.assign_task("draft_outreach_batch")

    with patch(
        "weeklyamp.agents.sales.generate_draft",
        return_value=("Draft email body", "test-model"),
    ):
        result = agent.execute(task_id)

    assert result["drafted"] == 1
    assert result["edition"] == "fan"

    statuses = {p["company_name"]: p["status"] for p in repo.get_sponsor_prospects()}
    assert statuses["FanCorp"] == "contacted"
    assert statuses["ArtistCorp"] == "identified"  # untouched


def test_sales_update_pipeline_summarises_by_status(repo, fan_sales_agent_id):
    repo.create_sponsor_prospect(company_name="A", target_editions="fan")
    pid_b = repo.create_sponsor_prospect(company_name="B", target_editions="fan")
    repo.update_prospect_status(pid_b, "contacted")
    repo.create_sponsor_prospect(company_name="C", target_editions="artist")  # not in scope

    agent = SalesAgent(repo, agent_id=fan_sales_agent_id)
    task_id = agent.assign_task("update_pipeline")

    result = agent.execute(task_id)
    assert result["edition"] == "fan"
    assert result["total"] == 2  # Artist row excluded
    assert result["by_status"]["identified"] == 1
    assert result["by_status"]["contacted"] == 1


# ---- PromotionAgent.identify_partners ----


def test_promotion_identify_partners_persists_rows(repo, fan_promo_agent_id):
    fake_llm_output = json.dumps([
        {
            "partner_name": "Indie Audio Weekly",
            "partner_type": "newsletter",
            "audience_size": "12k subscribers",
            "audience_overlap": "Both serve home producers and bedroom artists",
            "pitch_idea": "Swap a featured-artist slot in the same week",
            "contact_url": "https://iaw.example/contact",
        },
        {
            "partner_name": "Mix Bus Podcast",
            "partner_type": "podcast",
            "audience_size": "8k weekly downloads",
            "audience_overlap": "Mix engineers cross over with artist edition",
            "pitch_idea": "Guest on each other's promo segment",
            "contact_url": "",
        },
    ])

    agent = PromotionAgent(repo, agent_id=fan_promo_agent_id)
    task_id = agent.assign_task("identify_partners", input_data={"count": 2})

    with patch(
        "weeklyamp.agents.promotion.generate_draft",
        return_value=(fake_llm_output, "test-model"),
    ):
        result = agent.execute(task_id)

    assert len(result["created"]) == 2
    rows = repo.get_cross_promo_partners(edition_slug="fan")
    names = {r["partner_name"] for r in rows}
    assert names == {"Indie Audio Weekly", "Mix Bus Podcast"}
    iaw = next(r for r in rows if r["partner_name"] == "Indie Audio Weekly")
    assert iaw["partner_type"] == "newsletter"
    assert iaw["edition_slug"] == "fan"
    assert "home producers" in iaw["audience_overlap"]


def test_promotion_identify_partners_normalises_invalid_type(repo, fan_promo_agent_id):
    """Unknown partner_type values should be coerced to 'other' rather
    than violating the CHECK constraint."""
    fake_llm_output = json.dumps([
        {"partner_name": "Weird One", "partner_type": "carrier_pigeon"},
    ])
    agent = PromotionAgent(repo, agent_id=fan_promo_agent_id)
    task_id = agent.assign_task("identify_partners")

    with patch(
        "weeklyamp.agents.promotion.generate_draft",
        return_value=(fake_llm_output, "test-model"),
    ):
        agent.execute(task_id)

    rows = repo.get_cross_promo_partners(edition_slug="fan")
    assert rows[0]["partner_type"] == "other"


def test_promotion_draft_cross_promo_marks_partner_contacted(repo, fan_promo_agent_id):
    pid = repo.create_cross_promo_partner(
        partner_name="Indie Audio Weekly",
        partner_type="newsletter",
        audience_overlap="Producers overlap",
        pitch_idea="Featured-artist swap",
        edition_slug="fan",
    )

    agent = PromotionAgent(repo, agent_id=fan_promo_agent_id)
    task_id = agent.assign_task("draft_cross_promo", input_data={"partner_id": pid})

    with patch(
        "weeklyamp.agents.promotion.generate_draft",
        return_value=("Hey IAW, want to swap features?", "test-model"),
    ):
        agent.execute(task_id)

    refreshed = repo.get_cross_promo_partners(edition_slug="fan")
    assert refreshed[0]["status"] == "contacted"


# ---- MarketingAgent fan-out coordinator ----


def test_marketing_identify_prospects_fans_out_to_every_sales_agent(
    repo, fan_sales_agent_id, artist_sales_agent_id
):
    """A single trigger on Marketing should produce prospects for both
    edition Sales leads, each tagged with their own edition."""
    by_edition = {
        "fan": json.dumps([{"company_name": "FanGear Co", "category": "music_gear"}]),
        "artist": json.dumps([{"company_name": "ArtistTools Co", "category": "music_gear"}]),
    }

    def _fake_generate(prompt, *args, **kwargs):
        # Look at the prompt to decide which canned response to return.
        if "fan edition" in prompt.lower():
            return by_edition["fan"], "test"
        if "artist edition" in prompt.lower():
            return by_edition["artist"], "test"
        return "[]", "test"

    marketing = MarketingAgent(repo)
    task_id = marketing.assign_task("identify_prospects")

    with patch("weeklyamp.agents.sales.generate_draft", side_effect=_fake_generate):
        result = marketing.execute(task_id)

    assert result["fanned_out_to"] == 2
    names = {r["company_name"] for r in repo.get_sponsor_prospects()}
    assert names == {"FanGear Co", "ArtistTools Co"}

    by_company = {r["company_name"]: r for r in repo.get_sponsor_prospects()}
    assert by_company["FanGear Co"]["target_editions"] == "fan"
    assert by_company["ArtistTools Co"]["target_editions"] == "artist"


def test_marketing_fanout_continues_after_specialist_failure(
    repo, fan_sales_agent_id, artist_sales_agent_id
):
    """If one Sales lead's task raises, the others must still run.
    Coordinator must not abort the entire fan-out on a single failure."""
    call_count = {"n": 0}

    def _flaky_generate(prompt, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("LLM blew up")
        return json.dumps([{"company_name": "Survivor Co"}]), "test"

    marketing = MarketingAgent(repo)
    task_id = marketing.assign_task("identify_prospects")

    with patch("weeklyamp.agents.sales.generate_draft", side_effect=_flaky_generate):
        result = marketing.execute(task_id)

    assert result["fanned_out_to"] == 2
    # One specialist errored, the other persisted its row
    errors = [r for r in result["results"] if isinstance(r["result"], dict) and r["result"].get("error")]
    survivors = [r for r in result["results"] if isinstance(r["result"], dict) and not r["result"].get("error")]
    assert len(errors) == 1
    assert len(survivors) == 1
    assert any(p["company_name"] == "Survivor Co" for p in repo.get_sponsor_prospects())


def test_marketing_identify_partners_fans_out_to_promotion_agents(repo, fan_promo_agent_id):
    fake = json.dumps([
        {"partner_name": "Cool Newsletter", "partner_type": "newsletter"},
    ])

    marketing = MarketingAgent(repo)
    task_id = marketing.assign_task("identify_partners")

    with patch(
        "weeklyamp.agents.promotion.generate_draft",
        return_value=(fake, "test"),
    ):
        result = marketing.execute(task_id)

    assert result["fanned_out_to"] == 1
    rows = repo.get_cross_promo_partners()
    assert any(r["partner_name"] == "Cool Newsletter" for r in rows)
