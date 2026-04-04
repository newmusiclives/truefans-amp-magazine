"""Subscriber routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from weeklyamp.delivery.subscribers import sync_subscribers
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def subscribers_page():
    cfg = get_config()
    repo = get_repo()
    active = repo.get_subscriber_count()
    subs = repo.get_subscribers("active")
    issue = repo.get_current_issue()
    engagement = repo.get_engagement(issue["id"]) if issue else None
    has_ghl = bool(cfg.ghl.api_key and cfg.ghl.location_id)

    return render("subscribers.html",
        active=active,
        subscribers=subs,
        engagement=engagement,
        issue=issue,
        has_ghl=has_ghl,
    )


@router.post("/sync", response_class=HTMLResponse)
async def sync():
    cfg = get_config()
    repo = get_repo()

    if not cfg.ghl.api_key:
        return render("partials/alert.html", message="GoHighLevel not configured.", level="error")

    try:
        result = sync_subscribers(repo, cfg.ghl)
        return render("partials/alert.html",
            message=f"Synced {result['synced']} subscribers ({result['new']} new, {result['total']} total).",
            level="success")
    except Exception as exc:
        return render("partials/alert.html", message=f"Sync failed: {exc}", level="error")


@router.get("/export", response_class=HTMLResponse)
async def export_subscribers(request: Request):
    import csv
    import io
    from fastapi.responses import StreamingResponse

    repo = get_repo()
    subscribers = repo.get_subscribers("active")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["email", "status", "source_channel", "subscribed_at"])
    for sub in subscribers:
        writer.writerow([sub.get("email", ""), sub.get("status", ""), sub.get("source_channel", ""), sub.get("subscribed_at", "")])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=subscribers_export.csv"},
    )


@router.get("/import", response_class=HTMLResponse)
async def import_page(request: Request):
    config = get_config()
    editions = get_repo().get_editions()
    return HTMLResponse(render("subscriber_import.html", editions=editions, config=config))


@router.post("/import", response_class=HTMLResponse)
async def import_csv(request: Request):
    import csv
    import io
    repo = get_repo()
    form = await request.form()
    file = form.get("csv_file")
    default_edition = form.get("edition_slug", "fan")

    if not file:
        return HTMLResponse('<div class="alert alert-danger">No file uploaded.</div>')

    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    imported = 0
    skipped = 0
    errors = []

    for row in reader:
        email = (row.get("email") or row.get("Email") or row.get("EMAIL") or "").strip().lower()
        if not email or "@" not in email:
            skipped += 1
            continue

        first_name = row.get("first_name") or row.get("First Name") or row.get("name") or row.get("Name") or ""
        edition = row.get("edition") or row.get("Edition") or default_edition

        try:
            repo.subscribe_to_editions(
                email=email,
                edition_slugs=[edition],
                first_name=first_name.strip(),
                source_channel="csv_import",
            )
            imported += 1
        except Exception as e:
            errors.append(f"{email}: {e}")
            skipped += 1

    result = f'<div class="alert alert-success">Imported {imported} subscribers. Skipped {skipped}.'
    if errors:
        result += f' Errors: {len(errors)}'
    result += '</div>'
    return HTMLResponse(result)
