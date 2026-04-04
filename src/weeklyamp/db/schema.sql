-- TrueFans NEWSLETTERS Database Schema (v10)

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_number INTEGER UNIQUE NOT NULL,
    title TEXT DEFAULT '',
    status TEXT DEFAULT 'planning' CHECK (status IN ('planning','drafting','reviewing','assembled','published')),
    publish_date TIMESTAMP,
    week_id TEXT DEFAULT '',
    send_day TEXT DEFAULT '',
    edition_slug TEXT DEFAULT '',
    issue_template TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS section_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    prompt_template TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    section_type TEXT DEFAULT 'core',
    target_word_count INTEGER DEFAULT 300,
    word_count_label TEXT DEFAULT 'medium',
    suggested_at TIMESTAMP,
    suggested_reason TEXT DEFAULT '',
    last_used_issue_id INTEGER,
    category TEXT DEFAULT '',
    series_type TEXT DEFAULT 'ongoing',
    series_length INTEGER DEFAULT 0,
    series_current INTEGER DEFAULT 0,
    description TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('rss','scrape','manual')),
    url TEXT NOT NULL,
    target_sections TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    last_fetched TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw_content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER REFERENCES sources(id),
    title TEXT DEFAULT '',
    url TEXT DEFAULT '',
    author TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    full_text TEXT DEFAULT '',
    published_at TIMESTAMP,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    relevance_score REAL DEFAULT 0.0,
    matched_sections TEXT DEFAULT '',
    is_used INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS editorial_inputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER REFERENCES issues(id),
    section_slug TEXT NOT NULL,
    topic TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    reference_urls TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL REFERENCES issues(id),
    section_slug TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    content TEXT DEFAULT '',
    ai_model TEXT DEFAULT '',
    prompt_used TEXT DEFAULT '',
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','revised')),
    reviewer_notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS assembled_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL REFERENCES issues(id),
    html_content TEXT DEFAULT '',
    plain_text TEXT DEFAULT '',
    ghl_campaign_id TEXT DEFAULT '',
    assembled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS subscribers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    first_name TEXT DEFAULT '',
    ghl_contact_id TEXT DEFAULT '',
    status TEXT DEFAULT 'active',
    source_channel TEXT DEFAULT '',
    email_verified INTEGER DEFAULT 0,
    verification_token TEXT DEFAULT '',
    unsubscribe_token TEXT DEFAULT '',
    subscribed_at TIMESTAMP,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS engagement_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL REFERENCES issues(id),
    ghl_campaign_id TEXT DEFAULT '',
    sends INTEGER DEFAULT 0,
    opens INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    open_rate REAL DEFAULT 0.0,
    click_rate REAL DEFAULT 0.0,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Section rotation log
CREATE TABLE IF NOT EXISTS section_rotation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL REFERENCES issues(id),
    section_slug TEXT NOT NULL,
    was_included INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Send schedule (multi-frequency publishing)
CREATE TABLE IF NOT EXISTS send_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day_of_week TEXT NOT NULL,
    edition_slug TEXT DEFAULT '',
    label TEXT DEFAULT '',
    section_slugs TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sponsor blocks (ad placements per newsletter edition)
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
    edition_slug TEXT DEFAULT '',
    edition_number INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sponsors directory (CRM)
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

-- Sponsor bookings (linking sponsors to issue slots)
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

-- AI agents
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

-- Agent tasks
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

-- Agent output log
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

-- Guest contacts
CREATE TABLE IF NOT EXISTS guest_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT DEFAULT '',
    organization TEXT DEFAULT '',
    role TEXT DEFAULT '',
    category TEXT DEFAULT '',
    website TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Guest articles
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

-- Artist submissions
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

-- Editorial calendar
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

-- Growth metrics
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

-- Social posts
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

-- Security audit log
CREATE TABLE IF NOT EXISTS security_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    ip_address TEXT DEFAULT '',
    user_agent TEXT DEFAULT '',
    detail TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Newsletter editions
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

-- Edition main sponsors (1 per newsletter x edition = 9 total)
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

-- Subscriber-edition link
CREATE TABLE IF NOT EXISTS subscriber_editions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    edition_id INTEGER NOT NULL REFERENCES newsletter_editions(id),
    send_days TEXT DEFAULT 'monday,wednesday,saturday',
    subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(subscriber_id, edition_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_issues_edition ON issues(edition_slug);
CREATE UNIQUE INDEX IF NOT EXISTS idx_schedule_day_edition ON send_schedule(day_of_week, edition_slug);
CREATE INDEX IF NOT EXISTS idx_drafts_issue_section ON drafts(issue_id, section_slug);
CREATE INDEX IF NOT EXISTS idx_raw_content_source ON raw_content(source_id);
CREATE INDEX IF NOT EXISTS idx_raw_content_used ON raw_content(is_used);
CREATE INDEX IF NOT EXISTS idx_editorial_issue ON editorial_inputs(issue_id);
CREATE INDEX IF NOT EXISTS idx_subscribers_email ON subscribers(email);
CREATE INDEX IF NOT EXISTS idx_rotation_log_issue ON section_rotation_log(issue_id);
CREATE INDEX IF NOT EXISTS idx_sponsor_blocks_issue ON sponsor_blocks(issue_id);
CREATE INDEX IF NOT EXISTS idx_sponsor_blocks_edition ON sponsor_blocks(edition_slug, edition_number);
CREATE INDEX IF NOT EXISTS idx_bookings_sponsor ON sponsor_bookings(sponsor_id);
CREATE INDEX IF NOT EXISTS idx_bookings_issue ON sponsor_bookings(issue_id);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_agent ON agent_tasks(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_state ON agent_tasks(state);
CREATE INDEX IF NOT EXISTS idx_output_log_task ON agent_output_log(task_id);
CREATE INDEX IF NOT EXISTS idx_guest_articles_contact ON guest_articles(contact_id);
CREATE INDEX IF NOT EXISTS idx_guest_articles_issue ON guest_articles(target_issue_id);
CREATE INDEX IF NOT EXISTS idx_submissions_state ON artist_submissions(review_state);
CREATE INDEX IF NOT EXISTS idx_calendar_issue ON editorial_calendar(issue_id);
CREATE INDEX IF NOT EXISTS idx_growth_date ON growth_metrics(metric_date);
CREATE INDEX IF NOT EXISTS idx_social_posts_issue ON social_posts(issue_id);
CREATE INDEX IF NOT EXISTS idx_security_log_event ON security_log(event_type);
CREATE INDEX IF NOT EXISTS idx_security_log_created ON security_log(created_at);
CREATE INDEX IF NOT EXISTS idx_editions_slug ON newsletter_editions(slug);
CREATE INDEX IF NOT EXISTS idx_sub_editions_subscriber ON subscriber_editions(subscriber_id);
CREATE INDEX IF NOT EXISTS idx_sub_editions_edition ON subscriber_editions(edition_id);

-- Schema version
INSERT OR IGNORE INTO schema_version (version) VALUES (1);
INSERT OR IGNORE INTO schema_version (version) VALUES (2);
INSERT OR IGNORE INTO schema_version (version) VALUES (3);
INSERT OR IGNORE INTO schema_version (version) VALUES (4);
INSERT OR IGNORE INTO schema_version (version) VALUES (5);
INSERT OR IGNORE INTO schema_version (version) VALUES (6);
INSERT OR IGNORE INTO schema_version (version) VALUES (7);
INSERT OR IGNORE INTO schema_version (version) VALUES (8);
INSERT OR IGNORE INTO schema_version (version) VALUES (9);
INSERT OR IGNORE INTO schema_version (version) VALUES (10);
INSERT OR IGNORE INTO schema_version (version) VALUES (11);
INSERT OR IGNORE INTO schema_version (version) VALUES (12);
INSERT OR IGNORE INTO schema_version (version) VALUES (13);
INSERT OR IGNORE INTO schema_version (version) VALUES (14);
INSERT OR IGNORE INTO schema_version (version) VALUES (15);
INSERT OR IGNORE INTO schema_version (version) VALUES (16);
INSERT OR IGNORE INTO schema_version (version) VALUES (17);
INSERT OR IGNORE INTO schema_version (version) VALUES (18);
INSERT OR IGNORE INTO schema_version (version) VALUES (19);
INSERT OR IGNORE INTO schema_version (version) VALUES (20);

-- Editor articles — direct editor-written content
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

-- ======================================================================
-- v21+: Advanced newsletter features (inactive by default)
-- ======================================================================

-- Email open/click tracking events
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

-- A/B tests for subject lines, content, send times
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

-- A/B test per-variant results
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

-- Email bounce log for deliverability management
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

-- Domain warm-up tracking
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

-- Scheduled sends (deferred publishing)
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

-- Webhooks for inbound/outbound integrations
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

-- Webhook delivery log
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

-- Referral system
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

-- Subscriber preferences (extends subscriber_editions with richer controls)
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

-- Welcome sequence (automated drip emails for new subscribers)
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

-- Re-engagement tracking
CREATE TABLE IF NOT EXISTS reengagement_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    campaign_type TEXT DEFAULT 'winback' CHECK (campaign_type IN ('winback','survey','last_chance')),
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    opened INTEGER DEFAULT 0,
    clicked INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_reengagement_sub ON reengagement_log(subscriber_id);

-- Reusable content blocks (snippets for sponsor blocks, CTAs, boilerplate)
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

-- User roles for team access control
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

-- Export/backup log
CREATE TABLE IF NOT EXISTS export_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    export_type TEXT NOT NULL CHECK (export_type IN ('subscribers','content','config','full_backup')),
    file_path TEXT DEFAULT '',
    file_size_bytes INTEGER DEFAULT 0,
    record_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Send time optimization per subscriber
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

-- ======================================================================
-- v22: Music-specific features (Spotify, artist profiles, genres,
--      section engagement, trivia/polls)
-- ======================================================================

-- Spotify artist data cache
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

-- Spotify new releases tracking
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

-- Audio embeds attached to drafts/issues
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

-- Artist profile pages
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

-- Artist follower relationships
CREATE TABLE IF NOT EXISTS artist_followers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    artist_profile_id INTEGER NOT NULL REFERENCES artist_profiles(id),
    followed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(subscriber_id, artist_profile_id)
);
CREATE INDEX IF NOT EXISTS idx_artist_followers_artist ON artist_followers(artist_profile_id);

-- Track which issues featured which artists
CREATE TABLE IF NOT EXISTS artist_newsletter_features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artist_profile_id INTEGER NOT NULL REFERENCES artist_profiles(id),
    issue_id INTEGER NOT NULL REFERENCES issues(id),
    section_slug TEXT DEFAULT '',
    draft_id INTEGER REFERENCES drafts(id),
    featured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_artist_features_artist ON artist_newsletter_features(artist_profile_id);

-- Subscriber genre preferences
CREATE TABLE IF NOT EXISTS subscriber_genres (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    genre TEXT NOT NULL,
    priority INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(subscriber_id, genre)
);
CREATE INDEX IF NOT EXISTS idx_sub_genres_sub ON subscriber_genres(subscriber_id);

-- Section-to-genre mapping for content relevance
CREATE TABLE IF NOT EXISTS section_genres (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section_slug TEXT NOT NULL,
    genre TEXT NOT NULL,
    relevance_weight REAL DEFAULT 1.0,
    UNIQUE(section_slug, genre)
);
CREATE INDEX IF NOT EXISTS idx_section_genres_slug ON section_genres(section_slug);

-- Section-level engagement events (extends email tracking)
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

-- Aggregated section engagement scores per issue
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

-- Per-subscriber interest profile built from engagement
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

-- Music trivia & polls
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

-- Individual votes on trivia/polls
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

-- Trivia leaderboard (running totals)
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

-- ======================================================================
-- v23: Growth & monetization — lead magnets, sponsor portal, contests,
--      reader content, referral rewards
-- ======================================================================

-- Lead magnets (gated downloads to drive signups)
CREATE TABLE IF NOT EXISTS lead_magnets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    description TEXT DEFAULT '',
    edition_slug TEXT DEFAULT '',
    file_url TEXT DEFAULT '',
    cover_image_url TEXT DEFAULT '',
    download_count INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lead_magnet_downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_magnet_id INTEGER NOT NULL REFERENCES lead_magnets(id),
    email TEXT NOT NULL,
    subscriber_id INTEGER REFERENCES subscribers(id),
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_lm_downloads_magnet ON lead_magnet_downloads(lead_magnet_id);

-- Sponsor inquiries (public application form)
CREATE TABLE IF NOT EXISTS sponsor_inquiries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    contact_name TEXT DEFAULT '',
    contact_email TEXT NOT NULL,
    website TEXT DEFAULT '',
    budget_range TEXT DEFAULT '',
    message TEXT DEFAULT '',
    editions_interested TEXT DEFAULT '',
    status TEXT DEFAULT 'new' CHECK (status IN ('new','contacted','qualified','proposal','closed_won','closed_lost')),
    notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sponsor_inq_status ON sponsor_inquiries(status);

-- Contests and giveaways
CREATE TABLE IF NOT EXISTS contests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    prize_description TEXT DEFAULT '',
    contest_type TEXT DEFAULT 'referral' CHECK (contest_type IN ('referral','vote','submit','share')),
    entry_requirement TEXT DEFAULT '',
    edition_slug TEXT DEFAULT '',
    start_date TEXT DEFAULT '',
    end_date TEXT DEFAULT '',
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft','active','closed','awarded')),
    winner_subscriber_id INTEGER REFERENCES subscribers(id),
    winner_name TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_contests_status ON contests(status);

CREATE TABLE IF NOT EXISTS contest_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contest_id INTEGER NOT NULL REFERENCES contests(id),
    subscriber_id INTEGER REFERENCES subscribers(id),
    email TEXT DEFAULT '',
    entry_data_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(contest_id, subscriber_id)
);
CREATE INDEX IF NOT EXISTS idx_contest_entries_contest ON contest_entries(contest_id);

-- Reader-submitted content (hot takes, reviews, tips)
CREATE TABLE IF NOT EXISTS reader_contributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER REFERENCES subscribers(id),
    email TEXT DEFAULT '',
    name TEXT DEFAULT '',
    content_type TEXT DEFAULT 'hot_take' CHECK (content_type IN ('hot_take','review','tip','question','story')),
    content TEXT DEFAULT '',
    edition_slug TEXT DEFAULT '',
    status TEXT DEFAULT 'submitted' CHECK (status IN ('submitted','approved','featured','rejected')),
    target_issue_id INTEGER REFERENCES issues(id),
    featured_in_issue_id INTEGER REFERENCES issues(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_reader_contrib_status ON reader_contributions(status);

-- Referral reward tiers
CREATE TABLE IF NOT EXISTS referral_rewards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tier_name TEXT NOT NULL,
    referrals_required INTEGER NOT NULL,
    reward_description TEXT DEFAULT '',
    reward_type TEXT DEFAULT 'badge' CHECK (reward_type IN ('badge','content','feature','merch','custom')),
    is_active INTEGER DEFAULT 1,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Newsletter milestones (public goals)
CREATE TABLE IF NOT EXISTS newsletter_milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_subscribers INTEGER NOT NULL,
    title TEXT DEFAULT '',
    description TEXT DEFAULT '',
    unlock_description TEXT DEFAULT '',
    is_reached INTEGER DEFAULT 0,
    reached_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO schema_version (version) VALUES (23);

-- Rate limiting (persists across restarts)
CREATE TABLE IF NOT EXISTS rate_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip_address TEXT NOT NULL,
    limit_type TEXT NOT NULL DEFAULT 'login',
    attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_rate_limits_ip_type ON rate_limits(ip_address, limit_type);

INSERT OR IGNORE INTO schema_version (version) VALUES (24);

-- Sponsor block performance tracking events
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

-- ======================================================================
-- v26: Paid subscriber tiers, audio newsletter, community forum,
--      advertiser self-serve portal
-- ======================================================================

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

-- v27: Affiliate program management
CREATE TABLE IF NOT EXISTS affiliate_programs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    website_url TEXT DEFAULT '',
    affiliate_url TEXT DEFAULT '',
    commission_type TEXT DEFAULT 'percentage' CHECK (commission_type IN ('percentage','flat','recurring')),
    commission_rate TEXT DEFAULT '',
    cookie_days INTEGER DEFAULT 30,
    category TEXT DEFAULT 'general' CHECK (category IN ('distribution','gear','education','software','services','streaming','marketing','general')),
    target_editions TEXT DEFAULT '',
    description TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    total_clicks INTEGER DEFAULT 0,
    total_conversions INTEGER DEFAULT 0,
    total_revenue_cents INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS affiliate_placements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    affiliate_id INTEGER NOT NULL REFERENCES affiliate_programs(id),
    issue_id INTEGER REFERENCES issues(id),
    edition_slug TEXT DEFAULT '',
    section_slug TEXT DEFAULT '',
    placement_type TEXT DEFAULT 'inline' CHECK (placement_type IN ('inline','block','cta')),
    anchor_text TEXT DEFAULT '',
    clicks INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_affiliate_placements_issue ON affiliate_placements(issue_id);

INSERT OR IGNORE INTO schema_version (version) VALUES (27);

-- v28: Market editions, artist newsletters, mobile app waitlist

CREATE TABLE IF NOT EXISTS edition_markets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    edition_slug TEXT NOT NULL,
    market_slug TEXT NOT NULL,
    market_name TEXT NOT NULL,
    description TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(edition_slug, market_slug)
);
CREATE INDEX IF NOT EXISTS idx_edition_markets_edition ON edition_markets(edition_slug);

CREATE TABLE IF NOT EXISTS artist_newsletters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artist_profile_id INTEGER REFERENCES artist_profiles(id),
    artist_name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    brand_color TEXT DEFAULT '#e8645a',
    logo_url TEXT DEFAULT '',
    tagline TEXT DEFAULT '',
    template_style TEXT DEFAULT 'default',
    schedule TEXT DEFAULT 'monthly',
    subscriber_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'waitlist' CHECK (status IN ('waitlist','setup','active','paused')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS artist_newsletter_waitlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artist_name TEXT NOT NULL,
    email TEXT NOT NULL,
    website TEXT DEFAULT '',
    social_links TEXT DEFAULT '',
    genre TEXT DEFAULT '',
    fan_count TEXT DEFAULT '',
    message TEXT DEFAULT '',
    status TEXT DEFAULT 'new' CHECK (status IN ('new','contacted','approved','rejected')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mobile_app_waitlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    platform TEXT DEFAULT 'both' CHECK (platform IN ('ios','android','both')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO schema_version (version) VALUES (28);

-- v29: Admin users for multi-user role management
CREATE TABLE IF NOT EXISTS admin_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT DEFAULT '',
    role TEXT DEFAULT 'viewer' CHECK (role IN ('admin','editor','reviewer','viewer')),
    is_active INTEGER DEFAULT 1,
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_admin_users_email ON admin_users(email);

INSERT OR IGNORE INTO schema_version (version) VALUES (29);

-- v30: Licensing infrastructure for city editions

CREATE TABLE IF NOT EXISTS licensees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    contact_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    phone TEXT DEFAULT '',
    website TEXT DEFAULT '',
    city_market_slug TEXT DEFAULT '',
    edition_slugs TEXT DEFAULT '',
    license_type TEXT DEFAULT 'monthly' CHECK (license_type IN ('monthly','annual','trial')),
    license_fee_cents INTEGER DEFAULT 0,
    revenue_share_pct REAL DEFAULT 20.0,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending','approved','active','suspended','cancelled')),
    trial_ends_at TIMESTAMP,
    activated_at TIMESTAMP,
    notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_licensees_email ON licensees(email);
CREATE INDEX IF NOT EXISTS idx_licensees_status ON licensees(status);

CREATE TABLE IF NOT EXISTS license_revenue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    licensee_id INTEGER NOT NULL REFERENCES licensees(id),
    month TEXT NOT NULL,
    sponsor_revenue_cents INTEGER DEFAULT 0,
    affiliate_revenue_cents INTEGER DEFAULT 0,
    subscriber_revenue_cents INTEGER DEFAULT 0,
    platform_share_cents INTEGER DEFAULT 0,
    licensee_share_cents INTEGER DEFAULT 0,
    status TEXT DEFAULT 'calculated' CHECK (status IN ('calculated','invoiced','paid')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_license_revenue_licensee ON license_revenue(licensee_id);

INSERT OR IGNORE INTO schema_version (version) VALUES (30);

-- v31: Artist newsletter product — subscriber lists, issues, templates

CREATE TABLE IF NOT EXISTS artist_newsletter_subscribers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    newsletter_id INTEGER NOT NULL REFERENCES artist_newsletters(id),
    email TEXT NOT NULL,
    first_name TEXT DEFAULT '',
    status TEXT DEFAULT 'active' CHECK (status IN ('active','unsubscribed')),
    subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(newsletter_id, email)
);
CREATE INDEX IF NOT EXISTS idx_artist_nl_subs_newsletter ON artist_newsletter_subscribers(newsletter_id);

CREATE TABLE IF NOT EXISTS artist_newsletter_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    newsletter_id INTEGER NOT NULL REFERENCES artist_newsletters(id),
    issue_number INTEGER DEFAULT 1,
    subject TEXT NOT NULL,
    html_content TEXT DEFAULT '',
    plain_text TEXT DEFAULT '',
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft','scheduled','sent')),
    scheduled_at TIMESTAMP,
    sent_at TIMESTAMP,
    opens INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_artist_nl_issues ON artist_newsletter_issues(newsletter_id);

CREATE TABLE IF NOT EXISTS artist_newsletter_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    html_template TEXT DEFAULT '',
    preview_image_url TEXT DEFAULT '',
    is_default INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO schema_version (version) VALUES (31);

-- v32: Marketing campaigns and outreach tracking

CREATE TABLE IF NOT EXISTS marketing_campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    campaign_type TEXT NOT NULL CHECK (campaign_type IN ('subscriber_growth','sponsor_outreach','retention','reactivation','upsell','event')),
    channel TEXT DEFAULT 'email' CHECK (channel IN ('email','sms','voice','ai_agent','social','multi')),
    target_audience TEXT DEFAULT '',
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft','scheduled','active','paused','completed','cancelled')),
    goal_description TEXT DEFAULT '',
    goal_target INTEGER DEFAULT 0,
    goal_achieved INTEGER DEFAULT 0,
    template_content TEXT DEFAULT '',
    ghl_workflow_id TEXT DEFAULT '',
    ghl_campaign_id TEXT DEFAULT '',
    scheduled_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_by TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_marketing_campaigns_type ON marketing_campaigns(campaign_type);
CREATE INDEX IF NOT EXISTS idx_marketing_campaigns_status ON marketing_campaigns(status);

CREATE TABLE IF NOT EXISTS marketing_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    template_type TEXT NOT NULL CHECK (template_type IN ('email','sms','voice_script','ai_prompt','social_post','landing_page')),
    category TEXT DEFAULT 'general' CHECK (category IN ('subscriber_growth','sponsor_outreach','retention','upsell','event','general')),
    subject TEXT DEFAULT '',
    content TEXT DEFAULT '',
    variables TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS outreach_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER REFERENCES marketing_campaigns(id),
    channel TEXT DEFAULT 'email',
    recipient_email TEXT DEFAULT '',
    recipient_phone TEXT DEFAULT '',
    recipient_name TEXT DEFAULT '',
    recipient_type TEXT DEFAULT 'subscriber' CHECK (recipient_type IN ('subscriber','sponsor_prospect','licensee_prospect','artist','partner')),
    status TEXT DEFAULT 'sent' CHECK (status IN ('queued','sent','delivered','opened','clicked','replied','converted','failed','bounced')),
    ghl_contact_id TEXT DEFAULT '',
    response_notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_outreach_campaign ON outreach_log(campaign_id);
CREATE INDEX IF NOT EXISTS idx_outreach_status ON outreach_log(status);

CREATE TABLE IF NOT EXISTS sponsor_prospects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    contact_name TEXT DEFAULT '',
    contact_email TEXT DEFAULT '',
    contact_phone TEXT DEFAULT '',
    website TEXT DEFAULT '',
    category TEXT DEFAULT 'general',
    target_editions TEXT DEFAULT '',
    estimated_budget TEXT DEFAULT '',
    status TEXT DEFAULT 'identified' CHECK (status IN ('identified','researching','contacted','meeting','proposal','negotiating','closed_won','closed_lost')),
    source TEXT DEFAULT 'manual',
    last_contacted_at TIMESTAMP,
    next_followup_at TIMESTAMP,
    notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sponsor_prospects_status ON sponsor_prospects(status);

INSERT OR IGNORE INTO schema_version (version) VALUES (32);
