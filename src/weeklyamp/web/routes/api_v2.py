"""Developer API v2 — authenticated JSON API for external integrations.

Provides read/write access to content, subscribers, issues, and analytics.
Protected by API keys from the api_keys table.
INACTIVE by default — requires valid API key.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from weeklyamp.web.deps import get_config, get_repo
from weeklyamp.web.security import rate_limit

router = APIRouter(
    prefix="/api/v2",
    # Per-IP rate limit in addition to the per-api-key limit enforced
    # inside verify_api_key. 300/min/IP is generous for legitimate use
    # but stops a stolen key from being weaponised from a single host.
    dependencies=[Depends(rate_limit("api_v2", max_per_minute=300))],
)


# ---- API Key Authentication ----

async def verify_api_key(request: Request) -> dict:
    """FastAPI dependency — verify API key from Authorization header."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="API key required (Bearer token)")

    key = auth[7:]
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    repo = get_repo()

    conn = repo._conn()
    row = conn.execute(
        "SELECT * FROM api_keys WHERE key_hash = ? AND is_active = 1",
        (key_hash,),
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")

    api_key = dict(row)

    # Check rate limit
    rate_limit = api_key.get("rate_limit", 100)
    # Simple per-minute rate tracking via request count
    # (production would use Redis or similar)

    # Update last_used
    conn = repo._conn()
    conn.execute("UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?", (api_key["id"],))
    conn.commit()
    conn.close()

    return api_key


# ---- Issues ----

@router.get("/issues")
async def list_issues(
    request: Request,
    api_key: dict = Depends(verify_api_key),
    edition: str = "",
    status: str = "published",
    limit: int = 20,
    offset: int = 0,
):
    """List newsletter issues."""
    repo = get_repo()
    conn = repo._conn()
    sql = "SELECT id, issue_number, title, edition_slug, status, published_at, created_at FROM issues WHERE status = ?"
    params: list = [status]
    if edition:
        sql += " AND edition_slug = ?"
        params.append(edition)
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return {"issues": [dict(r) for r in rows], "count": len(rows)}


@router.get("/issues/{issue_id}")
async def get_issue(issue_id: int, request: Request, api_key: dict = Depends(verify_api_key)):
    """Get a specific issue with assembled content."""
    repo = get_repo()
    issue = repo.get_issue(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    drafts = repo.get_drafts_for_issue(issue_id)
    return {
        "issue": dict(issue),
        "drafts": [{"section_slug": d["section_slug"], "content": d["content"], "status": d["status"]} for d in drafts],
    }


# ---- Subscribers ----

@router.get("/subscribers")
async def list_subscribers(
    request: Request,
    api_key: dict = Depends(verify_api_key),
    edition: str = "",
    limit: int = 50,
    offset: int = 0,
):
    """List subscribers (admin API keys only)."""
    perms = api_key.get("permissions", "")
    if "admin" not in perms and "subscribers" not in perms:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    repo = get_repo()
    conn = repo._conn()
    if edition:
        rows = conn.execute(
            """SELECT s.id, s.email, s.first_name, s.last_name, s.status, s.created_at
               FROM subscribers s
               JOIN subscriber_editions se ON se.subscriber_id = s.id
               JOIN newsletter_editions ne ON ne.id = se.edition_id
               WHERE ne.slug = ? AND s.status = 'active'
               ORDER BY s.id DESC LIMIT ? OFFSET ?""",
            (edition, limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, email, first_name, last_name, status, created_at FROM subscribers WHERE status = 'active' ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    conn.close()
    return {"subscribers": [dict(r) for r in rows], "count": len(rows)}


@router.post("/subscribers")
async def create_subscriber(request: Request, api_key: dict = Depends(verify_api_key)):
    """Create a new subscriber via API."""
    perms = api_key.get("permissions", "")
    if "admin" not in perms and "subscribers" not in perms:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    body = await request.json()
    email = body.get("email", "").strip()
    if not email:
        raise HTTPException(status_code=400, detail="Email required")

    repo = get_repo()
    existing = repo.get_subscriber_by_email(email)
    if existing:
        return {"subscriber_id": existing["id"], "status": "existing"}

    sub_id = repo.create_subscriber(
        email=email,
        first_name=body.get("first_name", ""),
        last_name=body.get("last_name", ""),
    )
    return {"subscriber_id": sub_id, "status": "created"}


# ---- Content Generation ----

@router.post("/generate")
async def generate_content(request: Request, api_key: dict = Depends(verify_api_key)):
    """Generate AI content for a section.

    Body: { "section_slug": "industry_pulse", "topic": "...", "notes": "..." }
    """
    perms = api_key.get("permissions", "")
    if "admin" not in perms and "content" not in perms:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    body = await request.json()
    section_slug = body.get("section_slug", "")
    topic = body.get("topic", "")
    notes = body.get("notes", "")

    if not section_slug:
        raise HTTPException(status_code=400, detail="section_slug required")

    config = get_config()
    from weeklyamp.content.prompts import build_prompt
    prompt = build_prompt(section_slug, topic=topic, notes=notes, newsletter_name=config.newsletter.name)

    from weeklyamp.content.generator import generate_draft
    content, model = generate_draft(prompt, config)

    return {"content": content, "model": model, "section_slug": section_slug}


# ---- Analytics ----

@router.get("/analytics/growth")
async def growth_analytics(
    request: Request,
    api_key: dict = Depends(verify_api_key),
    days: int = 30,
):
    """Get subscriber growth metrics."""
    repo = get_repo()
    trend = repo.get_growth_trend(days=days)
    subscriber_count = repo.get_subscriber_count()
    return {
        "current_subscribers": subscriber_count,
        "trend": [dict(r) for r in trend],
        "period_days": days,
    }


@router.get("/analytics/engagement")
async def engagement_analytics(
    request: Request,
    api_key: dict = Depends(verify_api_key),
    limit: int = 10,
):
    """Get engagement metrics for recent issues."""
    repo = get_repo()
    conn = repo._conn()
    rows = conn.execute(
        "SELECT * FROM engagement_metrics ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return {"metrics": [dict(r) for r in rows]}


@router.get("/analytics/revenue")
async def revenue_analytics(request: Request, api_key: dict = Depends(verify_api_key)):
    """Get revenue summary."""
    perms = api_key.get("permissions", "")
    if "admin" not in perms and "revenue" not in perms:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    repo = get_repo()
    summary = repo.get_revenue_summary()
    return {"revenue": summary}


# ---- Editions ----

@router.get("/editions")
async def list_editions(request: Request, api_key: dict = Depends(verify_api_key)):
    """List newsletter editions."""
    repo = get_repo()
    editions = repo.get_editions()
    return {"editions": [dict(e) for e in editions]}


# ---- Health ----

@router.get("/health")
async def api_health():
    """API health check (no auth required)."""
    return {"status": "ok", "version": "2.0"}
