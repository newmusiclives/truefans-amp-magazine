"""Draft routes — generate, view, edit."""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from weeklyamp.content.generator import generate_draft
from weeklyamp.content.prompts import build_prompt
from weeklyamp.content.sections import get_section_slugs
from weeklyamp.core.models import WORD_COUNT_MAX_TOKENS
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def drafts_page():
    cfg = get_config()
    repo = get_repo()
    issue = repo.get_current_issue()
    sections = repo.get_active_sections()
    drafts = repo.get_drafts_for_issue(issue["id"]) if issue else []
    draft_map = {d["section_slug"]: d for d in drafts}

    return render("drafts.html",
        issue=issue,
        sections=sections,
        draft_map=draft_map,
        config=cfg,
    )


@router.post("/generate", response_class=HTMLResponse)
async def generate(section_slug: str = Form("")):
    cfg = get_config()
    repo = get_repo()

    issue = repo.get_current_issue()
    if not issue:
        num = repo.get_next_issue_number()
        issue_id = repo.create_issue(num, title=f"Issue #{num}")
        issue = repo.get_issue(issue_id)
    else:
        issue_id = issue["id"]

    repo.update_issue_status(issue_id, "drafting")

    if section_slug:
        slugs = [section_slug]
    elif issue.get("issue_template"):
        slugs = [s.strip() for s in issue["issue_template"].split(",") if s.strip()]
    else:
        slugs = get_section_slugs(repo)
    # Always include ps_from_ps
    if "ps_from_ps" not in slugs:
        slugs.append("ps_from_ps")
    # Ensure ps_from_ps is always generated last so it can reference the edition
    if len(slugs) > 1 and "ps_from_ps" in slugs:
        slugs.remove("ps_from_ps")
        slugs.append("ps_from_ps")
    results = []

    for slug in slugs:
        inputs = repo.get_editorial_inputs(issue_id, slug)
        topic = inputs[0].get("topic", "") if inputs else ""
        notes = inputs[0].get("notes", "") if inputs else ""

        # For ps_from_ps, use this edition's drafts as reference instead of raw content
        if slug == "ps_from_ps":
            edition_drafts = repo.get_drafts_for_issue(issue_id)
            reference = "\n\n".join(
                f"**{d['section_slug'].replace('_', ' ').upper()}**: {d['content'][:200]}..."
                for d in edition_drafts if d["section_slug"] != "ps_from_ps"
            )
        else:
            raw_items = repo.get_unused_content(section_slug=slug, limit=3)
            reference = "\n\n".join(f"- {i['title']}: {i['summary']}" for i in raw_items[:3]) if raw_items else ""

        # Look up word count settings for this section
        section = repo.get_section(slug)
        target_wc = section.get("target_word_count", 300) if section else 300
        wc_label = section.get("word_count_label", "medium") if section else "medium"
        max_tokens = WORD_COUNT_MAX_TOKENS.get(wc_label, 1500)

        prompt = build_prompt(
            slug, topic, notes, reference, cfg.newsletter.name,
            target_word_count=target_wc, word_count_label=wc_label,
        )
        try:
            content, model = generate_draft(prompt, cfg, max_tokens_override=max_tokens)
            repo.create_draft(issue_id, slug, content, model, prompt[:2000])
            results.append({"slug": slug, "ok": True, "length": len(content)})
        except Exception as exc:
            results.append({"slug": slug, "ok": False, "error": str(exc)})

    # Re-fetch for display
    sections = repo.get_active_sections()
    drafts = repo.get_drafts_for_issue(issue_id)
    draft_map = {d["section_slug"]: d for d in drafts}

    return render("partials/draft_cards.html",
        sections=sections, draft_map=draft_map, results=results, issue=issue)


@router.get("/{section_slug}", response_class=HTMLResponse)
async def view_draft(section_slug: str):
    repo = get_repo()
    issue = repo.get_current_issue()
    if not issue:
        return render("partials/alert.html", message="No current issue.", level="error")
    draft = repo.get_latest_draft(issue["id"], section_slug)
    section = repo.get_section(section_slug)
    return render("draft_detail.html", draft=draft, section=section, issue=issue)


@router.post("/{section_slug}/save", response_class=HTMLResponse)
async def save_draft(section_slug: str, content: str = Form(...)):
    repo = get_repo()
    issue = repo.get_current_issue()
    if not issue:
        return render("partials/alert.html", message="No current issue.", level="error")
    draft = repo.get_latest_draft(issue["id"], section_slug)
    if draft:
        repo.update_draft_content(draft["id"], content)
    return render("partials/alert.html", message="Draft saved!", level="success")
