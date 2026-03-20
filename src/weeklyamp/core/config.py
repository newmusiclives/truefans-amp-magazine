"""Configuration loader: YAML files + environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

from weeklyamp.core.models import (
    ABTestConfig,
    AgentsConfig,
    AIConfig,
    AIProvider,
    AnalyticsConfig,
    AppConfig,
    DeliverabilityConfig,
    GHLConfig,
    EmailConfig,
    NewsletterConfig,
    RateLimitConfig,
    ReengagementConfig,
    ReferralConfig,
    RolesConfig,
    ScheduleConfig,
    SchedulerConfig,
    SponsorSlotsConfig,
    ArtistProfilesConfig,
    ContestsConfig,
    GenrePreferencesConfig,
    LeadMagnetsConfig,
    ReaderContentConfig,
    SectionEngagementConfig,
    SpotifyConfig,
    SponsorPortalConfig,
    SubmissionsConfig,
    TrackingConfig,
    TriviaPollsConfig,
    WebhookConfig,
    WelcomeSequenceConfig,
)

# Project root is 3 levels up from this file (src/weeklyamp/core/config.py)
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
_CONFIG_DIR = _PROJECT_ROOT / "config"


def _find_project_root() -> Path:
    """Walk up from cwd to find a directory containing pyproject.toml."""
    cwd = Path.cwd()
    for p in [cwd, *cwd.parents]:
        if (p / "pyproject.toml").exists():
            return p
    return cwd


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """Load configuration from YAML + environment variables.

    Priority: env vars > .env file > YAML defaults.
    """
    root = _find_project_root()
    load_dotenv(root / ".env")

    # Load YAML
    yaml_path = Path(config_path) if config_path else root / "config" / "default.yaml"
    yaml_data: dict = {}
    if yaml_path.exists():
        with open(yaml_path) as f:
            yaml_data = yaml.safe_load(f) or {}

    # Build newsletter config
    nl_data = yaml_data.get("newsletter", {})
    newsletter = NewsletterConfig(**nl_data)

    # Build AI config with env overrides
    ai_data = yaml_data.get("ai", {})
    provider_str = os.getenv("WEEKLYAMP_AI_PROVIDER", ai_data.get("provider", "anthropic"))
    ai = AIConfig(
        provider=AIProvider(provider_str),
        model=os.getenv("WEEKLYAMP_AI_MODEL", ai_data.get("model", "claude-sonnet-4-5-20250929")),
        max_tokens=int(ai_data.get("max_tokens", 2000)),
        temperature=float(ai_data.get("temperature", 0.7)),
    )

    # Build GoHighLevel config with env overrides
    ghl_data = yaml_data.get("ghl", {})
    ghl = GHLConfig(
        api_key=os.getenv("GHL_API_KEY", ghl_data.get("api_key", "")),
        location_id=os.getenv("GHL_LOCATION_ID", ghl_data.get("location_id", "")),
        edition_tags=ghl_data.get("edition_tags", {
            "fan": "newsletter-fan",
            "artist": "newsletter-artist",
            "industry": "newsletter-industry",
        }),
    )

    # Schedule config
    sched_data = yaml_data.get("schedule", {})
    schedule = ScheduleConfig(
        frequency=int(sched_data.get("frequency", 1)),
        send_days=sched_data.get("send_days", ["tuesday"]),
    )

    # Sponsor slots config
    ss_data = yaml_data.get("sponsor_slots", {})
    sponsor_slots = SponsorSlotsConfig(
        max_per_issue=int(ss_data.get("max_per_issue", 2)),
        available_positions=ss_data.get("available_positions", ["top", "mid", "bottom"]),
    )

    # Agents config
    agents_data = yaml_data.get("agents", {})
    agents = AgentsConfig(
        default_autonomy=agents_data.get("default_autonomy", "supervised"),
        review_required=agents_data.get("review_required", True),
        max_concurrent_tasks=int(agents_data.get("max_concurrent_tasks", 3)),
    )

    # Submissions config
    subs_data = yaml_data.get("submissions", {})
    submissions = SubmissionsConfig(
        api_key=os.getenv("TRUEFANS_SUBMISSIONS_API_KEY", subs_data.get("api_key", "")),
        auto_acknowledge=subs_data.get("auto_acknowledge", True),
        require_email=subs_data.get("require_email", True),
    )

    # Email config with env overrides (GoHighLevel / Mailgun SMTP)
    email_data = yaml_data.get("email", {})
    email = EmailConfig(
        enabled=os.getenv("WEEKLYAMP_EMAIL_ENABLED", str(email_data.get("enabled", False))).lower() in ("true", "1", "yes"),
        smtp_host=os.getenv("WEEKLYAMP_SMTP_HOST", email_data.get("smtp_host", "")),
        smtp_port=int(os.getenv("WEEKLYAMP_SMTP_PORT", email_data.get("smtp_port", 587))),
        smtp_user=os.getenv("WEEKLYAMP_SMTP_USER", email_data.get("smtp_user", "")),
        smtp_password=os.getenv("WEEKLYAMP_SMTP_PASSWORD", email_data.get("smtp_password", "")),
        from_address=os.getenv("WEEKLYAMP_EMAIL_FROM", email_data.get("from_address", "")),
        from_name=os.getenv("WEEKLYAMP_EMAIL_FROM_NAME", email_data.get("from_name", "TrueFans NEWSLETTERS")),
    )

    # Rate limit config
    rl_data = yaml_data.get("rate_limits", {})
    rate_limits = RateLimitConfig(
        login_max=int(os.getenv("WEEKLYAMP_RATE_LOGIN_MAX", rl_data.get("login_max", 5))),
        login_window=int(os.getenv("WEEKLYAMP_RATE_LOGIN_WINDOW", rl_data.get("login_window", 900))),
        subscribe_max=int(os.getenv("WEEKLYAMP_RATE_SUBSCRIBE_MAX", rl_data.get("subscribe_max", 5))),
        subscribe_window=int(os.getenv("WEEKLYAMP_RATE_SUBSCRIBE_WINDOW", rl_data.get("subscribe_window", 900))),
        submit_max=int(os.getenv("WEEKLYAMP_RATE_SUBMIT_MAX", rl_data.get("submit_max", 10))),
        submit_window=int(os.getenv("WEEKLYAMP_RATE_SUBMIT_WINDOW", rl_data.get("submit_window", 900))),
    )

    # Analytics config (with tracking sub-config)
    analytics_data = yaml_data.get("analytics", {})
    analytics = AnalyticsConfig(
        plausible_domain=analytics_data.get("plausible_domain", ""),
        tracking_enabled=analytics_data.get("tracking_enabled", False),
        utm_auto_tag=analytics_data.get("utm_auto_tag", False),
        utm_source=analytics_data.get("utm_source", "truefans_newsletter"),
        utm_medium=analytics_data.get("utm_medium", "email"),
    )

    # Tracking config
    trk_data = yaml_data.get("tracking", {})
    tracking = TrackingConfig(
        open_tracking=trk_data.get("open_tracking", False),
        click_tracking=trk_data.get("click_tracking", False),
        tracking_domain=os.getenv("WEEKLYAMP_TRACKING_DOMAIN", trk_data.get("tracking_domain", "")),
    )

    # A/B testing config
    ab_data = yaml_data.get("ab_testing", {})
    ab_testing = ABTestConfig(**ab_data) if ab_data else ABTestConfig()

    # Deliverability config
    deliv_data = yaml_data.get("deliverability", {})
    deliverability = DeliverabilityConfig(**deliv_data) if deliv_data else DeliverabilityConfig()

    # Scheduler config
    sched_pub_data = yaml_data.get("scheduler", {})
    scheduler = SchedulerConfig(**sched_pub_data) if sched_pub_data else SchedulerConfig()

    # Webhook config
    wh_data = yaml_data.get("webhooks", {})
    webhooks_cfg = WebhookConfig(
        enabled=wh_data.get("enabled", False),
        inbound_secret=os.getenv("WEEKLYAMP_WEBHOOK_SECRET", wh_data.get("inbound_secret", "")),
        max_retries=wh_data.get("max_retries", 3),
        timeout_seconds=wh_data.get("timeout_seconds", 10),
    )

    # Referral config
    ref_data = yaml_data.get("referrals", {})
    referrals = ReferralConfig(**ref_data) if ref_data else ReferralConfig()

    # Welcome sequence config
    ws_data = yaml_data.get("welcome_sequence", {})
    welcome_sequence = WelcomeSequenceConfig(**ws_data) if ws_data else WelcomeSequenceConfig()

    # Re-engagement config
    re_data = yaml_data.get("reengagement", {})
    reengagement = ReengagementConfig(**re_data) if re_data else ReengagementConfig()

    # Roles config
    roles_data = yaml_data.get("roles", {})
    roles = RolesConfig(**roles_data) if roles_data else RolesConfig()

    # Spotify config
    sp_data = yaml_data.get("spotify", {})
    spotify = SpotifyConfig(
        enabled=sp_data.get("enabled", False),
        client_id=os.getenv("SPOTIFY_CLIENT_ID", sp_data.get("client_id", "")),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET", sp_data.get("client_secret", "")),
        cache_ttl_hours=sp_data.get("cache_ttl_hours", 24),
        auto_lookup_submissions=sp_data.get("auto_lookup_submissions", False),
    )

    # Artist profiles config
    ap_data = yaml_data.get("artist_profiles", {})
    artist_profiles = ArtistProfilesConfig(**ap_data) if ap_data else ArtistProfilesConfig()

    # Genre preferences config
    gp_data = yaml_data.get("genre_preferences", {})
    genre_preferences = GenrePreferencesConfig(**gp_data) if gp_data else GenrePreferencesConfig()

    # Section engagement config
    se_data = yaml_data.get("section_engagement", {})
    section_engagement = SectionEngagementConfig(**se_data) if se_data else SectionEngagementConfig()

    # Trivia/polls config
    tp_data = yaml_data.get("trivia_polls", {})
    trivia_polls = TriviaPollsConfig(**tp_data) if tp_data else TriviaPollsConfig()

    # Lead magnets config
    lm_data = yaml_data.get("lead_magnets", {})
    lead_magnets = LeadMagnetsConfig(**lm_data) if lm_data else LeadMagnetsConfig()

    # Sponsor portal config
    sp_portal_data = yaml_data.get("sponsor_portal", {})
    sponsor_portal = SponsorPortalConfig(**sp_portal_data) if sp_portal_data else SponsorPortalConfig()

    # Contests config
    ct_data = yaml_data.get("contests", {})
    contests = ContestsConfig(**ct_data) if ct_data else ContestsConfig()

    # Reader content config
    rc_data = yaml_data.get("reader_content", {})
    reader_content = ReaderContentConfig(**rc_data) if rc_data else ReaderContentConfig()

    # DB path and backend
    db_path = os.getenv("WEEKLYAMP_DB_PATH", yaml_data.get("db_path", "data/weeklyamp.db"))
    db_backend = os.getenv("WEEKLYAMP_DB_BACKEND", yaml_data.get("db_backend", "sqlite"))
    database_url = os.getenv("WEEKLYAMP_DATABASE_URL", yaml_data.get("database_url", ""))

    # Site domain
    site_domain = os.getenv("WEEKLYAMP_SITE_DOMAIN", yaml_data.get("site_domain", "https://truefansnewsletters.com"))

    # Session max age
    session_max_age = int(os.getenv("WEEKLYAMP_SESSION_MAX_AGE", yaml_data.get("session_max_age", 43200)))

    # Pagination default
    pagination_default = int(os.getenv("WEEKLYAMP_PAGINATION_DEFAULT", yaml_data.get("pagination_default", 50)))

    # Max request body size
    max_request_body = int(os.getenv("WEEKLYAMP_MAX_REQUEST_BODY", yaml_data.get("max_request_body", 1_048_576)))

    return AppConfig(
        newsletter=newsletter,
        ai=ai,
        ghl=ghl,
        schedule=schedule,
        sponsor_slots=sponsor_slots,
        agents=agents,
        submissions=submissions,
        email=email,
        analytics=analytics,
        tracking=tracking,
        ab_testing=ab_testing,
        deliverability=deliverability,
        scheduler=scheduler,
        webhooks=webhooks_cfg,
        referrals=referrals,
        welcome_sequence=welcome_sequence,
        reengagement=reengagement,
        roles=roles,
        spotify=spotify,
        artist_profiles=artist_profiles,
        genre_preferences=genre_preferences,
        section_engagement=section_engagement,
        trivia_polls=trivia_polls,
        lead_magnets=lead_magnets,
        sponsor_portal=sponsor_portal,
        contests=contests,
        reader_content=reader_content,
        rate_limits=rate_limits,
        db_path=db_path,
        db_backend=db_backend,
        database_url=database_url,
        site_domain=site_domain,
        session_max_age=session_max_age,
        pagination_default=pagination_default,
        max_request_body=max_request_body,
    )


def load_sources_config() -> list[dict]:
    """Load content sources from sources.yaml."""
    root = _find_project_root()
    path = root / "config" / "sources.yaml"
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("sources", [])


def get_prompt_template(section_slug: str) -> str:
    """Load a prompt template from config/prompts/{slug}.md."""
    root = _find_project_root()
    path = root / "config" / "prompts" / f"{section_slug}.md"
    if path.exists():
        return path.read_text()
    return ""
