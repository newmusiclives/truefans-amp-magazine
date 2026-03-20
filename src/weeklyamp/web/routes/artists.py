"""Public artist directory + admin artist management routes."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import HTMLResponse

from weeklyamp.content.artist_profiles import ProfileManager
from weeklyamp.web.deps import get_config, get_repo, render

logger = logging.getLogger(__name__)

router = APIRouter()


def _mgr() -> ProfileManager:
    """Convenience: build a ProfileManager from current config/repo."""
    return ProfileManager(get_repo(), get_config())


# ──────────────────────────────────────────────
# PUBLIC routes (no auth required — /artists prefix is in _PUBLIC_PREFIXES)
# ──────────────────────────────────────────────

@router.get("/artists", response_class=HTMLResponse)
async def artist_directory(search: str = "", genre: str = ""):
    """Public artist directory page with search / genre filter."""
    mgr = _mgr()
    profiles = mgr.get_directory(genre_filter=genre, search=search)
    config = get_config()
    genres = config.genre_preferences.available_genres if config.genre_preferences.enabled else []
    return render(
        "artist_directory.html",
        profiles=profiles,
        search=search,
        genre=genre,
        genres=genres,
        config=config,
    )


@router.get("/artists/edit/{token}", response_class=HTMLResponse)
async def artist_self_edit_form(token: str):
    """Self-service edit form — accessed via unique token link."""
    repo = get_repo()
    profile = repo.get_artist_profile_by_token(token)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return render("artist_edit.html", profile=profile, token=token)


@router.post("/artists/edit/{token}", response_class=HTMLResponse)
async def artist_self_edit_save(
    token: str,
    bio: str = Form(""),
    website: str = Form(""),
    social_links_json: str = Form("{}"),
    image_url: str = Form(""),
):
    """Save self-service edits submitted by the artist."""
    repo = get_repo()
    profile = repo.get_artist_profile_by_token(token)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Validate JSON
    try:
        json.loads(social_links_json)
    except (json.JSONDecodeError, TypeError):
        social_links_json = profile.get("social_links_json", "{}")

    repo.update_artist_profile(
        profile["id"],
        bio=bio,
        website=website,
        social_links_json=social_links_json,
        image_url=image_url,
    )
    # Re-fetch after update
    profile = repo.get_artist_profile_by_token(token)
    return render("artist_edit.html", profile=profile, token=token, saved=True)


@router.get("/artists/{slug}", response_class=HTMLResponse)
async def artist_profile_page(slug: str):
    """Public artist profile page."""
    mgr = _mgr()
    profile = mgr.get_profile_with_details(slug)
    if not profile:
        raise HTTPException(status_code=404, detail="Artist not found")
    config = get_config()
    return render("artist_profile.html", profile=profile, config=config)


@router.post("/artists/{slug}/follow", response_class=HTMLResponse)
async def follow_artist(slug: str, email: str = Form(...)):
    """Follow an artist — requires subscriber email."""
    repo = get_repo()
    profile = repo.get_artist_profile(slug)
    if not profile:
        raise HTTPException(status_code=404, detail="Artist not found")

    subscriber = repo.get_subscriber_by_email(email)
    if not subscriber:
        raise HTTPException(status_code=400, detail="Email not found — subscribe first")

    repo.follow_artist(subscriber["id"], profile["id"])
    count = repo.get_artist_follower_count(profile["id"])
    return HTMLResponse(
        f'<span class="follow-count">{count} follower{"s" if count != 1 else ""}</span>'
        '<span class="follow-success">Followed!</span>'
    )


# ──────────────────────────────────────────────
# ADMIN routes (require authentication)
# ──────────────────────────────────────────────

@router.get("/admin/artists", response_class=HTMLResponse)
async def admin_artists():
    """Admin page: manage all artist profiles."""
    repo = get_repo()
    profiles = repo.get_artist_profiles(published_only=False, limit=200)

    # Augment with follower counts
    for p in profiles:
        p["follower_count"] = repo.get_artist_follower_count(p["id"])

    # Pending submissions for "create from submission" flow
    submissions = repo.get_submissions(review_state="approved")

    return render(
        "admin_artists.html",
        profiles=profiles,
        submissions=submissions,
    )


@router.post("/admin/artists/{profile_id}/approve", response_class=HTMLResponse)
async def approve_profile(profile_id: int):
    """Approve an artist profile."""
    mgr = _mgr()
    mgr.approve_profile(profile_id)
    # Return updated row partial for HTMX swap
    repo = get_repo()
    profiles = repo.get_artist_profiles(published_only=False, limit=200)
    for p in profiles:
        p["follower_count"] = repo.get_artist_follower_count(p["id"])
    submissions = repo.get_submissions(review_state="approved")
    return render("admin_artists.html", profiles=profiles, submissions=submissions, _partial="table")


@router.post("/admin/artists/{profile_id}/publish", response_class=HTMLResponse)
async def publish_profile(profile_id: int):
    """Publish an artist profile (must be approved first)."""
    mgr = _mgr()
    mgr.publish_profile(profile_id)
    repo = get_repo()
    profiles = repo.get_artist_profiles(published_only=False, limit=200)
    for p in profiles:
        p["follower_count"] = repo.get_artist_follower_count(p["id"])
    submissions = repo.get_submissions(review_state="approved")
    return render("admin_artists.html", profiles=profiles, submissions=submissions, _partial="table")


@router.post(
    "/admin/artists/{profile_id}/create-from-submission/{submission_id}",
    response_class=HTMLResponse,
)
async def create_from_submission(profile_id: int, submission_id: int):
    """Create an artist profile from an approved submission.

    Note: ``profile_id`` is 0 when creating new — the real ID is returned by
    the manager.
    """
    mgr = _mgr()
    new_id = mgr.create_from_submission(submission_id)
    if new_id is None:
        raise HTTPException(status_code=400, detail="Could not create profile")

    repo = get_repo()
    profiles = repo.get_artist_profiles(published_only=False, limit=200)
    for p in profiles:
        p["follower_count"] = repo.get_artist_follower_count(p["id"])
    submissions = repo.get_submissions(review_state="approved")
    return render("admin_artists.html", profiles=profiles, submissions=submissions, _partial="table")
