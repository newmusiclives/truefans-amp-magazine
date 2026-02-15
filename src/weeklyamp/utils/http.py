"""Shared HTTP client with retries and sensible defaults."""

from __future__ import annotations

import httpx

_DEFAULT_TIMEOUT = 30.0
_DEFAULT_HEADERS = {
    "User-Agent": "WEEKLYAMP/0.1 (newsletter research bot; +https://github.com/weeklyamp)"
}


def get_client(**kwargs) -> httpx.Client:
    """Return a configured httpx.Client."""
    return httpx.Client(
        timeout=kwargs.pop("timeout", _DEFAULT_TIMEOUT),
        headers={**_DEFAULT_HEADERS, **kwargs.pop("headers", {})},
        follow_redirects=True,
        **kwargs,
    )


def fetch_url(url: str, **kwargs) -> httpx.Response:
    """Fetch a URL with retries. Raises on failure after retries."""
    max_retries = kwargs.pop("max_retries", 2)
    client = get_client(**kwargs)
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            resp = client.get(url)
            resp.raise_for_status()
            return resp
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            last_exc = exc
            if attempt == max_retries:
                break
    client.close()
    raise last_exc
