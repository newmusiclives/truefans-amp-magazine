"""SQLite connection manager and migration runner."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

_SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"


def get_connection(db_path: str) -> sqlite3.Connection:
    """Return a SQLite connection with WAL mode and foreign keys enabled."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_database(db_path: str) -> None:
    """Run the schema SQL to create all tables, then apply any pending migrations."""
    conn = get_connection(db_path)
    schema_sql = _SCHEMA_PATH.read_text()
    conn.executescript(schema_sql)
    conn.close()

    # Run migrations for existing databases that need schema updates
    from weeklyamp.db.migrations import run_migrations
    run_migrations(db_path)


def get_schema_version(db_path: str) -> Optional[int]:
    """Return the current schema version, or None if DB doesn't exist."""
    path = Path(db_path)
    if not path.exists():
        return None
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT MAX(version) as v FROM schema_version"
        ).fetchone()
        return row["v"] if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


# Default section definitions to seed on init
# (slug, display_name, sort_order, section_type, word_count_label, target_word_count, category, series_type, series_length, description)
DEFAULT_SECTIONS = [
    # Music Industry (sort 10-19)
    ("backstage_pass", "BACKSTAGE PASS", 10, "core", "long", 700, "music_industry", "ongoing", 0, "Deep-dive narratives about iconic artist journeys"),
    ("industry_pulse", "INDUSTRY PULSE", 11, "rotating", "medium", 400, "music_industry", "ongoing", 0, "Latest music industry news and trends"),
    ("deal_or_no_deal", "DEAL OR NO DEAL", 12, "rotating", "medium", 400, "music_industry", "medium", 6, "Record deal analysis and negotiation insights"),
    ("streaming_dashboard", "STREAMING DASHBOARD", 13, "rotating", "short", 150, "music_industry", "ongoing", 0, "Streaming platform stats and insights"),
    # Artist Development (sort 20-29)
    ("coaching", "COACHING", 20, "core", "medium", 400, "artist_development", "ongoing", 0, "Inspiration and actionable advice for artists"),
    ("greatest_songwriters", "100 GREATEST SINGER SONGWRITERS", 21, "core", "medium", 400, "artist_development", "ongoing", 0, "Profiles of legendary singer-songwriters"),
    ("stage_ready", "STAGE READY", 22, "rotating", "medium", 400, "artist_development", "medium", 6, "Live performance tips and stage presence"),
    ("songcraft", "SONGCRAFT", 23, "rotating", "medium", 400, "artist_development", "ongoing", 0, "Songwriting techniques and creative process"),
    ("vocal_booth", "VOCAL BOOTH", 24, "rotating", "medium", 300, "artist_development", "short", 3, "Vocal training and singing technique tips"),
    ("artist_spotlight", "ARTIST SPOTLIGHT", 25, "rotating", "long", 700, "artist_development", "ongoing", 0, "Featured independent artist profiles"),
    # Technology (sort 30-39)
    ("tech_talk", "TECH TALK", 30, "core", "medium", 300, "technology", "ongoing", 0, "Music tech tools and digital strategies"),
    ("ai_music_lab", "AI & MUSIC LAB", 31, "rotating", "medium", 400, "technology", "ongoing", 0, "AI applications in music creation and business"),
    ("gear_garage", "GEAR GARAGE", 32, "rotating", "medium", 300, "technology", "short", 3, "Instrument and gear reviews for indie artists"),
    ("social_playbook", "SOCIAL PLAYBOOK", 33, "rotating", "medium", 400, "technology", "medium", 6, "Social media strategy for musicians"),
    ("production_notes", "PRODUCTION NOTES", 34, "rotating", "medium", 400, "technology", "ongoing", 0, "Recording and production techniques"),
    # Business (sort 40-49)
    ("recommends", "RECOMMENDS", 40, "core", "short", 150, "business", "ongoing", 0, "Curated tools, books, and resources"),
    ("money_moves", "MONEY MOVES", 41, "rotating", "medium", 400, "business", "ongoing", 0, "Revenue strategies and financial literacy for artists"),
    ("brand_building", "BRAND BUILDING", 42, "rotating", "medium", 400, "business", "medium", 6, "Artist branding and identity development"),
    ("rights_and_royalties", "RIGHTS & ROYALTIES", 43, "rotating", "medium", 400, "business", "short", 3, "Music rights, licensing, and royalty education"),
    ("diy_marketing", "DIY MARKETING", 44, "rotating", "medium", 400, "business", "ongoing", 0, "Marketing tactics for independent artists"),
    # Inspiration (sort 50-59)
    ("mondegreen", "MONDEGREEN", 50, "core", "medium", 300, "inspiration", "ongoing", 0, "Misheard lyrics and song meaning deep-dives"),
    ("ps_from_ps", "PS FROM PS", 51, "core", "short", 125, "inspiration", "ongoing", 0, "Personal sign-off and reflection"),
    ("creative_fuel", "CREATIVE FUEL", 52, "rotating", "short", 150, "inspiration", "ongoing", 0, "Quick creative prompts and inspiration"),
    ("vinyl_vault", "VINYL VAULT", 53, "rotating", "medium", 400, "inspiration", "ongoing", 0, "Classic album retrospectives and hidden gems"),
    ("the_muse", "THE MUSE", 54, "rotating", "medium", 400, "inspiration", "short", 3, "Stories of creative breakthroughs and inspiration"),
    ("lyrics_unpacked", "LYRICS UNPACKED", 55, "rotating", "medium", 400, "inspiration", "ongoing", 0, "Deep lyric analysis and interpretation"),
    # Community (sort 60-69)
    ("fan_mail", "FAN MAIL", 60, "rotating", "short", 200, "community", "ongoing", 0, "Reader letters, questions, and shout-outs"),
    ("truefans_connect", "TRUEFANS CONNECT", 61, "rotating", "medium", 400, "community", "ongoing", 0, "Community highlights and TrueFans platform news"),
    ("community_wins", "COMMUNITY WINS", 62, "rotating", "short", 200, "community", "ongoing", 0, "Celebrating reader and community achievements"),
    # Guest Content (sort 70-79)
    ("guest_column", "GUEST COLUMN", 70, "rotating", "long", 800, "guest_content", "ongoing", 0, "Guest articles from industry experts"),
]


def seed_sections(db_path: str) -> int:
    """Insert default section definitions. Returns count of newly inserted."""
    conn = get_connection(db_path)
    inserted = 0
    for entry in DEFAULT_SECTIONS:
        slug, display_name, sort_order, section_type, wc_label, target_wc, category, series_type, series_length, description = entry
        try:
            conn.execute(
                """INSERT INTO section_definitions
                   (slug, display_name, sort_order, section_type, word_count_label,
                    target_word_count, category, series_type, series_length, description)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (slug, display_name, sort_order, section_type, wc_label,
                 target_wc, category, series_type, series_length, description),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            pass  # already exists
    conn.commit()
    conn.close()
    return inserted
