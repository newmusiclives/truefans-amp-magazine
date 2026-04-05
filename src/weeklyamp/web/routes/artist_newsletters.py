"""Artist newsletter waitlist and admin routes."""
from __future__ import annotations
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()

@router.get("/artist-newsletters", response_class=HTMLResponse)
async def landing_page(request: Request):
    config = get_config()
    return HTMLResponse(render("artist_newsletters_landing.html", config=config))

@router.post("/artist-newsletters/waitlist", response_class=HTMLResponse)
async def waitlist_signup(request: Request, artist_name: str = Form(...), email: str = Form(...), website: str = Form(""), genre: str = Form(""), fan_count: str = Form(""), message: str = Form("")):
    repo = get_repo()
    repo.create_artist_newsletter_waitlist(artist_name, email, website, genre=genre, fan_count=fan_count, message=message)
    return HTMLResponse('<div style="padding:24px;text-align:center;color:#10b981;font-size:18px;font-weight:600;">You\'re on the list! We\'ll be in touch soon.</div>')

@router.post("/artist-newsletters/signup", response_class=HTMLResponse)
async def artist_signup(request: Request, artist_name: str = Form(...), email: str = Form(...), website: str = Form(""), genre: str = Form(""), fan_count: str = Form(""), plan: str = Form("starter")):
    repo = get_repo()
    config = get_config()
    # Create the newsletter
    import re
    slug = re.sub(r'[^a-z0-9]+', '-', artist_name.lower()).strip('-')
    newsletter_id = repo.create_artist_newsletter(artist_name, slug, tagline=f"{genre} artist", template_style="minimal")
    # Also save to waitlist for tracking
    repo.create_artist_newsletter_waitlist(artist_name, email, website, genre=genre, fan_count=fan_count)

    # Notify
    from weeklyamp.notifications.manager import NotificationManager
    NotificationManager(repo).notify_artist_newsletter_signup(artist_name)

    # If billing is active, create Manifest checkout for the artist plan
    if config.paid_tiers.enabled and config.artist_newsletters.enabled:
        plan_prices = {"starter": "artist_starter", "growth": "artist_growth", "pro": "artist_pro"}
        price_id = plan_prices.get(plan, "artist_starter")
        from weeklyamp.billing.stripe_client import PaymentClient
        client = PaymentClient(config.paid_tiers)
        checkout_url = client.create_checkout_session(
            price_id=price_id,
            customer_email=email,
            success_url=f"{config.site_domain}/admin/artist-newsletters/{newsletter_id}",
            cancel_url=f"{config.site_domain}/artist-newsletters",
            metadata={"newsletter_id": str(newsletter_id), "artist_name": artist_name, "plan": plan},
        )
        if checkout_url:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(checkout_url, status_code=303)

    return HTMLResponse(f'<div style="padding:40px;text-align:center;"><h2 style="color:#10b981;">Welcome, {artist_name}!</h2><p style="color:#9ca3af;font-size:18px;">Your newsletter is being set up. We\'ll email you at {email} with your dashboard login within 24 hours.</p><p style="margin-top:20px;"><a href="/n/{slug}" style="color:#e8645a;">Preview your subscribe page &rarr;</a></p></div>')

@router.get("/admin/artist-newsletters", response_class=HTMLResponse)
async def admin_page(request: Request):
    repo = get_repo()
    waitlist = repo.get_artist_newsletter_waitlist()
    return HTMLResponse(render("admin_artist_newsletters.html", waitlist=waitlist))

@router.post("/admin/artist-newsletters/{entry_id}/status", response_class=HTMLResponse)
async def update_status(entry_id: int, request: Request, status: str = Form(...)):
    repo = get_repo()
    repo.update_waitlist_status(entry_id, status)
    return HTMLResponse(f'<span class="badge badge-info">{status}</span>')

@router.get("/admin/artist-newsletters/{newsletter_id}", response_class=HTMLResponse)
async def newsletter_dashboard(newsletter_id: int, request: Request):
    repo = get_repo()
    config = get_config()
    newsletter = repo.get_artist_newsletter(newsletter_id)
    if not newsletter:
        return HTMLResponse("Newsletter not found", status_code=404)
    sub_count = repo.get_artist_nl_subscriber_count(newsletter_id)
    subscribers = repo.get_artist_nl_subscribers(newsletter_id, limit=50)
    issues = repo.get_artist_nl_issues(newsletter_id)
    templates = repo.get_artist_nl_templates()
    links = repo.get_artist_nl_links(newsletter_id)
    revenue = repo.get_artist_nl_revenue(newsletter_id)
    revenue_total = repo.get_artist_nl_revenue_total(newsletter_id)
    return HTMLResponse(render("artist_newsletter_dashboard.html",
        newsletter=newsletter, sub_count=sub_count, subscribers=subscribers,
        issues=issues, templates=templates, links=links,
        revenue=revenue, revenue_total=revenue_total, config=config))

@router.post("/admin/artist-newsletters/{newsletter_id}/link", response_class=HTMLResponse)
async def add_link(newsletter_id: int, request: Request, link_type: str = Form(...), label: str = Form(...), url: str = Form(...)):
    repo = get_repo()
    repo.add_artist_nl_link(newsletter_id, link_type, label, url)
    return HTMLResponse(f'<div class="alert alert-success">Link "{label}" added.</div>')

@router.post("/admin/artist-newsletters/link/{link_id}/delete", response_class=HTMLResponse)
async def delete_link(link_id: int, request: Request):
    repo = get_repo()
    repo.delete_artist_nl_link(link_id)
    return HTMLResponse('<div class="alert alert-success">Link removed.</div>')

@router.post("/admin/artist-newsletters/create", response_class=HTMLResponse)
async def create_newsletter(request: Request, artist_name: str = Form(...), slug: str = Form(...), brand_color: str = Form("#e8645a"), tagline: str = Form(""), template_style: str = Form("minimal")):
    repo = get_repo()
    newsletter_id = repo.create_artist_newsletter(artist_name, slug, brand_color=brand_color, tagline=tagline, template_style=template_style)
    return HTMLResponse(f'<div class="alert alert-success">Newsletter created! <a href="/admin/artist-newsletters/{newsletter_id}">Open Dashboard</a></div>')

@router.post("/admin/artist-newsletters/{newsletter_id}/update", response_class=HTMLResponse)
async def update_newsletter(newsletter_id: int, request: Request, brand_color: str = Form(""), tagline: str = Form(""), template_style: str = Form("")):
    repo = get_repo()
    kwargs = {}
    if brand_color:
        kwargs["brand_color"] = brand_color
    if tagline:
        kwargs["tagline"] = tagline
    if template_style:
        kwargs["template_style"] = template_style
    if kwargs:
        repo.update_artist_newsletter(newsletter_id, **kwargs)
    return HTMLResponse('<div class="alert alert-success">Newsletter updated.</div>')

@router.post("/admin/artist-newsletters/{newsletter_id}/issue", response_class=HTMLResponse)
async def create_issue(newsletter_id: int, request: Request, subject: str = Form(...), content: str = Form("")):
    repo = get_repo()
    issue_id = repo.create_artist_nl_issue(newsletter_id, subject, html_content=content)
    return HTMLResponse(f'<div class="alert alert-success">Issue created (ID: {issue_id}).</div>')

# Public subscribe page for artist newsletter
@router.get("/n/{slug}", response_class=HTMLResponse)
async def artist_newsletter_public(slug: str, request: Request):
    repo = get_repo()
    newsletter = repo.get_artist_newsletter_by_slug(slug)
    if not newsletter:
        return HTMLResponse("Newsletter not found", status_code=404)
    sub_count = repo.get_artist_nl_subscriber_count(newsletter["id"])
    return HTMLResponse(render("artist_newsletter_subscribe.html", newsletter=newsletter, sub_count=sub_count))

@router.post("/n/{slug}/subscribe", response_class=HTMLResponse)
async def artist_newsletter_subscribe(slug: str, request: Request, email: str = Form(...), first_name: str = Form("")):
    repo = get_repo()
    newsletter = repo.get_artist_newsletter_by_slug(slug)
    if not newsletter:
        return HTMLResponse("Newsletter not found", status_code=404)
    repo.add_artist_nl_subscriber(newsletter["id"], email, first_name)
    return HTMLResponse('<div style="padding:24px;text-align:center;color:#10b981;font-size:18px;font-weight:600;">You\'re subscribed! Welcome aboard.</div>')


# ---- Artist CRM (Unified Dashboard) ----

@router.get("/admin/artist-crm/{newsletter_id}", response_class=HTMLResponse)
async def artist_crm(newsletter_id: int, request: Request):
    """Unified Artist CRM — newsletter + merch + events + streaming + fan comms."""
    repo = get_repo()
    config = get_config()

    newsletter = repo.get_artist_newsletter(newsletter_id)
    if not newsletter:
        return HTMLResponse("Newsletter not found", status_code=404)

    # Newsletter data
    sub_count = repo.get_artist_nl_subscriber_count(newsletter_id)
    subscribers = repo.get_artist_nl_subscribers(newsletter_id, limit=50)
    issues = repo.get_artist_nl_issues(newsletter_id)
    links = repo.get_artist_nl_links(newsletter_id)
    revenue = repo.get_artist_nl_revenue(newsletter_id)
    revenue_total = repo.get_artist_nl_revenue_total(newsletter_id)

    # Artist profile data (if linked)
    artist_profile = None
    spotify_data = None
    if newsletter.get("artist_profile_id"):
        conn = repo._conn()
        ap = conn.execute("SELECT * FROM artist_profiles WHERE id = ?", (newsletter["artist_profile_id"],)).fetchone()
        if ap:
            artist_profile = dict(ap)
            # Get Spotify data if available
            if ap.get("spotify_id") and config.spotify.enabled:
                sp = conn.execute("SELECT * FROM spotify_artist_cache WHERE spotify_id = ?", (ap["spotify_id"],)).fetchone()
                if sp:
                    spotify_data = dict(sp)
        conn.close()

    # Events (if any linked to this artist's edition)
    conn = repo._conn()
    events = conn.execute(
        "SELECT * FROM events WHERE status IN ('published', 'draft') ORDER BY event_date DESC LIMIT 10"
    ).fetchall()
    conn.close()

    # Invoices
    invoices = repo.get_invoices(entity_type="artist_newsletter", entity_id=newsletter_id)

    return HTMLResponse(render("artist_crm.html",
        newsletter=newsletter, sub_count=sub_count, subscribers=subscribers,
        issues=issues, links=links, revenue=revenue, revenue_total=revenue_total,
        artist_profile=artist_profile, spotify_data=spotify_data,
        events=[dict(e) for e in events], invoices=invoices, config=config))
