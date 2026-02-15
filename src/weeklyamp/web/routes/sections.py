"""Section management routes."""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from weeklyamp.core.models import WORD_COUNT_RANGES
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


def _get_all_sections(repo):
    """Fetch all sections for table display."""
    conn = repo._conn()
    all_sections = conn.execute("SELECT * FROM section_definitions ORDER BY sort_order").fetchall()
    conn.close()
    return [dict(r) for r in all_sections]


@router.get("/", response_class=HTMLResponse)
async def sections_page():
    repo = get_repo()
    all_sections = _get_all_sections(repo)
    suggestions = repo.get_suggested_sections()
    return render("sections.html", sections=all_sections, suggestions=suggestions)


@router.post("/add", response_class=HTMLResponse)
async def add_section(
    slug: str = Form(...),
    display_name: str = Form(...),
    sort_order: int = Form(...),
):
    repo = get_repo()
    try:
        repo.add_section(slug, display_name, sort_order)
        message = f"Added section: {display_name}"
        level = "success"
    except Exception as exc:
        message = f"Failed: {exc}"
        level = "error"

    all_sections = _get_all_sections(repo)
    return render("partials/sections_table.html",
        sections=all_sections, message=message, level=level)


@router.post("/toggle/{slug}", response_class=HTMLResponse)
async def toggle_section(slug: str):
    repo = get_repo()
    section = repo.get_section(slug)
    if section:
        new_state = 0 if section["is_active"] else 1
        repo.update_section(slug, is_active=new_state)

    all_sections = _get_all_sections(repo)
    return render("partials/sections_table.html", sections=all_sections)


@router.post("/update-word-count/{slug}", response_class=HTMLResponse)
async def update_word_count(slug: str, word_count_label: str = Form(...)):
    repo = get_repo()
    wc_range = WORD_COUNT_RANGES.get(word_count_label, (300, 500))
    target = (wc_range[0] + wc_range[1]) // 2
    repo.update_section_word_count(slug, word_count_label, target)

    all_sections = _get_all_sections(repo)
    return render("partials/sections_table.html", sections=all_sections)


@router.post("/update-type/{slug}", response_class=HTMLResponse)
async def update_type(slug: str, section_type: str = Form(...)):
    repo = get_repo()
    if section_type in ("core", "rotating"):
        repo.update_section(slug, section_type=section_type)

    all_sections = _get_all_sections(repo)
    return render("partials/sections_table.html", sections=all_sections)


@router.post("/suggest", response_class=HTMLResponse)
async def suggest():
    repo = get_repo()
    cfg = get_config()
    try:
        from weeklyamp.content.discovery import save_suggestions, suggest_sections
        suggestions_data = suggest_sections(repo, cfg, count=3)
        saved = save_suggestions(repo, suggestions_data)
        message = f"Generated {saved} new section suggestions"
        level = "success"
    except Exception as exc:
        message = f"Suggestion failed: {exc}"
        level = "error"

    suggestions = repo.get_suggested_sections()
    return render("partials/suggestions_list.html",
        suggestions=suggestions, message=message, level=level)


@router.post("/accept/{slug}", response_class=HTMLResponse)
async def accept_suggestion(slug: str, as_type: str = Form("rotating")):
    repo = get_repo()
    repo.accept_suggested_section(slug, as_type)

    suggestions = repo.get_suggested_sections()
    return render("partials/suggestions_list.html", suggestions=suggestions)


@router.post("/dismiss/{slug}", response_class=HTMLResponse)
async def dismiss_suggestion(slug: str):
    repo = get_repo()
    repo.dismiss_suggested_section(slug)

    suggestions = repo.get_suggested_sections()
    return render("partials/suggestions_list.html", suggestions=suggestions)
