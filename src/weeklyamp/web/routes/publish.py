"""Publish routes — assemble, preview, push."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from weeklyamp.content.assembly import assemble_newsletter
from weeklyamp.delivery.beehiiv import BeehiivClient
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def publish_page():
    cfg = get_config()
    repo = get_repo()
    issue = repo.get_current_issue()
    assembled = repo.get_assembled(issue["id"]) if issue else None
    has_beehiiv = bool(cfg.beehiiv.api_key and cfg.beehiiv.publication_id)

    drafts = repo.get_drafts_for_issue(issue["id"]) if issue else []
    approved = sum(1 for d in drafts if d["status"] in ("approved", "revised"))
    total = len(repo.get_active_sections())

    return render("publish.html",
        issue=issue,
        assembled=assembled,
        has_beehiiv=has_beehiiv,
        approved=approved,
        total=total,
        config=cfg,
    )


@router.post("/assemble", response_class=HTMLResponse)
async def assemble():
    cfg = get_config()
    repo = get_repo()
    issue = repo.get_current_issue()
    if not issue:
        return render("partials/alert.html", message="No current issue.", level="error")

    try:
        html, plain = assemble_newsletter(repo, issue["id"], cfg)
        repo.save_assembled(issue["id"], html, plain)
        repo.update_issue_status(issue["id"], "assembled")
        return render("partials/assemble_result.html",
            success=True, html_len=len(html), plain_len=len(plain))
    except Exception as exc:
        return render("partials/alert.html", message=f"Assembly failed: {exc}", level="error")


@router.get("/preview", response_class=HTMLResponse)
async def preview():
    repo = get_repo()
    issue = repo.get_current_issue()
    if not issue:
        return HTMLResponse("<p>No current issue.</p>")
    assembled = repo.get_assembled(issue["id"])
    if not assembled:
        return HTMLResponse("<p>Not yet assembled.</p>")
    return HTMLResponse(assembled["html_content"])


@router.post("/push", response_class=HTMLResponse)
async def push():
    cfg = get_config()
    repo = get_repo()
    issue = repo.get_current_issue()
    assembled = repo.get_assembled(issue["id"]) if issue else None

    if not assembled:
        return render("partials/alert.html", message="Not assembled yet.", level="error")
    if not cfg.beehiiv.api_key:
        return render("partials/alert.html", message="Beehiiv not configured.", level="error")

    client = BeehiivClient(cfg.beehiiv)
    title = f"{cfg.newsletter.name} #{issue['issue_number']}"
    try:
        result = client.create_post(title=title, html_content=assembled["html_content"], send=False)
        post_id = result.get("id", "")
        repo.update_assembled_beehiiv(assembled["id"], post_id)
        return render("partials/alert.html",
            message=f"Draft created in Beehiiv! Post ID: {post_id}", level="success")
    except Exception as exc:
        return render("partials/alert.html", message=f"Push failed: {exc}", level="error")
    finally:
        client.close()
