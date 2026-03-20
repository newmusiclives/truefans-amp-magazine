"""Pydantic models for the WEEKLYAMP platform."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DraftStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISED = "revised"


class IssueStatus(str, Enum):
    PLANNING = "planning"
    DRAFTING = "drafting"
    REVIEWING = "reviewing"
    ASSEMBLED = "assembled"
    PUBLISHED = "published"


class ContentSourceType(str, Enum):
    RSS = "rss"
    SCRAPE = "scrape"
    MANUAL = "manual"


class AIProvider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


# --- Word Count ---

class WordCountLabel(str, Enum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


WORD_COUNT_RANGES: dict[str, tuple[int, int]] = {
    "short": (100, 200),
    "medium": (300, 500),
    "long": (600, 1000),
}

WORD_COUNT_MAX_TOKENS: dict[str, int] = {
    "short": 600,
    "medium": 1500,
    "long": 3000,
}


# --- Section Type ---

class SectionType(str, Enum):
    CORE = "core"
    ROTATING = "rotating"
    SUGGESTED = "suggested"


class SectionCategory(str, Enum):
    MUSIC_INDUSTRY = "music_industry"
    ARTIST_DEVELOPMENT = "artist_development"
    TECHNOLOGY = "technology"
    BUSINESS = "business"
    INSPIRATION = "inspiration"
    COMMUNITY = "community"
    GUEST_CONTENT = "guest_content"


class SeriesType(str, Enum):
    ONGOING = "ongoing"
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


# --- AI Agents ---

class AgentType(str, Enum):
    EDITOR_IN_CHIEF = "editor_in_chief"
    EDITOR = "editor"
    WRITER = "writer"
    RESEARCHER = "researcher"
    SALES = "sales"
    GROWTH = "growth"


class AgentTaskState(str, Enum):
    IDLE = "idle"
    ASSIGNED = "assigned"
    WORKING = "working"
    REVIEW = "review"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AutonomyLevel(str, Enum):
    MANUAL = "manual"
    SUPERVISED = "supervised"
    SEMI_AUTO = "semi_auto"
    AUTONOMOUS = "autonomous"


# --- Guest Articles ---

class PermissionState(str, Enum):
    REQUESTED = "requested"
    RECEIVED = "received"
    APPROVED = "approved"
    PUBLISHED = "published"
    DECLINED = "declined"


class DisplayMode(str, Enum):
    FULL = "full"
    SUMMARY = "summary"
    EXCERPT = "excerpt"


# --- Submissions ---

class SubmissionType(str, Enum):
    NEW_RELEASE = "new_release"
    TOUR_PROMO = "tour_promo"
    ARTIST_FEATURE = "artist_feature"


class SubmissionReviewState(str, Enum):
    SUBMITTED = "submitted"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"


class IntakeMethod(str, Enum):
    WEB_FORM = "web_form"
    EMAIL = "email"
    API = "api"


# --- Social ---

class SocialPlatform(str, Enum):
    TWITTER = "twitter"
    INSTAGRAM = "instagram"
    LINKEDIN = "linkedin"
    THREADS = "threads"
    BLUESKY = "bluesky"
    OTHER = "other"


class SocialPostStatus(str, Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    POSTED = "posted"
    FAILED = "failed"


class CalendarStatus(str, Enum):
    DRAFT = "draft"
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"


# --- Tracking ---

class TrackingEventType(str, Enum):
    OPEN = "open"
    CLICK = "click"
    UNSUBSCRIBE = "unsubscribe"


# --- A/B Testing ---

class ABTestType(str, Enum):
    SUBJECT = "subject"
    CONTENT = "content"
    SEND_TIME = "send_time"


class ABTestStatus(str, Enum):
    DRAFT = "draft"
    RUNNING = "running"
    MEASURING = "measuring"
    COMPLETE = "complete"
    CANCELLED = "cancelled"


# --- Bounce ---

class BounceType(str, Enum):
    HARD = "hard"
    SOFT = "soft"
    COMPLAINT = "complaint"


# --- Scheduled Send ---

class ScheduledSendStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    CANCELLED = "cancelled"
    FAILED = "failed"


# --- Webhook ---

class WebhookDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class WebhookEventType(str, Enum):
    ISSUE_PUBLISHED = "issue.published"
    SUBSCRIBER_NEW = "subscriber.new"
    SUBSCRIBER_UNSUBSCRIBED = "subscriber.unsubscribed"
    BOUNCE_RECEIVED = "bounce.received"
    SUBMISSION_RECEIVED = "submission.received"


# --- Content Frequency ---

class ContentFrequency(str, Enum):
    ALL = "all"
    WEEKLY_DIGEST = "weekly_digest"
    HIGHLIGHTS_ONLY = "highlights_only"


# --- Reusable Block ---

class ReusableBlockType(str, Enum):
    SPONSOR = "sponsor"
    CONTENT = "content"
    CTA = "cta"
    HEADER = "header"
    FOOTER = "footer"


# --- User Role ---

class UserRole(str, Enum):
    ADMIN = "admin"
    EDITOR = "editor"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


# --- Re-engagement ---

class ReengagementType(str, Enum):
    WINBACK = "winback"
    SURVEY = "survey"
    LAST_CHANCE = "last_chance"


# --- Export ---

class ExportType(str, Enum):
    SUBSCRIBERS = "subscribers"
    CONTENT = "content"
    CONFIG = "config"
    FULL_BACKUP = "full_backup"


# --- Day of Week ---

class DayOfWeek(str, Enum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


# --- Sponsor ---

class SponsorBlockPosition(str, Enum):
    TOP = "top"
    MID = "mid"
    BOTTOM = "bottom"


class BookingStatus(str, Enum):
    INQUIRY = "inquiry"
    BOOKED = "booked"
    CONFIRMED = "confirmed"
    DELIVERED = "delivered"
    INVOICED = "invoiced"
    PAID = "paid"


# --- Section ---

class SectionDefinition(BaseModel):
    id: Optional[int] = None
    slug: str
    display_name: str
    sort_order: int
    prompt_template: str = ""
    is_active: bool = True
    section_type: SectionType = SectionType.CORE
    target_word_count: int = 300
    word_count_label: WordCountLabel = WordCountLabel.MEDIUM
    suggested_at: Optional[datetime] = None
    suggested_reason: str = ""
    last_used_issue_id: Optional[int] = None
    category: str = ""
    series_type: str = "ongoing"
    series_length: int = 0
    series_current: int = 0
    description: str = ""
    created_at: Optional[datetime] = None


class SectionRotationLog(BaseModel):
    id: Optional[int] = None
    issue_id: int
    section_slug: str
    was_included: bool = True
    created_at: Optional[datetime] = None


# --- Issue ---

class Issue(BaseModel):
    id: Optional[int] = None
    issue_number: int
    title: str = ""
    status: IssueStatus = IssueStatus.PLANNING
    publish_date: Optional[datetime] = None
    week_id: str = ""
    send_day: str = ""
    edition_slug: str = ""
    issue_template: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# --- Content Source ---

class ContentSource(BaseModel):
    id: Optional[int] = None
    name: str
    source_type: ContentSourceType
    url: str
    target_sections: str = ""  # comma-separated slugs
    is_active: bool = True
    last_fetched: Optional[datetime] = None


# --- Raw Content ---

class RawContent(BaseModel):
    id: Optional[int] = None
    source_id: Optional[int] = None
    title: str = ""
    url: str = ""
    author: str = ""
    summary: str = ""
    full_text: str = ""
    published_at: Optional[datetime] = None
    fetched_at: Optional[datetime] = None
    relevance_score: float = 0.0
    matched_sections: str = ""  # comma-separated slugs
    is_used: bool = False


# --- Editorial Input ---

class EditorialInput(BaseModel):
    id: Optional[int] = None
    issue_id: Optional[int] = None
    section_slug: str
    topic: str = ""
    notes: str = ""
    reference_urls: str = ""
    created_at: Optional[datetime] = None


# --- Draft ---

class Draft(BaseModel):
    id: Optional[int] = None
    issue_id: int
    section_slug: str
    version: int = 1
    content: str = ""
    ai_model: str = ""
    prompt_used: str = ""
    status: DraftStatus = DraftStatus.PENDING
    reviewer_notes: str = ""
    created_at: Optional[datetime] = None


# --- Assembled Issue ---

class AssembledIssue(BaseModel):
    id: Optional[int] = None
    issue_id: int
    html_content: str = ""
    plain_text: str = ""
    ghl_campaign_id: str = ""
    assembled_at: Optional[datetime] = None
    published_at: Optional[datetime] = None


# --- Subscriber ---

class Subscriber(BaseModel):
    id: Optional[int] = None
    email: str
    ghl_contact_id: str = ""
    status: str = "active"
    subscribed_at: Optional[datetime] = None
    synced_at: Optional[datetime] = None


# --- Engagement ---

class EngagementMetric(BaseModel):
    id: Optional[int] = None
    issue_id: int
    ghl_campaign_id: str = ""
    sends: int = 0
    opens: int = 0
    clicks: int = 0
    open_rate: float = 0.0
    click_rate: float = 0.0
    fetched_at: Optional[datetime] = None


# --- Sponsor Block ---

class SponsorBlock(BaseModel):
    id: Optional[int] = None
    issue_id: int
    position: SponsorBlockPosition = SponsorBlockPosition.MID
    sponsor_name: str = ""
    headline: str = ""
    body_html: str = ""
    cta_url: str = ""
    cta_text: str = "Learn More"
    image_url: str = ""
    is_active: bool = True
    edition_slug: str = ""
    edition_number: int = 1
    created_at: Optional[datetime] = None


# --- Sponsor (CRM) ---

class Sponsor(BaseModel):
    id: Optional[int] = None
    name: str
    contact_name: str = ""
    contact_email: str = ""
    website: str = ""
    notes: str = ""
    is_active: bool = True
    created_at: Optional[datetime] = None


class EditionSponsor(BaseModel):
    id: Optional[int] = None
    edition_slug: str = ""
    edition_number: int = 1
    sponsor_id: Optional[int] = None
    sponsor_name: str = ""
    logo_url: str = ""
    tagline: str = ""
    website_url: str = ""
    notes: str = ""
    is_active: bool = True
    created_at: Optional[datetime] = None


class SponsorBooking(BaseModel):
    id: Optional[int] = None
    sponsor_id: int
    issue_id: Optional[int] = None
    position: SponsorBlockPosition = SponsorBlockPosition.MID
    status: BookingStatus = BookingStatus.INQUIRY
    rate_cents: int = 0
    notes: str = ""
    booked_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# --- Send Schedule ---

class SendSchedule(BaseModel):
    id: Optional[int] = None
    day_of_week: str
    edition_slug: str = ""
    label: str = ""
    section_slugs: str = ""  # comma-separated
    is_active: bool = True
    created_at: Optional[datetime] = None


# --- AI Agent ---

class AIAgent(BaseModel):
    id: Optional[int] = None
    agent_type: AgentType = AgentType.WRITER
    name: str = ""
    persona: str = ""
    system_prompt: str = ""
    autonomy_level: AutonomyLevel = AutonomyLevel.MANUAL
    config_json: str = "{}"
    is_active: bool = True
    created_at: Optional[datetime] = None


class AgentTask(BaseModel):
    id: Optional[int] = None
    agent_id: int = 0
    task_type: str = ""
    state: AgentTaskState = AgentTaskState.IDLE
    priority: int = 5
    input_json: str = "{}"
    output_json: str = "{}"
    issue_id: Optional[int] = None
    section_slug: str = ""
    human_override: bool = False
    human_notes: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AgentOutputLog(BaseModel):
    id: Optional[int] = None
    task_id: int = 0
    agent_id: int = 0
    output_type: str = ""
    content: str = ""
    metadata_json: str = "{}"
    tokens_used: int = 0
    created_at: Optional[datetime] = None


# --- Guest Articles ---

class GuestContact(BaseModel):
    id: Optional[int] = None
    name: str = ""
    email: str = ""
    organization: str = ""
    role: str = ""
    website: str = ""
    notes: str = ""
    created_at: Optional[datetime] = None


class GuestArticle(BaseModel):
    id: Optional[int] = None
    contact_id: Optional[int] = None
    title: str = ""
    author_name: str = ""
    author_bio: str = ""
    original_url: str = ""
    content_full: str = ""
    content_summary: str = ""
    display_mode: DisplayMode = DisplayMode.FULL
    permission_state: PermissionState = PermissionState.REQUESTED
    target_issue_id: Optional[int] = None
    target_section_slug: str = ""
    draft_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# --- Artist Submissions ---

class ArtistSubmission(BaseModel):
    id: Optional[int] = None
    artist_name: str = ""
    artist_email: str = ""
    artist_website: str = ""
    artist_social: str = ""
    submission_type: SubmissionType = SubmissionType.NEW_RELEASE
    intake_method: IntakeMethod = IntakeMethod.WEB_FORM
    title: str = ""
    description: str = ""
    release_date: str = ""
    genre: str = ""
    links_json: str = "[]"
    attachments_json: str = "[]"
    review_state: SubmissionReviewState = SubmissionReviewState.SUBMITTED
    target_issue_id: Optional[int] = None
    target_section_slug: str = ""
    draft_id: Optional[int] = None
    api_source: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# --- Editorial Calendar ---

class EditorialCalendar(BaseModel):
    id: Optional[int] = None
    issue_id: Optional[int] = None
    planned_date: str = ""
    theme: str = ""
    notes: str = ""
    section_assignments: str = "{}"
    agent_assignments: str = "{}"
    status: CalendarStatus = CalendarStatus.DRAFT
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# --- Growth Metrics ---

class GrowthMetric(BaseModel):
    id: Optional[int] = None
    metric_date: str = ""
    total_subscribers: int = 0
    new_subscribers: int = 0
    churned_subscribers: int = 0
    open_rate_avg: float = 0.0
    click_rate_avg: float = 0.0
    referral_count: int = 0
    social_impressions: int = 0
    created_at: Optional[datetime] = None


# --- Social Posts ---

class SocialPost(BaseModel):
    id: Optional[int] = None
    platform: SocialPlatform = SocialPlatform.TWITTER
    content: str = ""
    issue_id: Optional[int] = None
    status: SocialPostStatus = SocialPostStatus.DRAFT
    scheduled_at: Optional[datetime] = None
    posted_at: Optional[datetime] = None
    agent_task_id: Optional[int] = None
    created_at: Optional[datetime] = None


# --- Config models ---

class AIConfig(BaseModel):
    provider: AIProvider = AIProvider.ANTHROPIC
    model: str = "claude-sonnet-4-5-20250929"
    max_tokens: int = 2000
    temperature: float = 0.7


class GHLConfig(BaseModel):
    api_key: str = ""
    location_id: str = ""
    base_url: str = "https://services.leadconnectorhq.com"
    edition_tags: dict[str, str] = Field(default_factory=lambda: {
        "fan": "newsletter-fan",
        "artist": "newsletter-artist",
        "industry": "newsletter-industry",
    })


class NewsletterConfig(BaseModel):
    name: str = "TrueFans NEWSLETTERS"
    tagline: str = "for Industry Professionals, Music Artists and Fans"
    from_name: str = "PS"
    reply_to: str = ""
    header_image_url: str = ""
    intro_copy: str = ""
    footer_html: str = ""


class ScheduleConfig(BaseModel):
    frequency: int = 1
    send_days: list[str] = Field(default_factory=lambda: ["tuesday"])


class SponsorSlotsConfig(BaseModel):
    max_per_issue: int = 2
    available_positions: list[str] = Field(default_factory=lambda: ["top", "mid", "bottom"])


class AgentsConfig(BaseModel):
    default_autonomy: str = "supervised"
    review_required: bool = True
    max_concurrent_tasks: int = 3


class SubmissionsConfig(BaseModel):
    api_key: str = ""
    auto_acknowledge: bool = True
    require_email: bool = True


class EmailConfig(BaseModel):
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    from_address: str = ""
    from_name: str = "TrueFans NEWSLETTERS"


class AnalyticsConfig(BaseModel):
    plausible_domain: str = ""
    tracking_enabled: bool = False
    utm_auto_tag: bool = False
    utm_source: str = "truefans_newsletter"
    utm_medium: str = "email"


class TrackingConfig(BaseModel):
    open_tracking: bool = False
    click_tracking: bool = False
    tracking_domain: str = ""  # e.g. "trk.truefansnewsletters.com"


class ABTestConfig(BaseModel):
    enabled: bool = False
    default_sample_percent: int = 20
    default_measurement_hours: int = 4
    auto_send_winner: bool = True


class DeliverabilityConfig(BaseModel):
    bounce_handling: bool = False
    hard_bounce_threshold: int = 1
    soft_bounce_threshold: int = 3
    auto_suppress: bool = False
    warmup_enabled: bool = False
    warmup_daily_start: int = 50
    warmup_ramp_increment: int = 50


class SchedulerConfig(BaseModel):
    enabled: bool = False
    check_interval_seconds: int = 60
    default_send_hour: int = 9
    default_timezone: str = "America/New_York"


class WebhookConfig(BaseModel):
    enabled: bool = False
    inbound_secret: str = ""
    max_retries: int = 3
    timeout_seconds: int = 10


class ReferralConfig(BaseModel):
    enabled: bool = False
    reward_threshold: int = 3
    code_prefix: str = "TF"


class WelcomeSequenceConfig(BaseModel):
    enabled: bool = False
    default_steps: int = 3


class ReengagementConfig(BaseModel):
    enabled: bool = False
    inactive_days: int = 30
    suppress_after_days: int = 60


class RolesConfig(BaseModel):
    enabled: bool = False
    require_login: bool = True


class SpotifyConfig(BaseModel):
    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    cache_ttl_hours: int = 24
    auto_lookup_submissions: bool = False


class ArtistProfilesConfig(BaseModel):
    enabled: bool = False
    allow_self_service: bool = False
    require_approval: bool = True


class GenrePreferencesConfig(BaseModel):
    enabled: bool = False
    available_genres: list[str] = Field(default_factory=lambda: [
        "hip-hop", "rock", "pop", "country", "electronic", "jazz",
        "r&b", "latin", "metal", "indie", "classical", "folk",
        "reggae", "punk", "world",
    ])
    weight_sections_by_genre: bool = False
    max_genres_per_subscriber: int = 5


class SectionEngagementConfig(BaseModel):
    enabled: bool = False
    score_decay_days: int = 90
    min_events_for_profile: int = 5
    reorder_by_engagement: bool = False


class TriviaPollsConfig(BaseModel):
    enabled: bool = False
    max_options: int = 6
    show_results_in_next_issue: bool = True
    leaderboard_size: int = 25


class LeadMagnetsConfig(BaseModel):
    enabled: bool = False


class SponsorPortalConfig(BaseModel):
    enabled: bool = False
    public_rates_visible: bool = False
    base_cpm: float = 30.0
    premium_position_multiplier: float = 1.5
    weekly_discount: float = 0.9
    monthly_discount: float = 0.8


class ContestsConfig(BaseModel):
    enabled: bool = False
    max_active: int = 3


class ReaderContentConfig(BaseModel):
    enabled: bool = False
    auto_approve: bool = False
    max_per_issue: int = 2


class RateLimitConfig(BaseModel):
    login_max: int = 5
    login_window: int = 900
    subscribe_max: int = 5
    subscribe_window: int = 900
    submit_max: int = 10
    submit_window: int = 900


class AppConfig(BaseModel):
    newsletter: NewsletterConfig = Field(default_factory=NewsletterConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    ghl: GHLConfig = Field(default_factory=GHLConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    sponsor_slots: SponsorSlotsConfig = Field(default_factory=SponsorSlotsConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    submissions: SubmissionsConfig = Field(default_factory=SubmissionsConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    analytics: AnalyticsConfig = Field(default_factory=AnalyticsConfig)
    tracking: TrackingConfig = Field(default_factory=TrackingConfig)
    ab_testing: ABTestConfig = Field(default_factory=ABTestConfig)
    deliverability: DeliverabilityConfig = Field(default_factory=DeliverabilityConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    webhooks: WebhookConfig = Field(default_factory=WebhookConfig)
    referrals: ReferralConfig = Field(default_factory=ReferralConfig)
    welcome_sequence: WelcomeSequenceConfig = Field(default_factory=WelcomeSequenceConfig)
    reengagement: ReengagementConfig = Field(default_factory=ReengagementConfig)
    roles: RolesConfig = Field(default_factory=RolesConfig)
    spotify: SpotifyConfig = Field(default_factory=SpotifyConfig)
    artist_profiles: ArtistProfilesConfig = Field(default_factory=ArtistProfilesConfig)
    genre_preferences: GenrePreferencesConfig = Field(default_factory=GenrePreferencesConfig)
    section_engagement: SectionEngagementConfig = Field(default_factory=SectionEngagementConfig)
    trivia_polls: TriviaPollsConfig = Field(default_factory=TriviaPollsConfig)
    lead_magnets: LeadMagnetsConfig = Field(default_factory=LeadMagnetsConfig)
    sponsor_portal: SponsorPortalConfig = Field(default_factory=SponsorPortalConfig)
    contests: ContestsConfig = Field(default_factory=ContestsConfig)
    reader_content: ReaderContentConfig = Field(default_factory=ReaderContentConfig)
    rate_limits: RateLimitConfig = Field(default_factory=RateLimitConfig)
    db_path: str = "data/weeklyamp.db"
    db_backend: str = "sqlite"  # "sqlite" or "postgres"
    database_url: str = ""  # PostgreSQL connection string
    site_domain: str = "https://truefansnewsletters.com"
    session_max_age: int = 43200  # 12 hours
    pagination_default: int = 50
    max_request_body: int = 1_048_576  # 1 MB
