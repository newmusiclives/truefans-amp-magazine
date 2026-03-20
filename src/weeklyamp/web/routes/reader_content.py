"""Reader content routes — public submission and admin review."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from jinja2 import Environment, FileSystemLoader

from weeklyamp.content.reader_content import ReaderContentManager
from weeklyamp.web.deps import get_config, get_repo, render

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent.parent / "templates" / "web"
_pub_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

router = APIRouter()


def _get_manager():
    cfg = get_config()
    repo = get_repo()
    return ReaderContentManager(repo, cfg.reader_content), repo, cfg


# ---- Public routes ----


@router.get("/contribute", response_class=HTMLResponse)
async def contribute_form():
    """Reader submission form (public)."""
    manager, repo, cfg = _get_manager()
    editions = repo.get_editions(active_only=True)
    tpl = _pub_env.get_template("contribute.html")
    return tpl.render(editions=editions, enabled=cfg.reader_content.enabled)


@router.post("/contribute", response_class=HTMLResponse)
async def contribute_submit(request: Request):
    """Submit a reader contribution (public)."""
    manager, repo, cfg = _get_manager()
    form = await request.form()

    email = form.get("email", "").strip()[:254]
    name = form.get("name", "").strip()[:100]
    content_type = form.get("content_type", "hot_take")
    content = form.get("content", "").strip()[:2000]
    edition_slug = form.get("edition_slug", "")

    editions = repo.get_editions(active_only=True)
    tpl = _pub_env.get_template("contribute.html")

    # Validate
    if not email or not _EMAIL_RE.match(email):
        return HTMLResponse(tpl.render(
            editions=editions, enabled=cfg.reader_content.enabled,
            error="Please enter a valid email address.",
            email=email, name=name, content_type=content_type,
            content=content, edition_slug=edition_slug,
        ))

    if not content or len(content) < 10:
        return HTMLResponse(tpl.render(
            editions=editions, enabled=cfg.reader_content.enabled,
            error="Please write at least 10 characters.",
            email=email, name=name, content_type=content_type,
            content=content, edition_slug=edition_slug,
        ))

    try:
        contrib_id = manager.submit_contribution(
            email=email,
            name=name,
            content_type=content_type,
            content=content,
            edition_slug=edition_slug,
        )
        return HTMLResponse(tpl.render(
            editions=editions, enabled=cfg.reader_content.enabled,
            success="Thanks for your submission! It may be featured in an upcoming issue.",
        ))
    except Exception as exc:
        logger.exception("Contribution submission failed")
        return HTMLResponse(tpl.render(
            editions=editions, enabled=cfg.reader_content.enabled,
            error=f"Something went wrong: {exc}",
            email=email, name=name, content_type=content_type,
            content=content, edition_slug=edition_slug,
        ))


# ---- Admin routes ----


@router.get("/admin/reader-content", response_class=HTMLResponse)
async def admin_reader_content():
    """Admin page to review reader contributions."""
    manager, repo, cfg = _get_manager()
    contributions = manager.get_all()

    issues = []
    try:
        conn = repo._conn()
        rows = conn.execute(
            "SELECT id, issue_number, title, edition_slug FROM issues ORDER BY issue_number DESC LIMIT 20"
        ).fetchall()
        conn.close()
        issues = [dict(r) for r in rows]
    except Exception:
        pass

    return render("admin_reader_content.html",
        contributions=contributions,
        issues=issues,
        enabled=cfg.reader_content.enabled,
    )


@router.post("/admin/reader-content/{contrib_id}/approve", response_class=HTMLResponse)
async def admin_approve(contrib_id: int):
    """Approve a contribution."""
    manager, repo, cfg = _get_manager()
    manager.approve(contrib_id)

    contributions = manager.get_all()
    return render("admin_reader_content.html",
        contributions=contributions, issues=[],
        enabled=cfg.reader_content.enabled,
        message=f"Contribution #{contrib_id} approved", level="success",
    )


@router.post("/admin/reader-content/{contrib_id}/feature/{issue_id}", response_class=HTMLResponse)
async def admin_feature(contrib_id: int, issue_id: int):
    """Feature a contribution in an issue."""
    manager, repo, cfg = _get_manager()
    manager.feature_in_issue(contrib_id, issue_id)

    contributions = manager.get_all()
    return render("admin_reader_content.html",
        contributions=contributions, issues=[],
        enabled=cfg.reader_content.enabled,
        message=f"Contribution #{contrib_id} featured in issue #{issue_id}", level="success",
    )


@router.post("/admin/reader-content/{contrib_id}/reject", response_class=HTMLResponse)
async def admin_reject(contrib_id: int):
    """Reject a contribution."""
    manager, repo, cfg = _get_manager()
    manager.reject(contrib_id)

    contributions = manager.get_all()
    return render("admin_reader_content.html",
        contributions=contributions, issues=[],
        enabled=cfg.reader_content.enabled,
        message=f"Contribution #{contrib_id} rejected", level="success",
    )
