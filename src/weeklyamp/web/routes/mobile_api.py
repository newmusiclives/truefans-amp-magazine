"""Mobile API endpoints — JSON-based API for the TrueFans mobile app.

All endpoints return JSON. Authentication via Bearer token (subscriber's unsubscribe_token as API key).
"""

from __future__ import annotations

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from weeklyamp.web.deps import get_config, get_repo

router = APIRouter()


def _get_subscriber(repo, token: str):
    """Look up subscriber by their unsubscribe_token (used as API auth)."""
    if not token:
        return None
    conn = repo._conn()
    row = conn.execute("SELECT * FROM subscribers WHERE unsubscribe_token = ? AND status = 'active'", (token,)).fetchone()
    conn.close()
    return dict(row) if row else None


@router.get("/editions")
async def api_editions():
    """List available newsletter editions."""
    repo = get_repo()
    editions = repo.get_editions()
    return JSONResponse([{
        "slug": e["slug"], "name": e["name"], "tagline": e.get("tagline", ""),
        "color": e.get("color", ""), "icon": e.get("icon", ""),
    } for e in editions])


@router.get("/issues")
async def api_issues(edition: str = "", limit: int = 20):
    """List published issues, optionally filtered by edition."""
    repo = get_repo()
    issues = repo.get_published_issues(limit=limit)
    if edition:
        issues = [i for i in issues if i.get("edition_slug") == edition]
    return JSONResponse([{
        "id": i["id"], "issue_number": i["issue_number"],
        "edition_slug": i.get("edition_slug", ""), "title": i.get("title", ""),
        "status": i["status"], "publish_date": str(i.get("publish_date", "")),
    } for i in issues])


@router.get("/issues/{issue_id}")
async def api_issue_detail(issue_id: int):
    """Get full issue content."""
    repo = get_repo()
    issue = repo.get_issue(issue_id)
    if not issue:
        return JSONResponse({"error": "Issue not found"}, status_code=404)
    assembled = repo.get_assembled(issue_id)
    audio = repo.get_audio_issue(issue_id)
    return JSONResponse({
        "id": issue["id"], "issue_number": issue["issue_number"],
        "edition_slug": issue.get("edition_slug", ""), "title": issue.get("title", ""),
        "html_content": assembled.get("html_content", "") if assembled else "",
        "plain_text": assembled.get("plain_text", "") if assembled else "",
        "audio_url": audio.get("audio_url", "") if audio and audio.get("status") == "complete" else "",
    })


@router.get("/profile")
async def api_profile(authorization: str = Header("")):
    """Get subscriber profile and preferences."""
    repo = get_repo()
    token = authorization.replace("Bearer ", "").strip()
    subscriber = _get_subscriber(repo, token)
    if not subscriber:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Get edition subscriptions
    conn = repo._conn()
    editions = conn.execute(
        """SELECT ne.slug, ne.name, se.send_days
           FROM subscriber_editions se
           JOIN newsletter_editions ne ON ne.id = se.edition_id
           WHERE se.subscriber_id = ?""",
        (subscriber["id"],),
    ).fetchall()
    conn.close()

    return JSONResponse({
        "id": subscriber["id"],
        "email": subscriber["email"],
        "status": subscriber["status"],
        "editions": [{"slug": e["slug"], "name": e["name"], "send_days": e["send_days"]} for e in editions],
    })


@router.get("/community")
async def api_community():
    """List forum categories and recent threads."""
    repo = get_repo()
    categories = repo.get_forum_categories()
    result = []
    for cat in categories:
        threads = repo.get_forum_threads(cat["id"], limit=5)
        result.append({
            "slug": cat["slug"], "name": cat["name"],
            "description": cat.get("description", ""), "edition_slug": cat.get("edition_slug", ""),
            "thread_count": len(threads),
            "recent_threads": [{"id": t["id"], "title": t["title"], "reply_count": t.get("reply_count", 0)} for t in threads],
        })
    return JSONResponse(result)


@router.get("/trivia")
async def api_trivia():
    """List active trivia questions and polls."""
    repo = get_repo()
    conn = repo._conn()
    rows = conn.execute("SELECT * FROM trivia_polls WHERE status = 'active' ORDER BY created_at DESC LIMIT 10").fetchall()
    conn.close()
    import json
    return JSONResponse([{
        "id": r["id"], "question_type": r["question_type"],
        "question_text": r["question_text"],
        "options": json.loads(r.get("options_json", "[]")),
        "edition_slug": r.get("edition_slug", ""),
    } for r in [dict(row) for row in rows]])
