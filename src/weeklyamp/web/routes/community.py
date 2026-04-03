"""Community forum routes — public discussion by edition."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()

EDITION_LABELS = {"fan": "Fan Edition", "artist": "Artist Edition", "industry": "Industry Edition"}


@router.get("/community", response_class=HTMLResponse)
async def community_home(request: Request):
    repo = get_repo()
    config = get_config()
    categories = repo.get_forum_categories()
    # Group by edition
    editions = {}
    for cat in categories:
        ed = cat.get("edition_slug", "general")
        editions.setdefault(ed, []).append(cat)
    return HTMLResponse(render("community.html", editions=editions, edition_labels=EDITION_LABELS, config=config))


@router.get("/community/{category_slug}", response_class=HTMLResponse)
async def community_category(category_slug: str, request: Request):
    repo = get_repo()
    config = get_config()
    category = repo.get_forum_category_by_slug(category_slug)
    if not category:
        return HTMLResponse("Category not found", status_code=404)
    threads = repo.get_forum_threads(category["id"])
    return HTMLResponse(render("community_category.html", category=category, threads=threads, config=config))


@router.get("/community/{category_slug}/{thread_id}", response_class=HTMLResponse)
async def community_thread(category_slug: str, thread_id: int, request: Request):
    repo = get_repo()
    config = get_config()
    thread = repo.get_forum_thread(thread_id)
    if not thread:
        return HTMLResponse("Thread not found", status_code=404)
    replies = repo.get_forum_replies(thread_id)
    return HTMLResponse(render("community_thread.html", thread=thread, replies=replies, category_slug=category_slug, config=config))


@router.post("/community/{category_slug}/new", response_class=HTMLResponse)
async def create_thread(category_slug: str, request: Request, title: str = Form(...), content: str = Form(""), subscriber_id: int = Form(0)):
    repo = get_repo()
    category = repo.get_forum_category_by_slug(category_slug)
    if not category:
        return HTMLResponse("Category not found", status_code=404)
    thread_id = repo.create_forum_thread(category["id"], subscriber_id, title, content)
    return HTMLResponse(f'<div class="alert alert-success">Thread created! <a href="/community/{category_slug}/{thread_id}">View thread</a></div>')


@router.post("/community/{category_slug}/{thread_id}/reply", response_class=HTMLResponse)
async def post_reply(category_slug: str, thread_id: int, request: Request, content: str = Form(...), subscriber_id: int = Form(0)):
    repo = get_repo()
    repo.create_forum_reply(thread_id, subscriber_id, content)
    return HTMLResponse('<div class="alert alert-success">Reply posted!</div>')
