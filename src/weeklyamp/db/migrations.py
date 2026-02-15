"""Schema migration runner for WEEKLYAMP database."""

from __future__ import annotations

import sqlite3
from typing import Optional

from weeklyamp.core.database import get_connection

# Migrations keyed by target version number.
# Each migration runs SQL to advance from (version - 1) to version.
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
    agent_type TEXT NOT NULL CHECK (agent_type IN ('editor_in_chief','writer','researcher','sales','growth')),
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
}


def get_current_version(conn: sqlite3.Connection) -> int:
    """Return the current schema version from the database."""
    try:
        row = conn.execute("SELECT MAX(version) as v FROM schema_version").fetchone()
        return row["v"] if row and row["v"] else 0
    except sqlite3.OperationalError:
        return 0


def run_migrations(db_path: str) -> list[int]:
    """Run all pending migrations. Returns list of versions applied."""
    conn = get_connection(db_path)
    current = get_current_version(conn)
    applied: list[int] = []

    for version in sorted(MIGRATIONS.keys()):
        if version > current:
            conn.executescript(MIGRATIONS[version])
            applied.append(version)

    conn.close()
    return applied
