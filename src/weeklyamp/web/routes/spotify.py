"""Admin Spotify dashboard routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from weeklyamp.web.deps import get_config, get_repo, render

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_client(config):
    """Build a SpotifyClient from config, or None if disabled."""
    if not config.spotify.enabled:
        return None
    from weeklyamp.content.spotify import SpotifyClient
    return SpotifyClient(config.spotify)


@router.get("/", response_class=HTMLResponse)
async def spotify_dashboard():
    """Main Spotify dashboard page."""
    config = get_config()
    repo = get_repo()

    enabled = config.spotify.enabled
    cached_artists: list[dict] = []
    recent_releases: list[dict] = []

    if enabled:
        cached_artists = repo.search_spotify_cache("", limit=50)
        recent_releases = repo.get_recent_releases(limit=20)

    return render(
        "spotify.html",
        enabled=enabled,
        cached_artists=cached_artists,
        recent_releases=recent_releases,
    )


@router.post("/lookup", response_class=HTMLResponse)
async def lookup_artist(query: str = Form("")):
    """HTMX: search Spotify for an artist by name, return partial results."""
    config = get_config()
    client = _get_client(config)

    if not client or not query.strip():
        return HTMLResponse(
            '<div class="alert alert-warning">Spotify integration is not enabled or query is empty.</div>'
        )

    try:
        results = client.search_artist(query.strip(), limit=8)
    except Exception as exc:
        logger.exception("Spotify search failed for %r", query)
        return HTMLResponse(
            f'<div class="alert alert-error">Spotify search failed: {exc}</div>'
        )

    if not results:
        return HTMLResponse(
            '<div style="padding:12px;color:var(--text-dim);">No artists found.</div>'
        )

    rows = ""
    for r in results:
        genres = ", ".join(r.get("genres", [])[:3]) or "-"
        img = r.get("image_url", "")
        img_html = f'<img src="{img}" width="32" height="32" style="border-radius:4px;vertical-align:middle;margin-right:8px;">' if img else ""
        rows += f"""\
<tr>
  <td>{img_html}{r['name']}</td>
  <td>{genres}</td>
  <td>{r['followers']:,}</td>
  <td>{r['popularity']}</td>
  <td>
    <button class="btn btn-primary btn-sm"
            hx-post="/spotify/cache/{r['id']}"
            hx-target="#spotify-message"
            hx-swap="innerHTML">
      Cache
    </button>
  </td>
</tr>"""

    return HTMLResponse(f"""\
<div class="table-wrap">
  <table>
    <thead><tr><th>Artist</th><th>Genres</th><th>Followers</th><th>Popularity</th><th>Actions</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>""")


@router.post("/cache/{spotify_id}", response_class=HTMLResponse)
async def cache_artist(spotify_id: str):
    """Cache or refresh an artist's data from Spotify."""
    config = get_config()
    repo = get_repo()
    client = _get_client(config)

    if not client:
        return HTMLResponse('<span class="badge badge-error">Spotify not enabled</span>')

    try:
        artist_data = client.get_artist(spotify_id)
        client.cache_artist(repo, artist_data)
        release_count = client.sync_releases(repo, spotify_id)
        return HTMLResponse(
            f'<span class="badge badge-success">Cached {artist_data["name"]} + {release_count} releases</span>'
        )
    except Exception as exc:
        logger.exception("Failed to cache artist %s", spotify_id)
        return HTMLResponse(
            f'<span class="badge badge-error">Error: {exc}</span>'
        )


@router.get("/artist/{spotify_id}", response_class=HTMLResponse)
async def artist_detail(spotify_id: str):
    """Detail view of a cached artist and their releases."""
    config = get_config()
    repo = get_repo()

    artist = repo.get_spotify_artist(spotify_id)
    if not artist:
        return HTMLResponse('<div class="alert alert-warning">Artist not found in cache.</div>')

    # Fetch releases for this artist
    all_releases = repo.get_recent_releases(limit=200)
    artist_releases = [r for r in all_releases if r.get("spotify_artist_id") == spotify_id]

    # Attempt to get top tracks if Spotify is enabled
    top_tracks: list[dict] = []
    client = _get_client(config)
    if client:
        try:
            top_tracks = client.get_artist_top_tracks(spotify_id)
        except Exception:
            logger.warning("Could not fetch top tracks for %s", spotify_id)

    return render(
        "spotify.html",
        enabled=config.spotify.enabled,
        cached_artists=[],
        recent_releases=[],
        detail_artist=artist,
        artist_releases=artist_releases,
        top_tracks=top_tracks,
    )
