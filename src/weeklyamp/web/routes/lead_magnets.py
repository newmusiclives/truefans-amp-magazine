"""Lead magnet routes — public download pages and admin management."""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from weeklyamp.content.lead_magnets import LeadMagnetManager
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


def _get_manager():
    repo = get_repo()
    config = get_config()
    return LeadMagnetManager(repo, config.lead_magnets), repo


# ---- PUBLIC ----

@router.get("/resources", response_class=HTMLResponse)
async def resources_page():
    """Public: list all available lead magnets."""
    mgr, repo = _get_manager()
    magnets = mgr.get_active_magnets()
    editions = repo.get_editions(active_only=True)

    return render("resources.html",
        magnets=magnets,
        editions=editions,
    )


@router.get("/resources/{slug}", response_class=HTMLResponse)
async def magnet_landing(slug: str):
    """Public: individual lead magnet landing page."""
    mgr, repo = _get_manager()
    magnet = mgr.get_magnet_by_slug(slug)
    if not magnet:
        return HTMLResponse("Not found", status_code=404)

    editions = repo.get_editions(active_only=True)

    return render("lead_magnet_landing.html",
        magnet=magnet,
        editions=editions,
    )


@router.post("/resources/{slug}/download", response_class=HTMLResponse)
async def download_magnet(
    slug: str,
    email: str = Form(...),
    subscribe: str = Form(""),
):
    """Public: email gate — collect email, auto-subscribe, redirect to download."""
    mgr, repo = _get_manager()
    file_url = mgr.record_download(slug, email)

    if not file_url:
        return HTMLResponse("Resource not found", status_code=404)

    # If they opted into subscription via checkbox
    if subscribe:
        magnet = mgr.get_magnet_by_slug(slug)
        if magnet and magnet.get("edition_slug"):
            try:
                repo.subscribe_to_editions(
                    email=email,
                    edition_slugs=[magnet["edition_slug"]],
                    source_channel="lead_magnet",
                )
            except Exception:
                pass

    return RedirectResponse(url=file_url, status_code=303)


# ---- ADMIN ----

@router.get("/admin/lead-magnets", response_class=HTMLResponse)
async def admin_magnets_page():
    """Admin: manage lead magnets."""
    mgr, repo = _get_manager()
    magnets = mgr.get_all_magnets()
    editions = repo.get_editions(active_only=True)

    return render("admin_lead_magnets.html",
        magnets=magnets,
        editions=editions,
    )


@router.post("/admin/lead-magnets/create", response_class=HTMLResponse)
async def create_magnet(
    title: str = Form(...),
    slug: str = Form(""),
    description: str = Form(""),
    edition_slug: str = Form(""),
    file_url: str = Form(...),
    cover_image_url: str = Form(""),
):
    """Admin: create a new lead magnet."""
    mgr, repo = _get_manager()

    try:
        mgr.create_magnet(
            title=title,
            slug=slug,
            description=description,
            edition_slug=edition_slug,
            file_url=file_url,
            cover_image_url=cover_image_url,
        )
        message = f"Created lead magnet: {title}"
        level = "success"
    except Exception as exc:
        message = f"Failed: {exc}"
        level = "error"

    magnets = mgr.get_all_magnets()
    editions = repo.get_editions(active_only=True)

    return render("admin_lead_magnets.html",
        magnets=magnets,
        editions=editions,
        message=message,
        level=level,
    )
