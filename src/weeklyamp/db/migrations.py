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
    agent_type TEXT NOT NULL CHECK (agent_type IN ('editor_in_chief','editor','writer','researcher','sales','growth')),
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


def run_migrations(db_path: str) -> list[int]:
    """Run all pending SQLite migrations. Returns list of versions applied."""
    conn = get_connection(db_path)
    current = get_current_version(conn)
    applied: list[int] = []

    for version in sorted(MIGRATIONS.keys()):
        if version > current:
            conn.executescript(MIGRATIONS[version])
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
}


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
