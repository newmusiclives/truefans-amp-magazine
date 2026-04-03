"""Schema migration runner for WEEKLYAMP database."""

from __future__ import annotations

import sqlite3
from typing import Optional

from weeklyamp.core.database import get_connection

# Migrations keyed by target version number.
# Each migration runs SQL to advance from (version - 1) to version.
#
# NOTE: These migrations use SQLite-specific syntax (INSERT OR IGNORE,
# INTEGER PRIMARY KEY AUTOINCREMENT).  PostgreSQL equivalents are in
# PG_MIGRATIONS below.
MIGRATIONS: dict[int, str] = {
    2: """
-- v2: Add word count columns to section_definitions
ALTER TABLE section_definitions ADD COLUMN section_type TEXT DEFAULT 'core';
ALTER TABLE section_definitions ADD COLUMN target_word_count INTEGER DEFAULT 300;
ALTER TABLE section_definitions ADD COLUMN word_count_label TEXT DEFAULT 'medium';
ALTER TABLE section_definitions ADD COLUMN suggested_at TIMESTAMP;
ALTER TABLE section_definitions ADD COLUMN suggested_reason TEXT DEFAULT '';
ALTER TABLE section_definitions ADD COLUMN last_used_issue_id INTEGER;

INSERT OR IGNORE INTO schema_version (version) VALUES (2);
""",
    3: """
-- v3: Add issue scheduling columns + section_rotation_log + send_schedule tables
ALTER TABLE issues ADD COLUMN week_id TEXT DEFAULT '';
ALTER TABLE issues ADD COLUMN send_day TEXT DEFAULT '';
ALTER TABLE issues ADD COLUMN issue_template TEXT DEFAULT '';

CREATE TABLE IF NOT EXISTS section_rotation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL REFERENCES issues(id),
    section_slug TEXT NOT NULL,
    was_included INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_rotation_log_issue ON section_rotation_log(issue_id);

CREATE TABLE IF NOT EXISTS send_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day_of_week TEXT NOT NULL,
    label TEXT DEFAULT '',
    section_slugs TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO schema_version (version) VALUES (3);
""",
    4: """
-- v4: Sponsor blocks table
CREATE TABLE IF NOT EXISTS sponsor_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL REFERENCES issues(id),
    position TEXT NOT NULL DEFAULT 'mid' CHECK (position IN ('top','mid','bottom')),
    sponsor_name TEXT DEFAULT '',
    headline TEXT DEFAULT '',
    body_html TEXT DEFAULT '',
    cta_url TEXT DEFAULT '',
    cta_text TEXT DEFAULT 'Learn More',
    image_url TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sponsor_blocks_issue ON sponsor_blocks(issue_id);

INSERT OR IGNORE INTO schema_version (version) VALUES (4);
""",
    5: """
-- v5: Sponsors CRM tables
CREATE TABLE IF NOT EXISTS sponsors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    contact_name TEXT DEFAULT '',
    contact_email TEXT DEFAULT '',
    website TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sponsor_bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sponsor_id INTEGER NOT NULL REFERENCES sponsors(id),
    issue_id INTEGER REFERENCES issues(id),
    position TEXT DEFAULT 'mid' CHECK (position IN ('top','mid','bottom')),
    status TEXT DEFAULT 'inquiry' CHECK (status IN ('inquiry','booked','confirmed','delivered','invoiced','paid')),
    rate_cents INTEGER DEFAULT 0,
    notes TEXT DEFAULT '',
    booked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bookings_sponsor ON sponsor_bookings(sponsor_id);
CREATE INDEX IF NOT EXISTS idx_bookings_issue ON sponsor_bookings(issue_id);

INSERT OR IGNORE INTO schema_version (version) VALUES (5);
""",
    6: """
-- v6: Section expansion — category, series, description
ALTER TABLE section_definitions ADD COLUMN category TEXT DEFAULT '';
ALTER TABLE section_definitions ADD COLUMN series_type TEXT DEFAULT 'ongoing';
ALTER TABLE section_definitions ADD COLUMN series_length INTEGER DEFAULT 0;
ALTER TABLE section_definitions ADD COLUMN series_current INTEGER DEFAULT 0;
ALTER TABLE section_definitions ADD COLUMN description TEXT DEFAULT '';

INSERT OR IGNORE INTO schema_version (version) VALUES (6);
""",
    7: """
-- v7: AI agent system
CREATE TABLE IF NOT EXISTS ai_agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_type TEXT NOT NULL CHECK (agent_type IN ('editor_in_chief','editor','writer','researcher','sales','promotion','growth')),
    name TEXT NOT NULL,
    persona TEXT DEFAULT '',
    system_prompt TEXT DEFAULT '',
    autonomy_level TEXT DEFAULT 'manual' CHECK (autonomy_level IN ('manual','supervised','semi_auto','autonomous')),
    config_json TEXT DEFAULT '{}',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL REFERENCES ai_agents(id),
    task_type TEXT NOT NULL,
    state TEXT DEFAULT 'idle' CHECK (state IN ('idle','assigned','working','review','complete','failed','cancelled')),
    priority INTEGER DEFAULT 5,
    input_json TEXT DEFAULT '{}',
    output_json TEXT DEFAULT '{}',
    issue_id INTEGER REFERENCES issues(id),
    section_slug TEXT DEFAULT '',
    human_override INTEGER DEFAULT 0,
    human_notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_agent ON agent_tasks(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_state ON agent_tasks(state);

CREATE TABLE IF NOT EXISTS agent_output_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES agent_tasks(id),
    agent_id INTEGER NOT NULL REFERENCES ai_agents(id),
    output_type TEXT DEFAULT '',
    content TEXT DEFAULT '',
    metadata_json TEXT DEFAULT '{}',
    tokens_used INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_output_log_task ON agent_output_log(task_id);

INSERT OR IGNORE INTO schema_version (version) VALUES (7);
""",
    8: """
-- v8: Guest article system
CREATE TABLE IF NOT EXISTS guest_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT DEFAULT '',
    organization TEXT DEFAULT '',
    role TEXT DEFAULT '',
    website TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS guest_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER REFERENCES guest_contacts(id),
    title TEXT DEFAULT '',
    author_name TEXT DEFAULT '',
    author_bio TEXT DEFAULT '',
    original_url TEXT DEFAULT '',
    content_full TEXT DEFAULT '',
    content_summary TEXT DEFAULT '',
    display_mode TEXT DEFAULT 'full' CHECK (display_mode IN ('full','summary','excerpt')),
    permission_state TEXT DEFAULT 'requested' CHECK (permission_state IN ('requested','received','approved','published','declined')),
    target_issue_id INTEGER REFERENCES issues(id),
    target_section_slug TEXT DEFAULT '',
    draft_id INTEGER REFERENCES drafts(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_guest_articles_contact ON guest_articles(contact_id);
CREATE INDEX IF NOT EXISTS idx_guest_articles_issue ON guest_articles(target_issue_id);

INSERT OR IGNORE INTO schema_version (version) VALUES (8);
""",
    9: """
-- v9: Artist submission system
CREATE TABLE IF NOT EXISTS artist_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artist_name TEXT NOT NULL,
    artist_email TEXT DEFAULT '',
    artist_website TEXT DEFAULT '',
    artist_social TEXT DEFAULT '',
    submission_type TEXT DEFAULT 'new_release' CHECK (submission_type IN ('new_release','tour_promo','artist_feature')),
    intake_method TEXT DEFAULT 'web_form' CHECK (intake_method IN ('web_form','email','api')),
    title TEXT DEFAULT '',
    description TEXT DEFAULT '',
    release_date TEXT DEFAULT '',
    genre TEXT DEFAULT '',
    links_json TEXT DEFAULT '[]',
    attachments_json TEXT DEFAULT '[]',
    review_state TEXT DEFAULT 'submitted' CHECK (review_state IN ('submitted','reviewed','approved','rejected','scheduled','published')),
    target_issue_id INTEGER REFERENCES issues(id),
    target_section_slug TEXT DEFAULT '',
    draft_id INTEGER REFERENCES drafts(id),
    api_source TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_submissions_state ON artist_submissions(review_state);

INSERT OR IGNORE INTO schema_version (version) VALUES (9);
""",
    10: """
-- v10: Editorial calendar + growth tracking + social posts
CREATE TABLE IF NOT EXISTS editorial_calendar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER REFERENCES issues(id),
    planned_date TEXT DEFAULT '',
    theme TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    section_assignments TEXT DEFAULT '{}',
    agent_assignments TEXT DEFAULT '{}',
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft','planned','in_progress','complete')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_calendar_issue ON editorial_calendar(issue_id);

CREATE TABLE IF NOT EXISTS growth_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_date TEXT NOT NULL,
    total_subscribers INTEGER DEFAULT 0,
    new_subscribers INTEGER DEFAULT 0,
    churned_subscribers INTEGER DEFAULT 0,
    open_rate_avg REAL DEFAULT 0.0,
    click_rate_avg REAL DEFAULT 0.0,
    referral_count INTEGER DEFAULT 0,
    social_impressions INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_growth_date ON growth_metrics(metric_date);

CREATE TABLE IF NOT EXISTS social_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT DEFAULT 'twitter' CHECK (platform IN ('twitter','instagram','linkedin','threads','bluesky','other')),
    content TEXT DEFAULT '',
    issue_id INTEGER REFERENCES issues(id),
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft','scheduled','posted','failed')),
    scheduled_at TIMESTAMP,
    posted_at TIMESTAMP,
    agent_task_id INTEGER REFERENCES agent_tasks(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_social_posts_issue ON social_posts(issue_id);

INSERT OR IGNORE INTO schema_version (version) VALUES (10);
""",
    11: """
-- v11: Security audit log
CREATE TABLE IF NOT EXISTS security_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    ip_address TEXT DEFAULT '',
    user_agent TEXT DEFAULT '',
    detail TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_security_log_event ON security_log(event_type);
CREATE INDEX IF NOT EXISTS idx_security_log_created ON security_log(created_at);

INSERT OR IGNORE INTO schema_version (version) VALUES (11);
""",
    12: """
-- v12: Newsletter editions + subscriber editions + subscriber fields
CREATE TABLE IF NOT EXISTS newsletter_editions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    tagline TEXT DEFAULT '',
    description TEXT DEFAULT '',
    audience TEXT DEFAULT '',
    color TEXT DEFAULT '#e8645a',
    icon TEXT DEFAULT '',
    section_slugs TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_editions_slug ON newsletter_editions(slug);

CREATE TABLE IF NOT EXISTS subscriber_editions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    edition_id INTEGER NOT NULL REFERENCES newsletter_editions(id),
    subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(subscriber_id, edition_id)
);
CREATE INDEX IF NOT EXISTS idx_sub_editions_subscriber ON subscriber_editions(subscriber_id);
CREATE INDEX IF NOT EXISTS idx_sub_editions_edition ON subscriber_editions(edition_id);

ALTER TABLE subscribers ADD COLUMN first_name TEXT DEFAULT '';
ALTER TABLE subscribers ADD COLUMN source_channel TEXT DEFAULT '';

INSERT OR IGNORE INTO schema_version (version) VALUES (12);
""",
    13: """
-- v13: Add send_days to subscriber_editions for per-edition day-of-week frequency
ALTER TABLE subscriber_editions ADD COLUMN send_days TEXT DEFAULT 'monday,wednesday,saturday';

INSERT OR IGNORE INTO schema_version (version) VALUES (13);
""",
    14: """
-- v14: Add category column to guest_contacts
ALTER TABLE guest_contacts ADD COLUMN category TEXT DEFAULT '';

INSERT OR IGNORE INTO schema_version (version) VALUES (14);
""",
    15: """
-- v15: Add edition_slug and edition_number to sponsor_blocks for multi-newsletter ad management
ALTER TABLE sponsor_blocks ADD COLUMN edition_slug TEXT DEFAULT '';
ALTER TABLE sponsor_blocks ADD COLUMN edition_number INTEGER DEFAULT 1;
CREATE INDEX IF NOT EXISTS idx_sponsor_blocks_edition ON sponsor_blocks(edition_slug, edition_number);

INSERT OR IGNORE INTO schema_version (version) VALUES (15);
""",
    16: """
-- v16: Edition main sponsors (1 per newsletter x edition = 9 total)

CREATE TABLE IF NOT EXISTS edition_sponsors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    edition_slug TEXT NOT NULL,
    edition_number INTEGER NOT NULL DEFAULT 1,
    sponsor_id INTEGER REFERENCES sponsors(id),
    sponsor_name TEXT DEFAULT '',
    logo_url TEXT DEFAULT '',
    tagline TEXT DEFAULT '',
    website_url TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(edition_slug, edition_number)
);
CREATE INDEX IF NOT EXISTS idx_edition_sponsors_slug ON edition_sponsors(edition_slug);

INSERT OR IGNORE INTO schema_version (version) VALUES (16);
""",
    17: """
-- v17: Expand agent_type to include 'editor' role
-- SQLite doesn't support ALTER CHECK, so we recreate the table
PRAGMA foreign_keys=OFF;
CREATE TABLE IF NOT EXISTS ai_agents_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_type TEXT NOT NULL CHECK (agent_type IN ('editor_in_chief','editor','writer','researcher','sales','promotion','growth')),
    name TEXT NOT NULL,
    persona TEXT DEFAULT '',
    system_prompt TEXT DEFAULT '',
    autonomy_level TEXT DEFAULT 'manual' CHECK (autonomy_level IN ('manual','supervised','semi_auto','autonomous')),
    config_json TEXT DEFAULT '{}',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO ai_agents_new SELECT * FROM ai_agents;
DROP TABLE ai_agents;
ALTER TABLE ai_agents_new RENAME TO ai_agents;
CREATE INDEX IF NOT EXISTS idx_agent_tasks_agent ON agent_tasks(agent_id);
PRAGMA foreign_keys=ON;

INSERT OR IGNORE INTO schema_version (version) VALUES (17);
""",
    18: """
-- v18: Edition-aware scheduling — add edition_slug to issues and send_schedule
ALTER TABLE issues ADD COLUMN edition_slug TEXT DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_issues_edition ON issues(edition_slug);

ALTER TABLE send_schedule ADD COLUMN edition_slug TEXT DEFAULT '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_schedule_day_edition ON send_schedule(day_of_week, edition_slug);

INSERT OR IGNORE INTO schema_version (version) VALUES (18);
""",
    19: "SPECIAL:beehiiv_to_ghl",
    20: """
-- v20: Editor articles — direct editor-written content
CREATE TABLE IF NOT EXISTS editor_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL DEFAULT '',
    content TEXT DEFAULT '',
    author_name TEXT DEFAULT 'John',
    edition_slug TEXT DEFAULT '',
    target_issue_id INTEGER REFERENCES issues(id),
    target_section_slug TEXT DEFAULT '',
    draft_id INTEGER REFERENCES drafts(id),
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft','ready','assigned','published')),
    notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_editor_articles_edition ON editor_articles(edition_slug);
CREATE INDEX IF NOT EXISTS idx_editor_articles_status ON editor_articles(status);

INSERT OR IGNORE INTO schema_version (version) VALUES (20);
""",
    21: """
-- v21: Advanced newsletter features (tracking, A/B tests, bounce handling,
--      scheduled sends, webhooks, referrals, preferences, welcome sequence,
--      re-engagement, reusable blocks, user roles, export log, send time history)
--      All features are INACTIVE by default — enable via config.

CREATE TABLE IF NOT EXISTS email_tracking_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER REFERENCES subscribers(id),
    issue_id INTEGER REFERENCES issues(id),
    event_type TEXT NOT NULL CHECK (event_type IN ('open','click','unsubscribe')),
    link_url TEXT DEFAULT '',
    ip_address TEXT DEFAULT '',
    user_agent TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tracking_subscriber ON email_tracking_events(subscriber_id);
CREATE INDEX IF NOT EXISTS idx_tracking_issue ON email_tracking_events(issue_id);
CREATE INDEX IF NOT EXISTS idx_tracking_type ON email_tracking_events(event_type);

CREATE TABLE IF NOT EXISTS ab_tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER REFERENCES issues(id),
    test_type TEXT NOT NULL DEFAULT 'subject' CHECK (test_type IN ('subject','content','send_time')),
    variant_a TEXT DEFAULT '',
    variant_b TEXT DEFAULT '',
    variant_a_percentage INTEGER DEFAULT 50,
    winner TEXT DEFAULT '' CHECK (winner IN ('','a','b')),
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft','running','measuring','complete','cancelled')),
    sample_size_percent INTEGER DEFAULT 20,
    auto_send_winner INTEGER DEFAULT 1,
    measurement_hours INTEGER DEFAULT 4,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ab_tests_issue ON ab_tests(issue_id);
CREATE INDEX IF NOT EXISTS idx_ab_tests_status ON ab_tests(status);

CREATE TABLE IF NOT EXISTS ab_test_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id INTEGER NOT NULL REFERENCES ab_tests(id),
    variant TEXT NOT NULL CHECK (variant IN ('a','b')),
    sends INTEGER DEFAULT 0,
    opens INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    unsubscribes INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(test_id, variant)
);

CREATE TABLE IF NOT EXISTS bounce_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER REFERENCES subscribers(id),
    email TEXT NOT NULL,
    bounce_type TEXT NOT NULL DEFAULT 'soft' CHECK (bounce_type IN ('hard','soft','complaint')),
    raw_response TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bounce_email ON bounce_log(email);
CREATE INDEX IF NOT EXISTS idx_bounce_type ON bounce_log(bounce_type);

CREATE TABLE IF NOT EXISTS warmup_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    daily_limit INTEGER DEFAULT 50,
    ramp_increment INTEGER DEFAULT 50,
    ramp_interval_days INTEGER DEFAULT 1,
    current_day INTEGER DEFAULT 0,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scheduled_sends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL REFERENCES issues(id),
    edition_slug TEXT DEFAULT '',
    subject TEXT DEFAULT '',
    scheduled_at TIMESTAMP NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending','processing','sent','cancelled','failed')),
    error_message TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_scheduled_status ON scheduled_sends(status);
CREATE INDEX IF NOT EXISTS idx_scheduled_at ON scheduled_sends(scheduled_at);

CREATE TABLE IF NOT EXISTS webhooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    direction TEXT DEFAULT 'outbound' CHECK (direction IN ('inbound','outbound')),
    event_types TEXT DEFAULT '',
    secret TEXT DEFAULT '',
    is_active INTEGER DEFAULT 0,
    last_triggered_at TIMESTAMP,
    failure_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS webhook_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    webhook_id INTEGER NOT NULL REFERENCES webhooks(id),
    event_type TEXT NOT NULL,
    payload_json TEXT DEFAULT '{}',
    response_status INTEGER DEFAULT 0,
    response_body TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_webhook_log_webhook ON webhook_log(webhook_id);

CREATE TABLE IF NOT EXISTS referral_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    code TEXT UNIQUE NOT NULL,
    referral_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_referral_code ON referral_codes(code);

CREATE TABLE IF NOT EXISTS referral_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_code TEXT NOT NULL,
    referred_subscriber_id INTEGER REFERENCES subscribers(id),
    referred_email TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_referral_referrer ON referral_log(referrer_code);

CREATE TABLE IF NOT EXISTS subscriber_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    content_frequency TEXT DEFAULT 'all' CHECK (content_frequency IN ('all','weekly_digest','highlights_only')),
    preferred_send_hour INTEGER DEFAULT -1,
    timezone TEXT DEFAULT '',
    interests TEXT DEFAULT '',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(subscriber_id)
);

CREATE TABLE IF NOT EXISTS welcome_sequence_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    edition_slug TEXT DEFAULT '',
    step_number INTEGER NOT NULL DEFAULT 1,
    delay_hours INTEGER DEFAULT 0,
    subject TEXT DEFAULT '',
    html_content TEXT DEFAULT '',
    plain_text TEXT DEFAULT '',
    is_active INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_welcome_edition ON welcome_sequence_steps(edition_slug);

CREATE TABLE IF NOT EXISTS welcome_sequence_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    step_id INTEGER NOT NULL REFERENCES welcome_sequence_steps(id),
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_welcome_log_sub ON welcome_sequence_log(subscriber_id);

CREATE TABLE IF NOT EXISTS reengagement_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    campaign_type TEXT DEFAULT 'winback' CHECK (campaign_type IN ('winback','survey','last_chance')),
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    opened INTEGER DEFAULT 0,
    clicked INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_reengagement_sub ON reengagement_log(subscriber_id);

CREATE TABLE IF NOT EXISTS reusable_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    block_type TEXT DEFAULT 'content' CHECK (block_type IN ('sponsor','content','cta','header','footer')),
    html_content TEXT DEFAULT '',
    plain_text TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT DEFAULT '',
    role TEXT DEFAULT 'viewer' CHECK (role IN ('admin','editor','reviewer','viewer')),
    display_name TEXT DEFAULT '',
    email TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    last_login_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS export_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    export_type TEXT NOT NULL CHECK (export_type IN ('subscribers','content','config','full_backup')),
    file_path TEXT DEFAULT '',
    file_size_bytes INTEGER DEFAULT 0,
    record_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS send_time_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    issue_id INTEGER REFERENCES issues(id),
    sent_at TIMESTAMP,
    opened_at TIMESTAMP,
    hour_of_day INTEGER DEFAULT -1,
    day_of_week TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sendtime_sub ON send_time_history(subscriber_id);

INSERT OR IGNORE INTO schema_version (version) VALUES (21);
""",
    22: """
-- v22: Music-specific features — Spotify, artist profiles, genre preferences,
--      section engagement scoring, trivia/polls. All INACTIVE by default.

CREATE TABLE IF NOT EXISTS spotify_artist_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spotify_artist_id TEXT UNIQUE NOT NULL,
    artist_name TEXT DEFAULT '',
    genres TEXT DEFAULT '',
    followers INTEGER DEFAULT 0,
    popularity INTEGER DEFAULT 0,
    image_url TEXT DEFAULT '',
    monthly_listeners INTEGER DEFAULT 0,
    data_json TEXT DEFAULT '{}',
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_spotify_cache_name ON spotify_artist_cache(artist_name);

CREATE TABLE IF NOT EXISTS spotify_releases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spotify_artist_id TEXT NOT NULL,
    album_id TEXT NOT NULL,
    album_name TEXT DEFAULT '',
    release_date TEXT DEFAULT '',
    album_type TEXT DEFAULT 'single' CHECK (album_type IN ('album','single','compilation')),
    image_url TEXT DEFAULT '',
    external_url TEXT DEFAULT '',
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(spotify_artist_id, album_id)
);

CREATE TABLE IF NOT EXISTS audio_embeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER REFERENCES drafts(id),
    issue_id INTEGER REFERENCES issues(id),
    section_slug TEXT DEFAULT '',
    embed_type TEXT NOT NULL CHECK (embed_type IN ('spotify','youtube','apple_music')),
    external_id TEXT DEFAULT '',
    embed_url TEXT DEFAULT '',
    thumbnail_url TEXT DEFAULT '',
    title TEXT DEFAULT '',
    artist_name TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_audio_embeds_issue ON audio_embeds(issue_id);
CREATE INDEX IF NOT EXISTS idx_audio_embeds_draft ON audio_embeds(draft_id);

CREATE TABLE IF NOT EXISTS artist_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    artist_name TEXT NOT NULL,
    email TEXT DEFAULT '',
    bio TEXT DEFAULT '',
    website TEXT DEFAULT '',
    social_links_json TEXT DEFAULT '{}',
    image_url TEXT DEFAULT '',
    spotify_artist_id TEXT DEFAULT '',
    genres TEXT DEFAULT '',
    music_embeds_json TEXT DEFAULT '[]',
    is_published INTEGER DEFAULT 0,
    is_approved INTEGER DEFAULT 0,
    self_service_token TEXT DEFAULT '',
    submission_id INTEGER REFERENCES artist_submissions(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_artist_profiles_slug ON artist_profiles(slug);
CREATE INDEX IF NOT EXISTS idx_artist_profiles_published ON artist_profiles(is_published);

CREATE TABLE IF NOT EXISTS artist_followers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    artist_profile_id INTEGER NOT NULL REFERENCES artist_profiles(id),
    followed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(subscriber_id, artist_profile_id)
);
CREATE INDEX IF NOT EXISTS idx_artist_followers_artist ON artist_followers(artist_profile_id);

CREATE TABLE IF NOT EXISTS artist_newsletter_features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artist_profile_id INTEGER NOT NULL REFERENCES artist_profiles(id),
    issue_id INTEGER NOT NULL REFERENCES issues(id),
    section_slug TEXT DEFAULT '',
    draft_id INTEGER REFERENCES drafts(id),
    featured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_artist_features_artist ON artist_newsletter_features(artist_profile_id);

CREATE TABLE IF NOT EXISTS subscriber_genres (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    genre TEXT NOT NULL,
    priority INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(subscriber_id, genre)
);
CREATE INDEX IF NOT EXISTS idx_sub_genres_sub ON subscriber_genres(subscriber_id);

CREATE TABLE IF NOT EXISTS section_genres (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section_slug TEXT NOT NULL,
    genre TEXT NOT NULL,
    relevance_weight REAL DEFAULT 1.0,
    UNIQUE(section_slug, genre)
);
CREATE INDEX IF NOT EXISTS idx_section_genres_slug ON section_genres(section_slug);

CREATE TABLE IF NOT EXISTS section_engagement_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER REFERENCES subscribers(id),
    issue_id INTEGER REFERENCES issues(id),
    section_slug TEXT NOT NULL,
    event_type TEXT DEFAULT 'click' CHECK (event_type IN ('click','read')),
    link_url TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sec_engage_sub ON section_engagement_events(subscriber_id);
CREATE INDEX IF NOT EXISTS idx_sec_engage_section ON section_engagement_events(section_slug);
CREATE INDEX IF NOT EXISTS idx_sec_engage_issue ON section_engagement_events(issue_id);

CREATE TABLE IF NOT EXISTS section_engagement_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section_slug TEXT NOT NULL,
    issue_id INTEGER REFERENCES issues(id),
    total_clicks INTEGER DEFAULT 0,
    unique_clickers INTEGER DEFAULT 0,
    click_rate REAL DEFAULT 0.0,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(section_slug, issue_id)
);

CREATE TABLE IF NOT EXISTS subscriber_interest_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    section_slug TEXT NOT NULL,
    engagement_score REAL DEFAULT 0.0,
    click_count INTEGER DEFAULT 0,
    last_engaged_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(subscriber_id, section_slug)
);
CREATE INDEX IF NOT EXISTS idx_interest_sub ON subscriber_interest_profiles(subscriber_id);

CREATE TABLE IF NOT EXISTS trivia_polls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_type TEXT NOT NULL DEFAULT 'trivia' CHECK (question_type IN ('trivia','poll')),
    question_text TEXT NOT NULL,
    options_json TEXT DEFAULT '[]',
    correct_option_index INTEGER DEFAULT -1,
    explanation TEXT DEFAULT '',
    target_issue_id INTEGER REFERENCES issues(id),
    results_issue_id INTEGER REFERENCES issues(id),
    edition_slug TEXT DEFAULT '',
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft','active','closed')),
    closes_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_trivia_issue ON trivia_polls(target_issue_id);
CREATE INDEX IF NOT EXISTS idx_trivia_status ON trivia_polls(status);

CREATE TABLE IF NOT EXISTS trivia_poll_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trivia_poll_id INTEGER NOT NULL REFERENCES trivia_polls(id),
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    selected_option_index INTEGER NOT NULL,
    is_correct INTEGER DEFAULT 0,
    voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(trivia_poll_id, subscriber_id)
);
CREATE INDEX IF NOT EXISTS idx_trivia_votes_poll ON trivia_poll_votes(trivia_poll_id);

CREATE TABLE IF NOT EXISTS trivia_leaderboard (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    correct_count INTEGER DEFAULT 0,
    total_answered INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0,
    score INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(subscriber_id)
);

INSERT OR IGNORE INTO schema_version (version) VALUES (22);
""",
    23: """
-- v23: Growth & monetization — lead magnets, sponsor portal, contests,
--      reader content, referral rewards, newsletter milestones. All INACTIVE.

CREATE TABLE IF NOT EXISTS lead_magnets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL, slug TEXT UNIQUE NOT NULL, description TEXT DEFAULT '',
    edition_slug TEXT DEFAULT '', file_url TEXT DEFAULT '', cover_image_url TEXT DEFAULT '',
    download_count INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS lead_magnet_downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_magnet_id INTEGER NOT NULL REFERENCES lead_magnets(id),
    email TEXT NOT NULL, subscriber_id INTEGER REFERENCES subscribers(id),
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_lm_downloads_magnet ON lead_magnet_downloads(lead_magnet_id);

CREATE TABLE IF NOT EXISTS sponsor_inquiries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL, contact_name TEXT DEFAULT '', contact_email TEXT NOT NULL,
    website TEXT DEFAULT '', budget_range TEXT DEFAULT '', message TEXT DEFAULT '',
    editions_interested TEXT DEFAULT '',
    status TEXT DEFAULT 'new' CHECK (status IN ('new','contacted','qualified','proposal','closed_won','closed_lost')),
    notes TEXT DEFAULT '', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sponsor_inq_status ON sponsor_inquiries(status);

CREATE TABLE IF NOT EXISTS contests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL, description TEXT DEFAULT '', prize_description TEXT DEFAULT '',
    contest_type TEXT DEFAULT 'referral' CHECK (contest_type IN ('referral','vote','submit','share')),
    entry_requirement TEXT DEFAULT '', edition_slug TEXT DEFAULT '',
    start_date TEXT DEFAULT '', end_date TEXT DEFAULT '',
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft','active','closed','awarded')),
    winner_subscriber_id INTEGER REFERENCES subscribers(id), winner_name TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_contests_status ON contests(status);
CREATE TABLE IF NOT EXISTS contest_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contest_id INTEGER NOT NULL REFERENCES contests(id),
    subscriber_id INTEGER REFERENCES subscribers(id), email TEXT DEFAULT '',
    entry_data_json TEXT DEFAULT '{}', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(contest_id, subscriber_id)
);
CREATE INDEX IF NOT EXISTS idx_contest_entries_contest ON contest_entries(contest_id);

CREATE TABLE IF NOT EXISTS reader_contributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER REFERENCES subscribers(id), email TEXT DEFAULT '', name TEXT DEFAULT '',
    content_type TEXT DEFAULT 'hot_take' CHECK (content_type IN ('hot_take','review','tip','question','story')),
    content TEXT DEFAULT '', edition_slug TEXT DEFAULT '',
    status TEXT DEFAULT 'submitted' CHECK (status IN ('submitted','approved','featured','rejected')),
    target_issue_id INTEGER REFERENCES issues(id), featured_in_issue_id INTEGER REFERENCES issues(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_reader_contrib_status ON reader_contributions(status);

CREATE TABLE IF NOT EXISTS referral_rewards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tier_name TEXT NOT NULL, referrals_required INTEGER NOT NULL,
    reward_description TEXT DEFAULT '',
    reward_type TEXT DEFAULT 'badge' CHECK (reward_type IN ('badge','content','feature','merch','custom')),
    is_active INTEGER DEFAULT 1, sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS newsletter_milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_subscribers INTEGER NOT NULL, title TEXT DEFAULT '', description TEXT DEFAULT '',
    unlock_description TEXT DEFAULT '', is_reached INTEGER DEFAULT 0,
    reached_at TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO schema_version (version) VALUES (23);
""",
    24: """
-- v24: Rate limiting table (persists across restarts)
CREATE TABLE IF NOT EXISTS rate_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip_address TEXT NOT NULL,
    limit_type TEXT NOT NULL DEFAULT 'login',
    attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_rate_limits_ip_type ON rate_limits(ip_address, limit_type);

INSERT OR IGNORE INTO schema_version (version) VALUES (24);
""",
    25: """
-- v25: Sponsor block performance tracking events
CREATE TABLE IF NOT EXISTS sponsor_block_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    block_id INTEGER NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('impression','click')),
    subscriber_id INTEGER,
    ip_address TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sponsor_events_block ON sponsor_block_events(block_id);

INSERT OR IGNORE INTO schema_version (version) VALUES (25);
""",
    26: """
-- v26: Paid subscriber tiers, audio newsletter, community forum,
--      advertiser self-serve portal

-- Paid subscriber tiers
CREATE TABLE IF NOT EXISTS subscriber_tiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    price_cents INTEGER DEFAULT 0,
    billing_interval TEXT DEFAULT 'monthly' CHECK (billing_interval IN ('monthly','yearly')),
    features_json TEXT DEFAULT '[]',
    is_active INTEGER DEFAULT 1,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS subscriber_billing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    tier_id INTEGER NOT NULL REFERENCES subscriber_tiers(id),
    stripe_customer_id TEXT DEFAULT '',
    stripe_subscription_id TEXT DEFAULT '',
    status TEXT DEFAULT 'active' CHECK (status IN ('active','cancelled','past_due')),
    current_period_end TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_billing_subscriber ON subscriber_billing(subscriber_id);
CREATE INDEX IF NOT EXISTS idx_billing_stripe ON subscriber_billing(stripe_subscription_id);

-- Audio newsletter
CREATE TABLE IF NOT EXISTS audio_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL REFERENCES issues(id),
    edition_slug TEXT DEFAULT '',
    audio_url TEXT DEFAULT '',
    duration_seconds INTEGER DEFAULT 0,
    file_size_bytes INTEGER DEFAULT 0,
    tts_provider TEXT DEFAULT 'openai',
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending','processing','complete','failed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_audio_issue ON audio_issues(issue_id);

-- Community forum
CREATE TABLE IF NOT EXISTS forum_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    description TEXT DEFAULT '',
    edition_slug TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS forum_threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES forum_categories(id),
    subscriber_id INTEGER REFERENCES subscribers(id),
    title TEXT NOT NULL,
    content TEXT DEFAULT '',
    is_pinned INTEGER DEFAULT 0,
    is_locked INTEGER DEFAULT 0,
    reply_count INTEGER DEFAULT 0,
    last_reply_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_forum_threads_cat ON forum_threads(category_id);

CREATE TABLE IF NOT EXISTS forum_replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER NOT NULL REFERENCES forum_threads(id),
    subscriber_id INTEGER REFERENCES subscribers(id),
    content TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_forum_replies_thread ON forum_replies(thread_id);

-- Advertiser self-serve portal
CREATE TABLE IF NOT EXISTS advertiser_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sponsor_id INTEGER REFERENCES sponsors(id),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS advertiser_campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    advertiser_id INTEGER NOT NULL REFERENCES advertiser_accounts(id),
    name TEXT NOT NULL,
    edition_slug TEXT DEFAULT '',
    position TEXT DEFAULT 'mid',
    headline TEXT DEFAULT '',
    body_html TEXT DEFAULT '',
    cta_url TEXT DEFAULT '',
    cta_text TEXT DEFAULT 'Learn More',
    image_url TEXT DEFAULT '',
    budget_cents INTEGER DEFAULT 0,
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft','submitted','approved','live','completed')),
    start_date TEXT DEFAULT '',
    end_date TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_adv_campaigns_adv ON advertiser_campaigns(advertiser_id);
CREATE INDEX IF NOT EXISTS idx_adv_campaigns_status ON advertiser_campaigns(status);

INSERT OR IGNORE INTO schema_version (version) VALUES (26);
""",
}


def get_current_version(conn) -> int:
    """Return the current schema version from the database.

    Works with both sqlite3.Connection and PgConnection.
    """
    try:
        row = conn.execute("SELECT MAX(version) as v FROM schema_version").fetchone()
        if row is None:
            return 0
        v = row["v"] if isinstance(row, dict) else row["v"]
        return v if v else 0
    except Exception:
        return 0


def _run_v19_beehiiv_to_ghl(conn) -> None:
    """v19: Rename beehiiv columns to ghl — only if old columns exist."""
    # Check if old columns exist before renaming
    cols = {row[1] for row in conn.execute("PRAGMA table_info(assembled_issues)").fetchall()}
    if "beehiiv_post_id" in cols:
        conn.execute("ALTER TABLE assembled_issues RENAME COLUMN beehiiv_post_id TO ghl_campaign_id")
    cols = {row[1] for row in conn.execute("PRAGMA table_info(subscribers)").fetchall()}
    if "beehiiv_id" in cols:
        conn.execute("ALTER TABLE subscribers RENAME COLUMN beehiiv_id TO ghl_contact_id")
    cols = {row[1] for row in conn.execute("PRAGMA table_info(engagement_metrics)").fetchall()}
    if "beehiiv_post_id" in cols:
        conn.execute("ALTER TABLE engagement_metrics RENAME COLUMN beehiiv_post_id TO ghl_campaign_id")
    conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (19)")
    conn.commit()


def run_migrations(db_path: str) -> list[int]:
    """Run all pending SQLite migrations. Returns list of versions applied."""
    conn = get_connection(db_path)
    current = get_current_version(conn)
    applied: list[int] = []

    for version in sorted(MIGRATIONS.keys()):
        if version > current:
            sql = MIGRATIONS[version]
            if sql == "SPECIAL:beehiiv_to_ghl":
                _run_v19_beehiiv_to_ghl(conn)
            else:
                conn.executescript(sql)
            applied.append(version)

    conn.close()
    return applied


# ---------------------------------------------------------------------------
# PostgreSQL migration equivalents
# ---------------------------------------------------------------------------

def _sqlite_to_pg_migration(sql: str) -> str:
    """Convert a SQLite migration to PostgreSQL syntax."""
    import re
    result = sql
    # INTEGER PRIMARY KEY AUTOINCREMENT -> SERIAL PRIMARY KEY
    result = re.sub(
        r'(\w+)\s+INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT',
        r'\1 SERIAL PRIMARY KEY',
        result,
        flags=re.IGNORECASE,
    )
    # INSERT OR IGNORE INTO -> INSERT INTO ... ON CONFLICT DO NOTHING
    result = re.sub(
        r'INSERT\s+OR\s+IGNORE\s+INTO\s+(\w+)',
        r'INSERT INTO \1',
        result,
        flags=re.IGNORECASE,
    )
    # Add ON CONFLICT DO NOTHING to schema_version inserts
    result = re.sub(
        r"(INSERT INTO schema_version \(version\) VALUES \(\d+\))(\s*;)",
        r"\1 ON CONFLICT DO NOTHING\2",
        result,
    )
    return result


# Build PG_MIGRATIONS by converting each SQLite migration
PG_MIGRATIONS: dict[int, str] = {
    version: _sqlite_to_pg_migration(sql)
    for version, sql in MIGRATIONS.items()
    if not sql.startswith("SPECIAL:")
}
# v19: Beehiiv -> GHL column renames (PG syntax)
PG_MIGRATIONS[19] = """
ALTER TABLE assembled_issues RENAME COLUMN beehiiv_post_id TO ghl_campaign_id;
ALTER TABLE subscribers RENAME COLUMN beehiiv_id TO ghl_contact_id;
ALTER TABLE engagement_metrics RENAME COLUMN beehiiv_post_id TO ghl_campaign_id;
INSERT INTO schema_version (version) VALUES (19) ON CONFLICT DO NOTHING;
"""


def run_pg_migrations(database_url: str) -> list[int]:
    """Run all pending PostgreSQL migrations. Returns list of versions applied."""
    from weeklyamp.db.postgres import get_pg_connection
    conn = get_pg_connection(database_url)
    current = get_current_version(conn)
    applied: list[int] = []

    for version in sorted(PG_MIGRATIONS.keys()):
        if version > current:
            conn.executescript(PG_MIGRATIONS[version])
            applied.append(version)

    conn.close()
    return applied
