"""Publish routes — assemble, preview, push via GoHighLevel."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from weeklyamp.content.assembly import assemble_newsletter
from weeklyamp.delivery.ghl import GHLClient
from weeklyamp.delivery.smtp_sender import SMTPSender
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def publish_page():
    cfg = get_config()
    repo = get_repo()
    issue = repo.get_current_issue()
    assembled = repo.get_assembled(issue["id"]) if issue else None
    has_ghl = bool(cfg.ghl.api_key and cfg.ghl.location_id)
    has_email = bool(cfg.email.enabled and cfg.email.smtp_host)

    drafts = repo.get_drafts_for_issue(issue["id"]) if issue else []
    approved = sum(1 for d in drafts if d["status"] in ("approved", "revised"))

    # Use edition-scoped section count if applicable
    edition_slug = issue.get("edition_slug", "") if issue else ""
    edition = None
    if edition_slug:
        edition = repo.get_edition_by_slug(edition_slug)
        edition_sections = repo.get_edition_sections(edition_slug)
        total = len(edition_sections)
    else:
        total = len(repo.get_active_sections())

    return render("publish.html",
        issue=issue,
        assembled=assembled,
        has_ghl=has_ghl,
        has_email=has_email,
        approved=approved,
        total=total,
        config=cfg,
        edition=edition,
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
    """Send assembled newsletter via SMTP to edition subscribers."""
    cfg = get_config()
    repo = get_repo()
    issue = repo.get_current_issue()
    assembled = repo.get_assembled(issue["id"]) if issue else None

    if not assembled:
        return render("partials/alert.html", message="Not assembled yet.", level="error")

    if not cfg.email.enabled or not cfg.email.smtp_host:
        return render("partials/alert.html",
            message="Email not configured. Set WEEKLYAMP_EMAIL_ENABLED=true and SMTP settings in .env",
            level="error")

    # Build subject line
    edition_slug = issue.get("edition_slug", "") if issue else ""
    if edition_slug:
        ed = repo.get_edition_by_slug(edition_slug)
        ed_name = ed.get("name", "") if ed else ""
        subject = f"{cfg.newsletter.name} — {ed_name} #{issue['issue_number']}"
    else:
        subject = f"{cfg.newsletter.name} #{issue['issue_number']}"

    # Get recipients: all active subscribers (or filtered by edition tag via GHL)
    recipients = repo.get_subscribers("active")

    sender = SMTPSender(cfg.email)
    try:
        result = sender.send_bulk(
            recipients=recipients,
            subject=subject,
            html_body=assembled["html_content"],
            plain_text=assembled.get("plain_text", ""),
            site_domain=cfg.site_domain,
        )
        repo.update_assembled_ghl(assembled["id"], f"smtp-{issue['id']}")
        if result["sent"] > 0:
            repo.update_issue_status(issue["id"], "published")
        msg = f"Sent to {result['sent']} subscribers"
        if result["failed"]:
            msg += f" ({result['failed']} failed)"
        return render("partials/alert.html", message=msg, level="success")
    except Exception as exc:
        return render("partials/alert.html", message=f"Send failed: {exc}", level="error")


@router.post("/test-send", response_class=HTMLResponse)
async def test_send():
    """Send a test email to the configured from_address."""
    cfg = get_config()
    repo = get_repo()
    issue = repo.get_current_issue()
    assembled = repo.get_assembled(issue["id"]) if issue else None

    if not assembled:
        return render("partials/alert.html", message="Not assembled yet.", level="error")
    if not cfg.email.enabled or not cfg.email.from_address:
        return render("partials/alert.html", message="Email not configured.", level="error")

    edition_slug = issue.get("edition_slug", "") if issue else ""
    if edition_slug:
        ed = repo.get_edition_by_slug(edition_slug)
        ed_name = ed.get("name", "") if ed else ""
        subject = f"[TEST] {cfg.newsletter.name} — {ed_name} #{issue['issue_number']}"
    else:
        subject = f"[TEST] {cfg.newsletter.name} #{issue['issue_number']}"

    sender = SMTPSender(cfg.email)
    success = sender.send_single(
        to_email=cfg.email.from_address,
        subject=subject,
        html_body=assembled["html_content"],
        plain_text=assembled.get("plain_text", ""),
    )
    if success:
        return render("partials/alert.html",
            message=f"Test email sent to {cfg.email.from_address}", level="success")
    return render("partials/alert.html", message="Test send failed — check SMTP settings", level="error")


@router.get("/spam-check/{issue_id}", response_class=HTMLResponse)
async def spam_check(issue_id: int, request: Request):
    repo = get_repo()
    assembled = repo.get_assembled(issue_id)
    if not assembled:
        return HTMLResponse('<div class="alert alert-warning">Issue not assembled yet.</div>')
    from weeklyamp.content.spam_check import check_spam_score
    result = check_spam_score(assembled.get("html_content", ""), assembled.get("subject", ""))

    color = "#10b981" if result["score"] <= 25 else "#f59e0b" if result["score"] <= 50 else "#ef4444"
    html = f'<div class="card" style="margin-top:1rem">'
    html += f'<h4>Spam Score: <span style="color:{color};font-size:24px;">{result["score"]}/100</span> — {result["rating"]}</h4>'
    html += f'<p>Words: {result["word_count"]} | Links: {result["link_count"]} | Images: {result["image_count"]}</p>'
    if result["issues"]:
        html += '<h5>Issues</h5><ul>'
        for issue in result["issues"]:
            html += f'<li style="color:#ef4444;">{issue}</li>'
        html += '</ul>'
    html += '<h5>Recommendations</h5><ul>'
    for rec in result["recommendations"]:
        html += f'<li>{rec}</li>'
    html += '</ul></div>'
    return HTMLResponse(html)


@router.post("/generate-audio", response_class=HTMLResponse)
async def generate_audio(request: Request, issue_id: int = Form(...)):
    repo = get_repo()
    config = get_config()
    from weeklyamp.content.audio import generate_audio_newsletter
    audio_id = generate_audio_newsletter(repo, config, issue_id)
    if audio_id:
        return HTMLResponse(f'<div class="alert alert-success">Audio generated successfully! <a href="/audio/{issue_id}">Listen</a></div>')
    return HTMLResponse('<div class="alert alert-warning">Audio generation failed. Check that audio is enabled and the issue is assembled.</div>')
