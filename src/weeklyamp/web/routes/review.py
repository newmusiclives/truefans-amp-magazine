"""Review routes — approve, reject, edit drafts."""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def review_page():
    repo = get_repo()
    issue = repo.get_current_issue()
    sections = repo.get_active_sections()
    drafts = repo.get_drafts_for_issue(issue["id"]) if issue else []
    draft_map = {d["section_slug"]: d for d in drafts}

    return render("review.html",
        issue=issue,
        sections=sections,
        draft_map=draft_map,
    )


@router.post("/approve/{section_slug}", response_class=HTMLResponse)
async def approve(section_slug: str):
    repo = get_repo()
    issue = repo.get_current_issue()
    draft = repo.get_latest_draft(issue["id"], section_slug)
    if draft:
        repo.update_draft_status(draft["id"], "approved")

    # Return updated card
    draft = repo.get_latest_draft(issue["id"], section_slug)
    section = repo.get_section(section_slug)
    return render("partials/review_card.html", draft=draft, section=section)


@router.post("/reject/{section_slug}", response_class=HTMLResponse)
async def reject(section_slug: str, notes: str = Form("")):
    repo = get_repo()
    issue = repo.get_current_issue()
    draft = repo.get_latest_draft(issue["id"], section_slug)
    if draft:
        repo.update_draft_status(draft["id"], "rejected", notes)

    draft = repo.get_latest_draft(issue["id"], section_slug)
    section = repo.get_section(section_slug)
    return render("partials/review_card.html", draft=draft, section=section)


@router.post("/save/{section_slug}", response_class=HTMLResponse)
async def save_edit(section_slug: str, content: str = Form(...)):
    repo = get_repo()
    issue = repo.get_current_issue()
    draft = repo.get_latest_draft(issue["id"], section_slug)
    if draft:
        repo.update_draft_content(draft["id"], content)

    draft = repo.get_latest_draft(issue["id"], section_slug)
    section = repo.get_section(section_slug)
    return render("partials/review_card.html", draft=draft, section=section)
