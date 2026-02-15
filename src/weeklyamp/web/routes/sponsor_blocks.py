"""Sponsor block management routes."""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def sponsor_blocks_page():
    repo = get_repo()
    cfg = get_config()
    issue = repo.get_current_issue()
    blocks = repo.get_sponsor_blocks_for_issue(issue["id"]) if issue else []

    return render("sponsor_blocks.html",
        issue=issue,
        blocks=blocks,
        positions=cfg.sponsor_slots.available_positions,
        max_per_issue=cfg.sponsor_slots.max_per_issue,
    )


@router.post("/add", response_class=HTMLResponse)
async def add_block(
    position: str = Form("mid"),
    sponsor_name: str = Form(""),
    headline: str = Form(""),
    body_html: str = Form(""),
    cta_url: str = Form(""),
    cta_text: str = Form("Learn More"),
    image_url: str = Form(""),
):
    repo = get_repo()
    cfg = get_config()
    issue = repo.get_current_issue()
    if not issue:
        return render("partials/alert.html", message="No current issue.", level="error")

    repo.create_sponsor_block(
        issue_id=issue["id"],
        position=position,
        sponsor_name=sponsor_name,
        headline=headline,
        body_html=body_html,
        cta_url=cta_url,
        cta_text=cta_text,
        image_url=image_url,
    )

    blocks = repo.get_sponsor_blocks_for_issue(issue["id"])
    return render("partials/sponsor_blocks_list.html",
        blocks=blocks, issue=issue,
        positions=cfg.sponsor_slots.available_positions)


@router.post("/delete/{block_id}", response_class=HTMLResponse)
async def delete_block(block_id: int):
    repo = get_repo()
    cfg = get_config()
    repo.delete_sponsor_block(block_id)

    issue = repo.get_current_issue()
    blocks = repo.get_sponsor_blocks_for_issue(issue["id"]) if issue else []
    return render("partials/sponsor_blocks_list.html",
        blocks=blocks, issue=issue,
        positions=cfg.sponsor_slots.available_positions)
