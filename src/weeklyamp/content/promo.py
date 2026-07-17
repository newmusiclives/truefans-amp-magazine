"""Ecosystem cross-sell promo block.

Routes each edition's readers to the right next step in the TrueFans
ecosystem — AMP (paid monthly editorial), RISE (free artist Crew), or the
EDGE waitlist — as a single positioned CTA injected into every assembled
edition. See :class:`weeklyamp.core.models.PromoConfig`.

The block is config-driven and disabled by default. It is deliberately a
thin, self-contained unit so licensee/city editions inherit it for free
(they run through the same assembly path) and so per-target destination
URLs and copy can be tuned without touching the render pipeline.
"""

from __future__ import annotations

import base64
import json
import logging
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from weeklyamp.core.models import PromoConfig, PromoTarget

logger = logging.getLogger(__name__)

# Admin-editable overlay is stored as a JSON blob under this key so promo
# copy/routing/targets can be changed at runtime without a deploy.
PROMO_SETTINGS_KEY = "promo_config"

# Fields an admin may override at runtime. `enabled` is handled separately
# so the env kill-switch always wins.
_OVERRIDABLE = ("position", "track_clicks", "utm_source", "utm_medium",
                "routing", "default_target", "targets")


def effective_promo_config(repo, base: PromoConfig, env_forced: bool = False) -> PromoConfig:
    """Overlay any admin_settings promo override on top of the base config.

    The base already reflects YAML + the ``WEEKLYAMP_PROMO_ENABLED`` env
    toggle. A stored JSON override can change copy/routing/targets and may
    also flip ``enabled`` — but ``env_forced`` (the env kill-switch) always
    wins so ops can force-enable regardless of the stored value.
    """
    try:
        raw = repo.get_admin_setting(PROMO_SETTINGS_KEY)
    except Exception:
        logger.exception("Failed to read promo config override")
        return base
    if not raw:
        return base
    try:
        override = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("Ignoring malformed promo_config override")
        return base

    data = base.model_dump()
    for field in _OVERRIDABLE:
        if field in override:
            data[field] = override[field]
    if "enabled" in override:
        data["enabled"] = bool(override["enabled"])
    if env_forced:
        data["enabled"] = True
    try:
        return PromoConfig(**data)
    except Exception:
        logger.exception("Invalid promo config override; using base")
        return base


def _append_utm(url: str, params: dict[str, str]) -> str:
    """Append UTM params to *url* without clobbering existing query params."""
    parsed = urlparse(url)
    existing = parse_qs(parsed.query, keep_blank_values=True)
    for key, value in params.items():
        if value and key not in existing:
            existing[key] = [value]
    new_query = urlencode({k: vals[0] for k, vals in existing.items()})
    return urlunparse(parsed._replace(query=new_query))


def resolve_promo_target(
    config: PromoConfig, edition_slug: str, audience: str = ""
) -> tuple[str, PromoTarget] | None:
    """Pick the promo target for an edition.

    Resolution order: the routed target for this edition, then
    ``default_target`` as a fallback (so an edition routed to a target
    whose URL isn't live yet — e.g. RISE before its Crew page ships — still
    shows a usable CTA instead of nothing). Returns ``(key, target)`` or
    ``None`` when the block is disabled or no candidate has a URL.
    """
    if not config.enabled:
        return None

    routed = ""
    for candidate in (edition_slug, audience):
        if candidate and candidate in config.routing:
            routed = config.routing[candidate]
            break

    for key in (routed or config.default_target, config.default_target):
        target = config.targets.get(key)
        if target and target.url:
            return key, target
    return None


def _wrap_click(click_base: str, target_key: str, edition_slug: str, dest_url: str) -> str:
    """Wrap *dest_url* in a first-party ``/t/promo`` redirect for click logging.

    The destination (with its UTM params intact) is base64-encoded, so the
    landing page still receives full UTM attribution after the redirect.
    """
    encoded = base64.urlsafe_b64encode(dest_url.encode()).decode()
    query = urlencode({"t": target_key, "e": edition_slug or "", "url": encoded})
    return f"{click_base.rstrip('/')}/t/promo?{query}"


def build_promo_block(
    config: PromoConfig,
    edition_slug: str,
    audience: str = "",
    campaign: str = "",
    click_base: str = "",
) -> dict | None:
    """Build the promo block for an edition.

    Returns a dict ``{"position", "html", "plain", "target"}`` ready for
    injection into the assembled sections, or ``None`` when the block is
    disabled, unmapped, or the resolved target has no URL yet.

    When ``click_base`` is set (a site origin), the CTA is wrapped in a
    ``/t/promo`` redirect for first-party click logging; UTM params are
    preserved on the final destination either way.
    """
    resolved = resolve_promo_target(config, edition_slug, audience)
    if not resolved:
        return None
    key, target = resolved

    utm = {
        "utm_source": config.utm_source,
        "utm_medium": config.utm_medium,
        "utm_campaign": campaign or edition_slug or "dispatch",
        "utm_content": key,
    }
    dest_url = _append_utm(target.url, utm)
    cta_url = _wrap_click(click_base, key, edition_slug, dest_url) if click_base else dest_url

    # Imported here to avoid a circular import at module load time
    # (templates -> sanitize, but promo -> templates -> ...).
    from weeklyamp.delivery.templates import render_promo_block

    html = render_promo_block(target, cta_url)
    plain = (
        f"--- {(target.label or target.headline).upper()} ---\n"
        f"{target.headline}\n{target.cta_text}: {dest_url}\n"
    )
    position = config.position if config.position in ("top", "mid", "bottom") else "bottom"
    return {"position": position, "html": html, "plain": plain, "target": key}
