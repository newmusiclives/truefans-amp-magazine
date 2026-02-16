-- TrueFans AMP Magazine Database Schema (v10)

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
    beehiiv_post_id TEXT DEFAULT '',
    assembled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS subscribers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    beehiiv_id TEXT DEFAULT '',
    status TEXT DEFAULT 'active',
    subscribed_at TIMESTAMP,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS engagement_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL REFERENCES issues(id),
    beehiiv_post_id TEXT DEFAULT '',
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
    label TEXT DEFAULT '',
    section_slugs TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sponsor blocks (ad placements per issue)
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
    agent_type TEXT NOT NULL CHECK (agent_type IN ('editor_in_chief','writer','researcher','sales','growth')),
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
