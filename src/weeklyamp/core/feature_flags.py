"""Feature flag system.

Flags resolve in this order (highest priority first):

1. Row in the ``feature_flags`` DB table — runtime-mutable via the
   admin UI at ``/admin/feature-flags``. This is the "rapid rollout"
   path: flip a flag, next request sees the new value.
2. Default in ``config/default.yaml`` under the ``features:`` block —
   the baseline each deploy starts with.
3. Hardcoded ``False`` — safety net if both DB and config miss.

The DB lookup result is cached in-process until :func:`invalidate_cache`
is called (which the admin-UI write path does on every toggle).

Canonical flag names live in :class:`FeatureFlag` so typos fail at
import time instead of silently resolving to the hardcoded ``False``.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class FeatureFlag:
    """Canonical feature flag names. Use these constants, not raw strings."""

    # Revenue
    PAID_TIERS = "paid_tiers"
    WHITE_LABEL = "white_label"
    FRANCHISE = "franchise"
    ADVERTISERS = "advertisers"
    MARKETPLACE = "marketplace"

    # Content
    AUDIO = "audio"
    PODCAST = "podcast"
    CONTESTS = "contests"
    TRIVIA = "trivia"
    USER_SUBMISSIONS = "user_submissions"

    # Engagement
    WELCOME_SEQUENCE = "welcome_sequence"
    REENGAGEMENT = "reengagement"
    REFERRALS = "referrals"
    COMMUNITY = "community"
    AB_TESTING = "ab_testing"
    EVENTS = "events"
    CROSS_PROMO = "cross_promo"

    # Integrations
    SPOTIFY = "spotify"
    WEBHOOKS_INBOUND = "webhooks_inbound"
    API_V2 = "api_v2"
    GDPR_EXPORT = "gdpr_export"

    # Internal tooling
    CALENDAR_REBOOK = "calendar_rebook"
    COHORT_RETENTION = "cohort_retention"
    SECTION_HEATMAP = "section_heatmap"


# Group metadata for the admin UI (key → (label, category, description)).
# Adding a flag here makes it show up in /admin/feature-flags automatically.
FLAG_METADATA: dict[str, tuple[str, str, str]] = {
    FeatureFlag.PAID_TIERS: ("Paid tiers", "Revenue", "Subscription billing via Manifest Financial"),
    FeatureFlag.WHITE_LABEL: ("White-label", "Revenue", "Custom domain/branding per licensee"),
    FeatureFlag.FRANCHISE: ("Franchise / city licensing", "Revenue", "Territory-exclusive city licensees"),
    FeatureFlag.ADVERTISERS: ("Advertiser portal", "Revenue", "Self-serve ad buying + ad campaigns"),
    FeatureFlag.MARKETPLACE: ("Marketplace", "Revenue", "Creator marketplace for cross-promotion"),
    FeatureFlag.AUDIO: ("Audio newsletter", "Content", "TTS audio version of each edition"),
    FeatureFlag.PODCAST: ("Podcast generation", "Content", "Podcast feed from newsletter content"),
    FeatureFlag.CONTESTS: ("Contests / giveaways", "Content", "Reader contests + entry tracking"),
    FeatureFlag.TRIVIA: ("Trivia / leaderboard", "Content", "Trivia questions + public leaderboard"),
    FeatureFlag.USER_SUBMISSIONS: ("User submissions", "Content", "Reader-submitted content pipeline"),
    FeatureFlag.WELCOME_SEQUENCE: ("Welcome sequence", "Engagement", "Drip emails for new subscribers"),
    FeatureFlag.REENGAGEMENT: ("Re-engagement", "Engagement", "Win-back emails for inactive readers"),
    FeatureFlag.REFERRALS: ("Referrals", "Engagement", "Subscriber referral rewards"),
    FeatureFlag.COMMUNITY: ("Community forum", "Engagement", "Subscriber-only discussion forum"),
    FeatureFlag.AB_TESTING: ("A/B subject testing", "Engagement", "Split-test subject lines"),
    FeatureFlag.EVENTS: ("Events", "Engagement", "Event registration + public event listing"),
    FeatureFlag.CROSS_PROMO: ("Cross-promotion", "Engagement", "Partner newsletter swaps"),
    FeatureFlag.SPOTIFY: ("Spotify integration", "Integrations", "Pull artist data from Spotify"),
    FeatureFlag.WEBHOOKS_INBOUND: ("Inbound webhooks", "Integrations", "Accept webhook POSTs from external systems"),
    FeatureFlag.API_V2: ("Public API v2", "Integrations", "API-key-authenticated JSON API"),
    FeatureFlag.GDPR_EXPORT: ("GDPR data export", "Integrations", "Subscriber data export endpoint"),
    FeatureFlag.CALENDAR_REBOOK: ("Calendar reschedule", "Internal", "Drag-and-drop edition reschedule UI"),
    FeatureFlag.COHORT_RETENTION: ("Cohort retention", "Internal", "Subscriber cohort analysis dashboard"),
    FeatureFlag.SECTION_HEATMAP: ("Section heatmap", "Internal", "Per-section engagement heatmap"),
}


# Launch Set — the ten flags recommended ON for the minimum-viable public
# launch. Rendered as a pinned group at the top of /admin/feature-flags so
# operators can confirm/toggle them without scrolling past the full list.
# Membership here is a UI-only signal; it does not change a flag's default
# or behavior.
LAUNCH_SET: tuple[str, ...] = (
    FeatureFlag.WELCOME_SEQUENCE,
    FeatureFlag.REENGAGEMENT,
    FeatureFlag.REFERRALS,
    FeatureFlag.AB_TESTING,
    FeatureFlag.CROSS_PROMO,
    FeatureFlag.WEBHOOKS_INBOUND,
    FeatureFlag.GDPR_EXPORT,
    FeatureFlag.SECTION_HEATMAP,
    FeatureFlag.COHORT_RETENTION,
    FeatureFlag.CALENDAR_REBOOK,
)


# ---- In-process cache ----

_cache: dict[str, bool] = {}
_cache_lock = threading.Lock()
_config_defaults: dict[str, bool] = {}


def set_config_defaults(defaults: dict[str, bool]) -> None:
    """Call at app startup with the parsed `features:` block from
    config/default.yaml. Subsequent :func:`enabled` calls fall back to
    these values when no DB row exists for the flag."""
    global _config_defaults
    _config_defaults = dict(defaults)


def invalidate_cache(key: Optional[str] = None) -> None:
    """Drop the in-process cache for a single flag (on toggle) or all
    flags (on restart/reset). Admin UI calls this after every write."""
    with _cache_lock:
        if key is None:
            _cache.clear()
        else:
            _cache.pop(key, None)


def enabled(name: str, *, repo=None) -> bool:
    """Return True if the named feature flag is on.

    Parameters:
        name: flag name (use :class:`FeatureFlag` constants, not raw strings)
        repo: optional Repository instance. If None, we attempt to get
              one from ``weeklyamp.web.deps.get_repo`` — this lets route
              handlers call ``enabled(FeatureFlag.PAID_TIERS)`` without
              plumbing a repo through every dependency.
    """
    with _cache_lock:
        cached = _cache.get(name)
    if cached is not None:
        return cached

    # 1. DB override
    if repo is None:
        try:
            from weeklyamp.web.deps import get_repo
            repo = get_repo()
        except Exception:
            logger.debug("could not acquire repo for flag lookup: %s", name)
            repo = None

    if repo is not None:
        try:
            db_value = repo.get_feature_flag(name)
        except Exception:
            logger.debug("DB lookup failed for flag %s", name, exc_info=True)
            db_value = None
        if db_value is not None:
            with _cache_lock:
                _cache[name] = db_value
            return db_value

    # 2. Config default
    default = _config_defaults.get(name, False)
    with _cache_lock:
        _cache[name] = default
    return default


def require_feature(flag_name: str):
    """FastAPI dependency that 404s when the named flag is off.

    Usage::

        from weeklyamp.core.feature_flags import require_feature, FeatureFlag

        @router.get("/pricing", dependencies=[Depends(require_feature(FeatureFlag.PAID_TIERS))])
        async def pricing_page(): ...

    We return 404 rather than 403 so the feature is indistinguishable
    from "endpoint doesn't exist" — no info leak to anonymous probers
    about what features exist behind the flag.
    """
    from fastapi import HTTPException

    async def _check() -> None:
        if not enabled(flag_name):
            raise HTTPException(status_code=404)

    return _check


def seed_from_config(repo, config_features: dict[str, bool]) -> None:
    """Write any missing flags to the DB with their config defaults.

    Called once at app startup. Idempotent — existing rows are not
    overwritten. Ensures the admin UI always has a complete list of
    flags to toggle, even for features added in a new release.
    """
    for key, default_value in config_features.items():
        try:
            if repo.get_feature_flag(key) is None:
                meta = FLAG_METADATA.get(key, (key, "", ""))
                _label, category, description = meta
                repo.set_feature_flag(key, default_value, description=description, category=category)
        except Exception:
            logger.warning("Failed to seed feature flag %s", key, exc_info=True)
