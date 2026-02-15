"""Guest article routes."""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from weeklyamp.guests.manager import GuestArticleManager
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()

PERMISSION_STATES = ["requested", "received", "approved", "published", "declined"]


@router.get("/", response_class=HTMLResponse)
async def guests_page():
    repo = get_repo()
    articles = repo.get_guest_articles()
    contacts = repo.get_guest_contacts()
    return render("guests.html",
        articles=articles, contacts=contacts,
        permission_states=PERMISSION_STATES,
    )


@router.post("/contacts/add", response_class=HTMLResponse)
async def add_contact(
    name: str = Form(...),
    email: str = Form(""),
    organization: str = Form(""),
    role: str = Form(""),
    website: str = Form(""),
    notes: str = Form(""),
):
    repo = get_repo()
    try:
        repo.create_guest_contact(name, email, organization, role, website, notes)
        message = f"Added contact: {name}"
        level = "success"
    except Exception as e:
        message = f"Failed: {e}"
        level = "error"

    contacts = repo.get_guest_contacts()
    return render("partials/guest_contacts_table.html",
        contacts=contacts, message=message, level=level)


@router.post("/request", response_class=HTMLResponse)
async def request_article(
    contact_id: int = Form(...),
    topic: str = Form(""),
    notes: str = Form(""),
):
    repo = get_repo()
    config = get_config()
    manager = GuestArticleManager(repo, config)
    try:
        manager.request_article(contact_id, topic, notes)
        message = "Article request created."
        level = "success"
    except Exception as e:
        message = f"Failed: {e}"
        level = "error"

    articles = repo.get_guest_articles()
    contacts = repo.get_guest_contacts()
    return render("guests.html",
        articles=articles, contacts=contacts,
        permission_states=PERMISSION_STATES,
        message=message, level=level,
    )


@router.get("/{article_id}", response_class=HTMLResponse)
async def guest_detail(article_id: int):
    repo = get_repo()
    article = repo.get_guest_article(article_id)
    if not article:
        return render("partials/alert.html", message="Article not found.", level="error")
    upcoming_issues = repo.get_upcoming_issues(limit=10)
    return render("guest_detail.html",
        article=article, upcoming_issues=upcoming_issues,
        permission_states=PERMISSION_STATES,
    )


@router.post("/{article_id}/permission", response_class=HTMLResponse)
async def update_permission(article_id: int, permission_state: str = Form(...)):
    repo = get_repo()
    config = get_config()
    manager = GuestArticleManager(repo, config)
    try:
        manager.track_permission(article_id, permission_state)
        message = f"Permission updated to: {permission_state}"
        level = "success"
    except Exception as e:
        message = f"Failed: {e}"
        level = "error"

    article = repo.get_guest_article(article_id)
    upcoming_issues = repo.get_upcoming_issues(limit=10)
    return render("guest_detail.html",
        article=article, upcoming_issues=upcoming_issues,
        permission_states=PERMISSION_STATES,
        message=message, level=level,
    )


@router.post("/{article_id}/approve", response_class=HTMLResponse)
async def approve_article(
    article_id: int,
    issue_id: int = Form(0),
    section_slug: str = Form("guest_column"),
):
    repo = get_repo()
    config = get_config()
    manager = GuestArticleManager(repo, config)
    try:
        manager.approve_article(article_id, issue_id if issue_id else None, section_slug)
        if issue_id:
            manager.create_draft_from_guest(article_id)
            message = "Article approved and draft created."
        else:
            message = "Article approved."
        level = "success"
    except Exception as e:
        message = f"Failed: {e}"
        level = "error"

    article = repo.get_guest_article(article_id)
    upcoming_issues = repo.get_upcoming_issues(limit=10)
    return render("guest_detail.html",
        article=article, upcoming_issues=upcoming_issues,
        permission_states=PERMISSION_STATES,
        message=message, level=level,
    )
