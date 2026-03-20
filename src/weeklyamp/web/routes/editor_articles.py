"""Editor articles routes — direct editor-written content."""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()

STATUSES = ["draft", "ready", "assigned", "published"]


@router.get("/", response_class=HTMLResponse)
async def editor_articles_page():
    repo = get_repo()
    articles = repo.get_editor_articles()
    editions = repo.get_editions()
    upcoming_issues = repo.get_upcoming_issues(limit=20)
    sections = repo.get_active_sections()
    return render("editor_articles.html",
        articles=articles,
        editions=editions,
        upcoming_issues=upcoming_issues,
        sections=sections,
        statuses=STATUSES,
    )


@router.post("/create", response_class=HTMLResponse)
async def create_article(
    title: str = Form(...),
    content: str = Form(""),
    author_name: str = Form("John"),
    edition_slug: str = Form(""),
    target_issue_id: int = Form(0),
    target_section_slug: str = Form(""),
    notes: str = Form(""),
):
    repo = get_repo()
    try:
        repo.create_editor_article(
            title=title, content=content, author_name=author_name,
            edition_slug=edition_slug, target_issue_id=target_issue_id,
            target_section_slug=target_section_slug, notes=notes,
        )
        message = f"Article created: {title}"
        level = "success"
    except Exception as e:
        message = f"Failed: {e}"
        level = "error"

    articles = repo.get_editor_articles()
    editions = repo.get_editions()
    upcoming_issues = repo.get_upcoming_issues(limit=20)
    sections = repo.get_active_sections()
    return render("editor_articles.html",
        articles=articles, editions=editions,
        upcoming_issues=upcoming_issues, sections=sections,
        statuses=STATUSES, message=message, level=level,
    )


@router.get("/{article_id}", response_class=HTMLResponse)
async def editor_article_detail(article_id: int):
    repo = get_repo()
    article = repo.get_editor_article(article_id)
    if not article:
        return render("partials/alert.html", message="Article not found.", level="error")
    editions = repo.get_editions()
    upcoming_issues = repo.get_upcoming_issues(limit=20)
    sections = repo.get_active_sections()
    return render("editor_article_detail.html",
        article=article, editions=editions,
        upcoming_issues=upcoming_issues, sections=sections,
        statuses=STATUSES,
    )


@router.post("/{article_id}/save", response_class=HTMLResponse)
async def save_article(
    article_id: int,
    title: str = Form(...),
    content: str = Form(""),
    author_name: str = Form("John"),
    edition_slug: str = Form(""),
    target_issue_id: int = Form(0),
    target_section_slug: str = Form(""),
    notes: str = Form(""),
    status: str = Form("draft"),
):
    repo = get_repo()
    try:
        repo.update_editor_article(
            article_id, title=title, content=content,
            author_name=author_name, edition_slug=edition_slug,
            target_issue_id=target_issue_id or None,
            target_section_slug=target_section_slug,
            notes=notes, status=status,
        )
        message = "Article saved."
        level = "success"
    except Exception as e:
        message = f"Save failed: {e}"
        level = "error"

    article = repo.get_editor_article(article_id)
    editions = repo.get_editions()
    upcoming_issues = repo.get_upcoming_issues(limit=20)
    sections = repo.get_active_sections()
    return render("editor_article_detail.html",
        article=article, editions=editions,
        upcoming_issues=upcoming_issues, sections=sections,
        statuses=STATUSES, message=message, level=level,
    )


@router.post("/{article_id}/assign", response_class=HTMLResponse)
async def assign_to_issue(article_id: int):
    """Create a draft from this editor article and assign it to the target issue."""
    repo = get_repo()
    article = repo.get_editor_article(article_id)
    if not article:
        return render("partials/alert.html", message="Article not found.", level="error")

    if not article["target_issue_id"]:
        return render("partials/alert.html", message="No issue selected. Save with an issue first.", level="error")
    if not article["target_section_slug"]:
        return render("partials/alert.html", message="No section selected. Save with a section first.", level="error")
    if not article["content"]:
        return render("partials/alert.html", message="Article has no content.", level="error")

    try:
        draft_id = repo.create_draft(
            issue_id=article["target_issue_id"],
            section_slug=article["target_section_slug"],
            content=article["content"],
            ai_model="editor",
            prompt_used=f"Editor article by {article['author_name']}: {article['title']}",
        )
        # Auto-approve editor articles
        repo.update_draft_status(draft_id, "approved")
        repo.update_editor_article(article_id, status="assigned", draft_id=draft_id)
        message = f"Draft created and approved for Issue #{article['target_issue_id']}."
        level = "success"
    except Exception as e:
        message = f"Assignment failed: {e}"
        level = "error"

    article = repo.get_editor_article(article_id)
    editions = repo.get_editions()
    upcoming_issues = repo.get_upcoming_issues(limit=20)
    sections = repo.get_active_sections()
    return render("editor_article_detail.html",
        article=article, editions=editions,
        upcoming_issues=upcoming_issues, sections=sections,
        statuses=STATUSES, message=message, level=level,
    )


@router.post("/{article_id}/delete", response_class=HTMLResponse)
async def delete_article(article_id: int):
    repo = get_repo()
    try:
        repo.delete_editor_article(article_id)
        message = "Article deleted."
        level = "success"
    except Exception as e:
        message = f"Delete failed: {e}"
        level = "error"

    articles = repo.get_editor_articles()
    editions = repo.get_editions()
    upcoming_issues = repo.get_upcoming_issues(limit=20)
    sections = repo.get_active_sections()
    return render("editor_articles.html",
        articles=articles, editions=editions,
        upcoming_issues=upcoming_issues, sections=sections,
        statuses=STATUSES, message=message, level=level,
    )
