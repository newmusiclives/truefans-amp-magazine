-- TrueFans NEWSLETTERS Database Schema (PostgreSQL, v14)

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS issues (
    id SERIAL PRIMARY KEY,
    issue_number INTEGER UNIQUE NOT NULL,
    title TEXT DEFAULT '',
    status TEXT DEFAULT 'planning' CHECK (status IN ('planning','drafting','reviewing','assembled','published')),
    publish_date TIMESTAMP,
    week_id TEXT DEFAULT '',
    send_day TEXT DEFAULT '',
    issue_template TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS section_definitions (
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('rss','scrape','manual')),
    url TEXT NOT NULL,
    target_sections TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    last_fetched TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw_content (
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
    issue_id INTEGER REFERENCES issues(id),
    section_slug TEXT NOT NULL,
    topic TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    reference_urls TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS drafts (
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
    issue_id INTEGER NOT NULL REFERENCES issues(id),
    html_content TEXT DEFAULT '',
    plain_text TEXT DEFAULT '',
    ghl_campaign_id TEXT DEFAULT '',
    assembled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS subscribers (
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
    issue_id INTEGER NOT NULL REFERENCES issues(id),
    section_slug TEXT NOT NULL,
    was_included INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Send schedule (multi-frequency publishing)
CREATE TABLE IF NOT EXISTS send_schedule (
    id SERIAL PRIMARY KEY,
    day_of_week TEXT NOT NULL,
    label TEXT DEFAULT '',
    section_slugs TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sponsor blocks (ad placements per issue)
CREATE TABLE IF NOT EXISTS sponsor_blocks (
    id SERIAL PRIMARY KEY,
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

-- Sponsors directory (CRM)
CREATE TABLE IF NOT EXISTS sponsors (
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    ip_address TEXT DEFAULT '',
    user_agent TEXT DEFAULT '',
    detail TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Newsletter editions
CREATE TABLE IF NOT EXISTS newsletter_editions (
    id SERIAL PRIMARY KEY,
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

-- Subscriber-edition link
CREATE TABLE IF NOT EXISTS subscriber_editions (
    id SERIAL PRIMARY KEY,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    edition_id INTEGER NOT NULL REFERENCES newsletter_editions(id),
    send_days TEXT DEFAULT 'monday,wednesday,saturday',
    subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(subscriber_id, edition_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_drafts_issue_section ON drafts(issue_id, section_slug);
CREATE INDEX IF NOT EXISTS idx_raw_content_source ON raw_content(source_id);
CREATE INDEX IF NOT EXISTS idx_raw_content_used ON raw_content(is_used);
CREATE INDEX IF NOT EXISTS idx_editorial_issue ON editorial_inputs(issue_id);
CREATE INDEX IF NOT EXISTS idx_subscribers_email ON subscribers(email);
CREATE INDEX IF NOT EXISTS idx_rotation_log_issue ON section_rotation_log(issue_id);
CREATE INDEX IF NOT EXISTS idx_sponsor_blocks_issue ON sponsor_blocks(issue_id);
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
INSERT INTO schema_version (version) VALUES (1) ON CONFLICT DO NOTHING;
INSERT INTO schema_version (version) VALUES (2) ON CONFLICT DO NOTHING;
INSERT INTO schema_version (version) VALUES (3) ON CONFLICT DO NOTHING;
INSERT INTO schema_version (version) VALUES (4) ON CONFLICT DO NOTHING;
INSERT INTO schema_version (version) VALUES (5) ON CONFLICT DO NOTHING;
INSERT INTO schema_version (version) VALUES (6) ON CONFLICT DO NOTHING;
INSERT INTO schema_version (version) VALUES (7) ON CONFLICT DO NOTHING;
INSERT INTO schema_version (version) VALUES (8) ON CONFLICT DO NOTHING;
INSERT INTO schema_version (version) VALUES (9) ON CONFLICT DO NOTHING;
INSERT INTO schema_version (version) VALUES (10) ON CONFLICT DO NOTHING;
INSERT INTO schema_version (version) VALUES (11) ON CONFLICT DO NOTHING;
INSERT INTO schema_version (version) VALUES (12) ON CONFLICT DO NOTHING;
INSERT INTO schema_version (version) VALUES (13) ON CONFLICT DO NOTHING;
INSERT INTO schema_version (version) VALUES (14) ON CONFLICT DO NOTHING;
INSERT INTO schema_version (version) VALUES (15) ON CONFLICT DO NOTHING;
INSERT INTO schema_version (version) VALUES (16) ON CONFLICT DO NOTHING;
INSERT INTO schema_version (version) VALUES (17) ON CONFLICT DO NOTHING;
INSERT INTO schema_version (version) VALUES (18) ON CONFLICT DO NOTHING;
INSERT INTO schema_version (version) VALUES (19) ON CONFLICT DO NOTHING;
INSERT INTO schema_version (version) VALUES (20) ON CONFLICT DO NOTHING;

-- Editor articles
CREATE TABLE IF NOT EXISTS editor_articles (
    id SERIAL PRIMARY KEY,
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

-- Rate limiting (persists across restarts)
CREATE TABLE IF NOT EXISTS rate_limits (
    id SERIAL PRIMARY KEY,
    ip_address TEXT NOT NULL,
    limit_type TEXT NOT NULL DEFAULT 'login',
    attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_rate_limits_ip_type ON rate_limits(ip_address, limit_type);

-- Sponsor block performance tracking events
CREATE TABLE IF NOT EXISTS sponsor_block_events (
    id SERIAL PRIMARY KEY,
    block_id INTEGER NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('impression','click')),
    subscriber_id INTEGER,
    ip_address TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sponsor_events_block ON sponsor_block_events(block_id);

-- v26: Paid subscriber tiers, audio newsletter, community forum,
--      advertiser self-serve portal

-- Paid subscriber tiers
CREATE TABLE IF NOT EXISTS subscriber_tiers (
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    description TEXT DEFAULT '',
    edition_slug TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS forum_threads (
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
    thread_id INTEGER NOT NULL REFERENCES forum_threads(id),
    subscriber_id INTEGER REFERENCES subscribers(id),
    content TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_forum_replies_thread ON forum_replies(thread_id);

-- Advertiser self-serve portal
CREATE TABLE IF NOT EXISTS advertiser_accounts (
    id SERIAL PRIMARY KEY,
    sponsor_id INTEGER REFERENCES sponsors(id),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS advertiser_campaigns (
    id SERIAL PRIMARY KEY,
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

-- v27: Affiliate program management
CREATE TABLE IF NOT EXISTS affiliate_programs (
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
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

-- v28: Market editions, artist newsletters, mobile app waitlist

CREATE TABLE IF NOT EXISTS edition_markets (
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    platform TEXT DEFAULT 'both' CHECK (platform IN ('ios','android','both')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO schema_version (version) VALUES (28) ON CONFLICT DO NOTHING;
