"""White-label domain routing middleware.

Maps custom domains to specific newsletter editions for white-label SaaS support.
INACTIVE by default — requires white_label.enabled=true.
"""

from __future__ import annotations

import logging
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class DomainRoutingMiddleware(BaseHTTPMiddleware):
    """Route requests to edition-specific content based on Host header.

    When a custom domain is configured for an edition (e.g., nashville.truefansnewsletters.com
    or nashvillemusic.com), this middleware sets the edition context on the request state
    so that templates render with the edition's branding.
    """

    def __init__(self, app, config=None):
        super().__init__(app)
        self.config = config
        self._domain_cache: dict[str, dict] = {}
        self._cache_built = False

    def _build_cache(self) -> None:
        """Build domain → edition mapping from database."""
        if self._cache_built or not self.config:
            return
        if not self.config.white_label.enabled:
            self._cache_built = True
            return
        try:
            from weeklyamp.web.deps import get_repo
            repo = get_repo()
            conn = repo._conn()
            rows = conn.execute(
                "SELECT slug, custom_domain, custom_logo_url, custom_css, custom_footer_html "
                "FROM newsletter_editions WHERE custom_domain != ''"
            ).fetchall()
            conn.close()
            for row in rows:
                domain = row["custom_domain"].lower().strip()
                if domain:
                    self._domain_cache[domain] = dict(row)
            self._cache_built = True
            logger.info("Domain routing cache built: %d custom domains", len(self._domain_cache))
        except Exception:
            logger.exception("Failed to build domain routing cache")

    def _lookup_edition(self, host: str) -> Optional[dict]:
        """Look up edition by Host header."""
        self._build_cache()
        host = host.lower().split(":")[0]  # strip port
        return self._domain_cache.get(host)

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self.config or not self.config.white_label.enabled:
            return await call_next(request)

        host = request.headers.get("host", "")
        edition = self._lookup_edition(host)
        if edition:
            request.state.white_label_edition = edition
            request.state.custom_logo_url = edition.get("custom_logo_url", "")
            request.state.custom_css = edition.get("custom_css", "")
            request.state.custom_footer_html = edition.get("custom_footer_html", "")
        else:
            request.state.white_label_edition = None

        return await call_next(request)
