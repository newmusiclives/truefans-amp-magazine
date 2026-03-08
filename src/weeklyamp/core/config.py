"""Configuration loader: YAML files + environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

from weeklyamp.core.models import (
    AgentsConfig,
    AIConfig,
    AIProvider,
    AppConfig,
    BeehiivConfig,
    EmailConfig,
    NewsletterConfig,
    RateLimitConfig,
    ScheduleConfig,
    SponsorSlotsConfig,
    SubmissionsConfig,
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

    # Build Beehiiv config with env overrides
    bh_data = yaml_data.get("beehiiv", {})
    beehiiv = BeehiivConfig(
        api_key=os.getenv("BEEHIIV_API_KEY", bh_data.get("api_key", "")),
        publication_id=os.getenv("BEEHIIV_PUBLICATION_ID", bh_data.get("publication_id", "")),
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
        beehiiv=beehiiv,
        schedule=schedule,
        sponsor_slots=sponsor_slots,
        agents=agents,
        submissions=submissions,
        email=email,
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
