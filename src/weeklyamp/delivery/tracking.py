"""Email open/click tracking injection for newsletter delivery."""

from __future__ import annotations

import base64
import logging
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from weeklyamp.core.models import TrackingConfig

logger = logging.getLogger(__name__)


class TrackingProcessor:
    """Injects open/click tracking pixels and link redirects into HTML emails.

    All tracking features are gated behind config flags and are disabled
    by default.  When disabled, methods return the input HTML unchanged.
    """

    def __init__(self, config: TrackingConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Open + click tracking
    # ------------------------------------------------------------------

    def inject_tracking(
        self,
        html_body: str,
        issue_id: int,
        subscriber_id: int,
        site_domain: str,
    ) -> str:
        """Rewrite *html_body* to include open-tracking pixel and click redirects.

        * Open tracking: adds a 1x1 transparent GIF ``<img>`` before ``</body>``.
        * Click tracking: rewrites every ``<a href="...">`` to route through a
          redirect endpoint that records the click event.

        Args:
            html_body: Raw newsletter HTML.
            issue_id: Database ID of the current issue.
            subscriber_id: Database ID of the recipient.
            site_domain: Base URL for tracking endpoints
                (e.g. ``https://truefansnewsletters.com``).

        Returns:
            Modified HTML with tracking injected, or the original HTML if
            both tracking options are disabled.
        """
        domain = site_domain.rstrip("/")

        # --- Open tracking ---
        if self.config.open_tracking:
            pixel_url = f"{domain}/t/open/{issue_id}/{subscriber_id}.gif"
            pixel_tag = (
                f'<img src="{pixel_url}" width="1" height="1" '
                f'alt="" style="display:none;border:0;" />'
            )
            # Insert just before </body>, or append if no closing tag
            if "</body>" in html_body.lower():
                html_body = re.sub(
                    r"(</body>)",
                    f"{pixel_tag}\\1",
                    html_body,
                    count=1,
                    flags=re.IGNORECASE,
                )
            else:
                html_body += pixel_tag
            logger.debug(
                "Open tracking pixel injected for issue=%s subscriber=%s",
                issue_id,
                subscriber_id,
            )

        # --- Click tracking ---
        if self.config.click_tracking:
            def _rewrite_link(match: re.Match) -> str:
                original_url = match.group(1)
                # Skip mailto:, tel:, and anchor-only links
                if original_url.startswith(("mailto:", "tel:", "#", "{{", "{%")):
                    return match.group(0)
                # Skip unsubscribe links — those must remain direct
                if "/unsubscribe" in original_url:
                    return match.group(0)
                encoded = base64.urlsafe_b64encode(
                    original_url.encode("utf-8")
                ).decode("ascii")
                redirect_url = (
                    f"{domain}/t/click/{issue_id}/{subscriber_id}"
                    f"?url={encoded}"
                )
                return match.group(0).replace(original_url, redirect_url)

            html_body = re.sub(
                r'<a\s[^>]*href=["\']([^"\']+)["\']',
                _rewrite_link,
                html_body,
                flags=re.IGNORECASE,
            )
            logger.debug(
                "Click tracking injected for issue=%s subscriber=%s",
                issue_id,
                subscriber_id,
            )

        return html_body

    # ------------------------------------------------------------------
    # UTM parameter injection
    # ------------------------------------------------------------------

    def inject_utm_params(
        self,
        html_body: str,
        utm_source: str,
        utm_medium: str,
        utm_campaign: str,
    ) -> str:
        """Append UTM query parameters to all external links in *html_body*.

        Only ``http://`` and ``https://`` links are modified.  Internal
        tracking redirects (``/t/click/...``) and unsubscribe links are
        skipped so they are not double-tagged.

        Args:
            html_body: Newsletter HTML.
            utm_source: Value for ``utm_source``.
            utm_medium: Value for ``utm_medium``.
            utm_campaign: Value for ``utm_campaign``.

        Returns:
            HTML with UTM parameters appended to qualifying links.
        """
        utm_params = {
            "utm_source": utm_source,
            "utm_medium": utm_medium,
            "utm_campaign": utm_campaign,
        }

        def _add_utm(match: re.Match) -> str:
            original_url = match.group(1)
            # Only tag external http(s) links
            if not original_url.startswith(("http://", "https://")):
                return match.group(0)
            # Skip tracking redirect links and unsubscribe
            if "/t/click/" in original_url or "/unsubscribe" in original_url:
                return match.group(0)
            parsed = urlparse(original_url)
            existing_params = parse_qs(parsed.query, keep_blank_values=True)
            # Don't overwrite existing UTM params
            for key, value in utm_params.items():
                if key not in existing_params:
                    existing_params[key] = [value]
            new_query = urlencode(
                {k: v[0] for k, v in existing_params.items()},
                doseq=False,
            )
            new_url = urlunparse(parsed._replace(query=new_query))
            return match.group(0).replace(original_url, new_url)

        html_body = re.sub(
            r'<a\s[^>]*href=["\']([^"\']+)["\']',
            _add_utm,
            html_body,
            flags=re.IGNORECASE,
        )
        logger.debug("UTM params injected: source=%s campaign=%s", utm_source, utm_campaign)
        return html_body
