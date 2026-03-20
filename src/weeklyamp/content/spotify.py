"""Spotify Web API client for artist lookups and release tracking."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

import httpx

from weeklyamp.core.models import SpotifyConfig

logger = logging.getLogger(__name__)

TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"


class SpotifyClient:
    """Thin wrapper around the Spotify Web API (Client Credentials flow)."""

    def __init__(self, config: SpotifyConfig) -> None:
        self.config = config
        self._access_token: str = ""
        self._token_expires_at: float = 0.0

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self) -> None:
        """Obtain an access token via the Client Credentials flow.

        Caches the token and its expiry so subsequent calls are free until
        the token expires.
        """
        logger.info("Authenticating with Spotify (client credentials)")
        resp = httpx.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(self.config.client_id, self.config.client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        # Subtract a 60-second buffer so we refresh slightly before expiry
        self._token_expires_at = time.time() + data.get("expires_in", 3600) - 60
        logger.debug("Spotify token acquired, expires in %ss", data.get("expires_in"))

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Make an authenticated request to the Spotify Web API.

        Automatically refreshes the access token when it is expired or
        missing.
        """
        if not self._access_token or time.time() >= self._token_expires_at:
            self.authenticate()

        url = f"{API_BASE}/{path}"
        resp = httpx.request(
            method,
            url,
            params=params,
            headers={"Authorization": f"Bearer {self._access_token}"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def search_artist(self, name: str, limit: int = 5) -> list[dict]:
        """Search Spotify for artists matching *name*.

        Returns a list of cleaned dicts:
            id, name, genres, followers, popularity, image_url
        """
        data = self._request("GET", "search", params={
            "q": name,
            "type": "artist",
            "limit": limit,
        })
        results: list[dict] = []
        for item in data.get("artists", {}).get("items", []):
            images = item.get("images") or []
            results.append({
                "id": item["id"],
                "name": item["name"],
                "genres": item.get("genres", []),
                "followers": item.get("followers", {}).get("total", 0),
                "popularity": item.get("popularity", 0),
                "image_url": images[0]["url"] if images else "",
            })
        return results

    def get_artist(self, spotify_id: str) -> dict:
        """Fetch full artist data for a single Spotify artist ID."""
        item = self._request("GET", f"artists/{spotify_id}")
        images = item.get("images") or []
        return {
            "id": item["id"],
            "name": item["name"],
            "genres": item.get("genres", []),
            "followers": item.get("followers", {}).get("total", 0),
            "popularity": item.get("popularity", 0),
            "image_url": images[0]["url"] if images else "",
            "external_url": item.get("external_urls", {}).get("spotify", ""),
        }

    def get_artist_albums(self, spotify_id: str, limit: int = 20) -> list[dict]:
        """Return the artist's albums and singles."""
        data = self._request(
            "GET",
            f"artists/{spotify_id}/albums",
            params={"include_groups": "album,single", "limit": limit},
        )
        albums: list[dict] = []
        for item in data.get("items", []):
            images = item.get("images") or []
            albums.append({
                "id": item["id"],
                "name": item["name"],
                "release_date": item.get("release_date", ""),
                "album_type": item.get("album_group", item.get("album_type", "album")),
                "total_tracks": item.get("total_tracks", 0),
                "image_url": images[0]["url"] if images else "",
                "external_url": item.get("external_urls", {}).get("spotify", ""),
            })
        return albums

    def get_artist_top_tracks(self, spotify_id: str, market: str = "US") -> list[dict]:
        """Return the artist's top tracks for the given market."""
        data = self._request(
            "GET",
            f"artists/{spotify_id}/top-tracks",
            params={"market": market},
        )
        tracks: list[dict] = []
        for item in data.get("tracks", []):
            images = (item.get("album") or {}).get("images") or []
            tracks.append({
                "id": item["id"],
                "name": item["name"],
                "album_name": (item.get("album") or {}).get("name", ""),
                "duration_ms": item.get("duration_ms", 0),
                "popularity": item.get("popularity", 0),
                "preview_url": item.get("preview_url", ""),
                "image_url": images[0]["url"] if images else "",
                "external_url": item.get("external_urls", {}).get("spotify", ""),
            })
        return tracks

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def cache_artist(self, repo: Any, spotify_data: dict) -> int:
        """Save artist data to the spotify_artist_cache table via the repo."""
        genres = ", ".join(spotify_data.get("genres", []))
        return repo.upsert_spotify_artist(
            spotify_artist_id=spotify_data["id"],
            artist_name=spotify_data["name"],
            genres=genres,
            followers=spotify_data.get("followers", 0),
            popularity=spotify_data.get("popularity", 0),
            image_url=spotify_data.get("image_url", ""),
            data_json=json.dumps(spotify_data),
        )

    def sync_releases(self, repo: Any, spotify_id: str) -> int:
        """Fetch albums from Spotify and upsert them into spotify_releases.

        Returns the number of releases upserted.
        """
        albums = self.get_artist_albums(spotify_id, limit=50)
        for album in albums:
            repo.upsert_spotify_release(
                spotify_artist_id=spotify_id,
                album_id=album["id"],
                album_name=album["name"],
                release_date=album.get("release_date", ""),
                album_type=album.get("album_type", "album"),
                image_url=album.get("image_url", ""),
                external_url=album.get("external_url", ""),
            )
        logger.info("Synced %d releases for artist %s", len(albums), spotify_id)
        return len(albums)
