"""Research routes — sources, content, topics."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from weeklyamp.research.discovery import score_and_tag_content
from weeklyamp.research.sources import fetch_all_sources, sync_sources_from_config
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def research_page():
    repo = get_repo()
    sources = repo.get_active_sources()
    content = repo.get_unused_content(limit=50)
    issue = repo.get_current_issue()
    editorial = repo.get_editorial_inputs(issue["id"]) if issue else []
    sections = repo.get_active_sections()

    return render("research.html",
        sources=sources,
        content=content,
        editorial=editorial,
        sections=sections,
        issue=issue,
    )


@router.post("/scrape", response_class=HTMLResponse)
async def scrape():
    cfg = get_config()
    repo = get_repo()
    sync_sources_from_config(repo)
    results = fetch_all_sources(repo)

    # Score content
    items = repo.get_unused_content(limit=200)
    for item in items:
        if not item["matched_sections"] or item["relevance_score"] == 0:
            score_and_tag_content(repo, item["id"], item["title"], item["summary"])

    total = sum(results.values())
    return render("partials/scrape_result.html", results=results, total=total)


@router.post("/add-topic", response_class=HTMLResponse)
async def add_topic(
    section_slug: str = Form(...),
    topic: str = Form(...),
    notes: str = Form(""),
):
    repo = get_repo()
    issue = repo.get_current_issue()
    if not issue:
        num = repo.get_next_issue_number()
        issue_id = repo.create_issue(num)
    else:
        issue_id = issue["id"]

    repo.add_editorial_input(issue_id, section_slug, topic, notes)
    # Return updated editorial list
    editorial = repo.get_editorial_inputs(issue_id)
    sections = repo.get_active_sections()
    return render("partials/editorial_list.html", editorial=editorial, sections=sections)
