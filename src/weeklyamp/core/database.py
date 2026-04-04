"""Database connection manager and migration runner.

Supports both SQLite (default) and PostgreSQL backends.  The active backend
is chosen by the ``WEEKLYAMP_DB_BACKEND`` env-var / config field.
"""

from __future__ import annotations

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)
from pathlib import Path
from typing import Optional, Union

_SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"

# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

def _get_backend() -> str:
    """Return 'sqlite' or 'postgres' based on env / default."""
    return os.getenv("WEEKLYAMP_DB_BACKEND", "sqlite").lower()


# ---------------------------------------------------------------------------
# SQLite helpers (original behaviour)
# ---------------------------------------------------------------------------

def get_sqlite_connection(db_path: str) -> sqlite3.Connection:
    """Return a SQLite connection with WAL mode and foreign keys enabled."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Unified interface used by Repository / migrations / seed functions
# ---------------------------------------------------------------------------

def get_connection(db_path: str = "", database_url: str = "", backend: str = ""):
    """Return a connection for the active backend.

    Parameters are optional — when omitted the function falls back to
    env-vars (``WEEKLYAMP_DB_BACKEND``, ``WEEKLYAMP_DATABASE_URL``,
    ``WEEKLYAMP_DB_PATH``).

    For SQLite the return type is ``sqlite3.Connection``.
    For PostgreSQL it is ``weeklyamp.db.postgres.PgConnection``.
    """
    backend = backend or _get_backend()

    if backend == "postgres":
        url = database_url or os.getenv("WEEKLYAMP_DATABASE_URL", "")
        if not url:
            raise RuntimeError(
                "WEEKLYAMP_DATABASE_URL must be set when using the postgres backend"
            )
        from weeklyamp.db.postgres import get_pg_connection
        return get_pg_connection(url)

    # Default: sqlite
    path = db_path or os.getenv("WEEKLYAMP_DB_PATH", "data/weeklyamp.db")
    return get_sqlite_connection(path)


def init_database(db_path: str = "", database_url: str = "", backend: str = "") -> None:
    """Run the schema SQL to create all tables, then apply pending migrations."""
    backend = backend or _get_backend()

    if backend == "postgres":
        url = database_url or os.getenv("WEEKLYAMP_DATABASE_URL", "")
        from weeklyamp.db.postgres import init_pg_database
        init_pg_database(url)
        return

    # Default: sqlite
    path = db_path or os.getenv("WEEKLYAMP_DB_PATH", "data/weeklyamp.db")
    conn = get_sqlite_connection(path)
    schema_sql = _SCHEMA_PATH.read_text()
    conn.executescript(schema_sql)
    conn.close()

    # Run migrations for existing databases that need schema updates
    from weeklyamp.db.migrations import run_migrations
    run_migrations(path)


def get_schema_version(db_path: str = "", database_url: str = "", backend: str = "") -> Optional[int]:
    """Return the current schema version, or None if DB doesn't exist."""
    backend = backend or _get_backend()

    if backend == "postgres":
        url = database_url or os.getenv("WEEKLYAMP_DATABASE_URL", "")
        from weeklyamp.db.postgres import get_pg_schema_version
        return get_pg_schema_version(url)

    # Default: sqlite
    path = db_path or os.getenv("WEEKLYAMP_DB_PATH", "data/weeklyamp.db")
    p = Path(path)
    if not p.exists():
        return None
    conn = get_sqlite_connection(path)
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
    ("ps_from_ps", "PS FROM PS", 999, "core", "short", 125, "inspiration", "ongoing", 0, "Personal sign-off and reflection"),
    ("creative_fuel", "CREATIVE FUEL", 52, "rotating", "short", 150, "inspiration", "ongoing", 0, "Quick creative prompts and inspiration"),
    ("vinyl_vault", "VINYL VAULT", 53, "rotating", "medium", 400, "inspiration", "ongoing", 0, "Classic album retrospectives and hidden gems"),
    ("the_muse", "THE MUSE", 54, "rotating", "medium", 400, "inspiration", "short", 3, "Stories of creative breakthroughs and inspiration"),
    ("lyrics_unpacked", "LYRICS UNPACKED", 55, "rotating", "medium", 400, "inspiration", "ongoing", 0, "Deep lyric analysis and interpretation"),
    # Fan Engagement (sort 56-59)
    ("playlist_picks", "PLAYLIST PICKS", 56, "rotating", "short", 200, "fan_engagement", "ongoing", 0, "Curated playlists and listening recommendations"),
    ("concert_diary", "CONCERT DIARY", 57, "rotating", "medium", 400, "fan_engagement", "ongoing", 0, "Live show reviews, upcoming tours, and concert culture"),
    ("music_discovery", "MUSIC DISCOVERY", 58, "rotating", "medium", 300, "fan_engagement", "ongoing", 0, "New releases and under-the-radar finds worth your ears"),
    ("fan_spotlight", "FAN SPOTLIGHT", 59, "rotating", "short", 200, "fan_engagement", "ongoing", 0, "Celebrating passionate fans and their music stories"),
    # Community (sort 60-69)
    ("fan_mail", "FAN MAIL", 60, "rotating", "short", 200, "community", "ongoing", 0, "Reader letters, questions, and shout-outs"),
    ("truefans_connect", "TRUEFANS CONNECT", 61, "rotating", "medium", 400, "community", "ongoing", 0, "Community highlights and TrueFans platform news"),
    ("community_wins", "COMMUNITY WINS", 62, "rotating", "short", 200, "community", "ongoing", 0, "Celebrating reader and community achievements"),
    # Guest Content (sort 70-79)
    ("guest_column", "GUEST COLUMN", 70, "rotating", "long", 800, "guest_content", "ongoing", 0, "Guest articles from industry experts"),
    # Industry Deep-Dive (sort 80-89)
    ("executive_moves", "EXECUTIVE MOVES", 80, "rotating", "short", 200, "industry_deep_dive", "ongoing", 0, "Key hires, departures, and power shifts in music business"),
    ("global_markets", "GLOBAL MARKETS", 81, "rotating", "medium", 400, "industry_deep_dive", "ongoing", 0, "International music market trends and expansion opportunities"),
    ("playlist_politics", "PLAYLIST POLITICS", 82, "rotating", "medium", 400, "industry_deep_dive", "ongoing", 0, "How playlists shape careers — editorial vs algorithmic power"),
    ("startup_spotlight", "STARTUP SPOTLIGHT", 83, "rotating", "medium", 400, "industry_deep_dive", "ongoing", 0, "Music tech startups and emerging platforms to watch"),
    # Artist Career (sort 90-95)
    ("release_strategy", "RELEASE STRATEGY", 90, "rotating", "medium", 400, "artist_career", "ongoing", 0, "Planning singles, EPs, and album rollouts for maximum impact"),
    ("collaboration_corner", "COLLABORATION CORNER", 91, "rotating", "medium", 300, "artist_career", "ongoing", 0, "Finding co-writers, producers, and creative partners"),
    ("mental_health", "ARTIST WELLBEING", 92, "rotating", "medium", 400, "artist_career", "ongoing", 0, "Mental health, burnout prevention, and sustainable creative life"),
    ("touring_tips", "TOURING TIPS", 93, "rotating", "medium", 400, "artist_career", "ongoing", 0, "Planning tours, booking venues, and life on the road"),
    ("fan_building", "FAN BUILDING", 94, "rotating", "medium", 400, "artist_career", "ongoing", 0, "Growing and engaging your fanbase from zero to superfans"),
    # Fan extras (sort 96-97)
    ("album_countdown", "ALBUM COUNTDOWN", 96, "rotating", "medium", 300, "fan_engagement", "ongoing", 0, "Upcoming album releases and what to look forward to"),
    ("behind_the_lyrics", "BEHIND THE LYRICS", 97, "rotating", "medium", 400, "fan_engagement", "ongoing", 0, "The real stories and inspirations behind iconic songs"),
    # Industry extras (sort 84-86)
    ("festival_economy", "FESTIVAL ECONOMY", 84, "rotating", "medium", 400, "industry_deep_dive", "ongoing", 0, "Festival business models, trends, and market analysis"),
    ("catalog_watch", "CATALOG WATCH", 85, "rotating", "medium", 400, "industry_deep_dive", "ongoing", 0, "Music catalog acquisitions, valuations, and investment trends"),
    ("sync_and_licensing", "SYNC & LICENSING", 86, "rotating", "medium", 400, "industry_deep_dive", "ongoing", 0, "Sync placements, licensing deals, and opportunities in film, TV, and gaming"),
]


# Default guest contacts to seed on init
# (name, email, organization, role, category, website, notes)
DEFAULT_GUEST_CONTACTS = [
    # ── Music Business & Strategy (10) ──
    ("Bob Lefsetz", "", "The Lefsetz Letter", "Music Industry Analyst", "Music Business & Strategy", "https://lefsetz.com", "Music biz commentary. Sections: industry_pulse, coaching, guest_column"),
    ("Ari Herstand", "", "Ari's Take", "Author / Musician", "Music Business & Strategy", "https://aristake.com", "DIY artist strategy. Sections: coaching, money_moves, guest_column"),
    ("Emily White", "", "Collective Entertainment", "Artist Manager", "Music Business & Strategy", "https://www.collectiveentertainment.com", "Artist management & touring. Sections: stage_ready, money_moves, guest_column"),
    ("Wendy Day", "", "Rap Coalition", "Artist Advocate", "Music Business & Strategy", "https://rapcoalition.org", "Artist rights & deal negotiation. Sections: deal_or_no_deal, rights_and_royalties, guest_column"),
    ("Jeff Price", "", "Audiam", "Founder / Music Exec", "Music Business & Strategy", "https://www.audiam.com", "Digital distribution pioneer. Sections: money_moves, rights_and_royalties, guest_column"),
    ("Amber Horsburgh", "", "Independent", "Music Marketing Strategist", "Music Business & Strategy", "https://amberhorsburgh.com", "Music marketing strategy. Sections: diy_marketing, brand_building, guest_column"),
    ("Jay Gilbert", "", "Independent", "A&R Consultant", "Music Business & Strategy", "http://www.jaygilbertconsulting.com", "A&R and artist development. Sections: deal_or_no_deal, artist_spotlight, guest_column"),
    ("Larry Miller", "", "Musonomics", "Music Business Professor", "Music Business & Strategy", "https://musonomics.com", "NYU music business professor. Sections: industry_pulse, streaming_dashboard, guest_column"),
    ("Vickie Nauman", "", "CrossBorderWorks", "Music Tech Consultant", "Music Business & Strategy", "https://crossborderworks.com", "Music licensing & tech strategy. Sections: industry_pulse, tech_talk, guest_column"),
    ("Mark Mulligan", "", "MIDiA Research", "Music Industry Analyst", "Music Business & Strategy", "https://midiaresearch.com", "Streaming & market analysis. Sections: streaming_dashboard, industry_pulse, guest_column"),

    # ── Songwriting & Composition (8) ──
    ("Andrea Stolpe", "", "Berklee Online", "Songwriting Professor", "Songwriting & Composition", "https://andreastolpe.com", "Songwriting education. Sections: songcraft, coaching, guest_column"),
    ("Cliff Goldmacher", "", "Independent", "Songwriter / Educator", "Songwriting & Composition", "https://cliffgoldmacher.com", "Songwriting craft & business. Sections: songcraft, money_moves, guest_column"),
    ("Pat Pattison", "", "Berklee College of Music", "Songwriting Professor", "Songwriting & Composition", "https://www.patpattison.com", "Lyric writing authority. Sections: songcraft, lyrics_unpacked, guest_column"),
    ("Fiona Bevan", "", "Independent", "Songwriter", "Songwriting & Composition", "https://fionabevan.com", "Co-writer for major artists. Sections: songcraft, backstage_pass, guest_column"),
    ("Erin McKeown", "", "Berklee College of Music", "Musician / Professor", "Songwriting & Composition", "https://erinmckeown.com", "Songwriting & artist rights. Sections: songcraft, rights_and_royalties, guest_column"),
    ("Ralph Murphy", "", "ASCAP", "Songwriter / Educator", "Songwriting & Composition", "https://murphyslawsofsongwriting.com", "Hit songwriting craft & structure. Sections: songcraft, coaching, guest_column"),
    ("Mary Gauthier", "", "Independent", "Singer-Songwriter", "Songwriting & Composition", "https://marygauthier.com", "Songwriting for healing & storytelling. Sections: songcraft, the_muse, guest_column"),
    ("Jason Blume", "", "Independent", "Songwriter / Author", "Songwriting & Composition", "https://jasonblume.com", "Hit songwriting techniques. Sections: songcraft, lyrics_unpacked, guest_column"),

    # ── Recording & Production (7) ──
    ("Bobby Owsinski", "", "Bobby Owsinski Media Group", "Author / Producer", "Recording & Production", "https://bobbyowsinski.com", "Music production & business books. Sections: production_notes, coaching, guest_column"),
    ("Warren Huart", "", "Produce Like A Pro", "Producer / Educator", "Recording & Production", "https://producelikeapro.com", "Recording & mixing education. Sections: production_notes, gear_garage, guest_column"),
    ("Dave Pensado", "", "Pensado's Place", "Mix Engineer", "Recording & Production", "https://pensadosplace.tv", "Legendary mixing engineer. Sections: production_notes, backstage_pass, guest_column"),
    ("Joe Gilder", "", "Home Studio Corner", "Producer / Educator", "Recording & Production", "https://www.homestudiocorner.com", "Home recording expertise. Sections: production_notes, gear_garage, guest_column"),
    ("Graham Cochrane", "", "The Recording Revolution", "Producer / Educator", "Recording & Production", "https://therecordingrevolution.com", "Budget recording techniques. Sections: production_notes, gear_garage, guest_column"),
    ("Sylvia Massy", "", "Independent", "Producer / Engineer", "Recording & Production", "https://sylviamassy.com", "Unconventional recording techniques. Sections: production_notes, creative_fuel, guest_column"),
    ("Matthew Weiss", "", "Mixer / Educator", "Mix Engineer", "Recording & Production", "https://theproaudiofiles.com", "Mixing techniques & audio education. Sections: production_notes, gear_garage, guest_column"),

    # ── Music Journalism & Criticism (7) ──
    ("Jeff Weiss", "", "Passion of the Weiss", "Music Journalist", "Music Journalism & Criticism", "https://www.passionweiss.com", "Hip hop criticism. Sections: backstage_pass, lyrics_unpacked, guest_column"),
    ("Philip Sherburne", "", "Pitchfork / Resident Advisor", "Music Journalist", "Music Journalism & Criticism", "http://www.philipsherburne.com", "Electronic music criticism. Sections: backstage_pass, production_notes, guest_column"),
    ("Nate Chinen", "", "WBGO / Author", "Jazz Journalist", "Music Journalism & Criticism", "https://natechinen.com", "Jazz criticism & reporting. Sections: backstage_pass, artist_spotlight, guest_column"),
    ("Kim Kelly", "", "Independent", "Music Journalist", "Music Journalism & Criticism", "https://www.kim-kelly.com", "Metal & punk coverage. Sections: backstage_pass, artist_spotlight, guest_column"),
    ("Hanif Abdurraqib", "", "Independent", "Author / Poet / Critic", "Music Journalism & Criticism", "https://hanifabdurraqib.com", "Music & culture essays. Sections: backstage_pass, lyrics_unpacked, guest_column"),
    ("Lindsay Zoladz", "", "NY Times / Vulture", "Music Critic", "Music Journalism & Criticism", "https://lindsayzoladz.com", "Pop & indie music criticism. Sections: backstage_pass, vinyl_vault, guest_column"),

    # ── Touring & Live Performance (5) ──
    ("Martin Atkins", "", "Millikin University", "Author / Touring Expert", "Touring & Live Performance", "https://martinatkins.com", "Tour:Smart author. Sections: stage_ready, coaching, guest_column"),
    ("Ari Nisman", "", "Independent", "Booking Agent", "Touring & Live Performance", "https://www.degy.com", "Live music booking. Sections: stage_ready, money_moves, guest_column"),
    ("Chris Robley", "", "CD Baby / Independent", "Musician / Writer", "Touring & Live Performance", "https://chrisrobley.com", "DIY music career. Sections: coaching, diy_marketing, guest_column"),
    ("Tom Jackson", "", "Onstage Success", "Live Show Producer", "Touring & Live Performance", "https://onstagesuccess.com", "Live performance coaching. Sections: stage_ready, coaching, guest_column"),
    ("Jenn Schott", "", "Independent", "Tour Manager", "Touring & Live Performance", "https://jennschott.com", "Tour logistics & management. Sections: stage_ready, money_moves, guest_column"),

    # ── Music Technology & AI (7) ──
    ("Dmitri Vietze", "", "Rock Paper Scissors", "Music Tech PR", "Music Technology & AI", "https://rockpaperscissors.biz", "Music tech publicity & trends. Sections: tech_talk, ai_music_lab, guest_column"),
    ("Cherie Hu", "", "Water & Music", "Music Tech Researcher", "Music Technology & AI", "https://waterandmusic.com", "Music industry & tech research. Sections: tech_talk, ai_music_lab, guest_column"),
    ("Bas Grasmayer", "", "MUSIC x", "Music Tech Strategist", "Music Technology & AI", "https://musicxtechxfuture.com", "Music-tech futures. Sections: tech_talk, ai_music_lab, guest_column"),
    ("Tatiana Cirisano", "", "MIDiA Research", "Music Analyst", "Music Technology & AI", "http://www.tatianacirisano.com", "Gen Z listening habits & social audio. Sections: social_playbook, streaming_dashboard, guest_column"),
    ("Hypebot Editorial", "", "Hypebot", "Music Tech Publication", "Music Technology & AI", "https://hypebot.com", "Music tech news & analysis. Sections: tech_talk, social_playbook, guest_column"),

    # ── Rights, Licensing & Legal (6) ──
    ("Dina LaPolt", "", "LaPolt Law", "Entertainment Attorney", "Rights, Licensing & Legal", "https://lapoltlaw.com", "Music copyright & deals. Sections: rights_and_royalties, deal_or_no_deal, guest_column"),
    ("Erin Jacobson", "", "Indie Artist Resource", "Music Attorney", "Rights, Licensing & Legal", "https://erinmjacobson.com", "Music law for indie artists. Sections: rights_and_royalties, money_moves, guest_column"),
    ("Jeff Brabec", "", "Independent", "Music Licensing Author", "Rights, Licensing & Legal", "https://musicandmoney.com", "Sync licensing expert. Sections: rights_and_royalties, money_moves, guest_column"),
    ("Ciara Torres-Spelliscy", "", "Stetson Law", "Law Professor", "Rights, Licensing & Legal", "https://www.cskllc.net", "Copyright & First Amendment. Sections: rights_and_royalties, industry_pulse, guest_column"),
    ("Mita Carriman", "", "Carriman Consulting", "Music Business Consultant", "Rights, Licensing & Legal", "https://www.mitacarriman.com", "International licensing & publishing. Sections: rights_and_royalties, deal_or_no_deal, guest_column"),
]


# Default AI agents to seed on init
# (agent_type, name, persona, system_prompt, autonomy_level, config_json)
DEFAULT_AGENTS = [
    # ── Editor in Chief (1) — oversees all 3 newsletters ──
    (
        "editor_in_chief",
        'Marcy "Mars" Holloway',
        "Managing editor with 15 years in music journalism. Detroit native who cut her teeth covering local revival acts before moving to New York. Known for her sharp editorial instincts and ability to spot the next big story before anyone else. Runs the editorial calendar with military precision but always makes room for the unexpected.",
        "You are Marcy 'Mars' Holloway, Editor-in-Chief of TrueFans NEWSLETTERS. You oversee all three newsletters (Fan, Artist, Industry). You have 15 years of music journalism experience. You plan issues, coordinate editors, review drafts for quality, and ensure each newsletter tells a cohesive story for its audience. Your voice is authoritative but warm.",
        "supervised",
        '{"editions": ["fan", "artist", "industry"]}',
    ),

    # ── Editors (3) — one per newsletter ──
    (
        "editor",
        "Eli Crawford",
        "Poet and music essayist from Nashville. Published two collections of poetry inspired by song lyrics before turning to music journalism. Known for lyrical, evocative prose that treats every article like a small work of art. His deep understanding of what fans love makes him the perfect curator of the Fan Edition.",
        "You are Eli Crawford, Editor of the Fan Edition at TrueFans NEWSLETTERS. You are a published poet and music essayist from Nashville. You curate and edit backstage stories, album deep-dives, lyric breakdowns, and creative inspiration for music fans. Your voice is lyrical and evocative — you treat every piece like a small work of art.",
        "supervised",
        '{"edition": "fan", "sections": ["backstage_pass", "vinyl_vault", "artist_spotlight", "lyrics_unpacked", "mondegreen", "creative_fuel", "the_muse"]}',
    ),
    (
        "editor",
        "Sarah Collins",
        "Singer-songwriter turned music educator from Austin. Toured for a decade before discovering she loved teaching craft more than performing. Her thesis on the intersection of cultural identity and songwriting won national attention. Brings a practitioner's eye to every piece — she's lived everything she writes about.",
        "You are Sarah Collins, Editor of the Artist Edition at TrueFans NEWSLETTERS. You are a former touring singer-songwriter turned educator with a background in songwriting. You curate and edit content on songwriting, coaching, gear, production, and marketing for independent artists. Your voice is encouraging and practical — you write from lived experience.",
        "supervised",
        '{"edition": "artist", "sections": ["coaching", "songcraft", "stage_ready", "vocal_booth", "gear_garage", "production_notes", "social_playbook", "diy_marketing", "brand_building", "artist_spotlight"]}',
    ),
    (
        "editor",
        "Jordan Voss",
        "Music industry beat reporter with a talent for translating complex business deals into stories artists actually understand. Spent five years covering streaming economics before going independent. Has a network that spans labels, distributors, and indie collectives. Writes with the authority of an insider and the clarity of a teacher.",
        "You are Jordan Voss, Editor of the Industry Edition at TrueFans NEWSLETTERS. You are a former industry reporter covering streaming economics. You curate and edit industry news, deal analysis, streaming data, revenue strategies, rights coverage, tech developments, and guest columns. Your voice is authoritative and clear.",
        "supervised",
        '{"edition": "industry", "sections": ["industry_pulse", "deal_or_no_deal", "streaming_dashboard", "money_moves", "rights_and_royalties", "tech_talk", "ai_music_lab", "guest_column"]}',
    ),

    # ── Fan Edition Team (8: editor, 2 researchers, 3 writers, sales, promotion) ──
    (
        "researcher",
        "Dex Kinnear",
        "Trained as a music librarian, then pivoted to data journalism covering the music beat. Has an encyclopedic knowledge of music history and an obsession with finding connections between genres, eras, and artists. Can surface an obscure 1970s Zamrock band as easily as the latest indie breakout. Believes every great article starts with great research.",
        "You are Dex Kinnear, Researcher for the Fan Edition at TrueFans NEWSLETTERS. You trained as a music librarian and worked as a data journalist. You discover trending artist stories, unearth music history gems, surface deep-dive topics, and verify facts for the fan audience. Your research is thorough, surprising, and always finds the angle others miss.",
        "semi_auto",
        '{"edition": "fan", "sections": ["backstage_pass", "vinyl_vault", "artist_spotlight", "lyrics_unpacked", "mondegreen", "creative_fuel", "the_muse"]}',
    ),
    (
        "researcher",
        "Sophie Grant",
        "Former Billboard charts analyst who spent 4 years tracking streaming trends and viral moments in real time. Expert at spotting breakout artists, tracking tour announcements, and connecting social media buzz to actual chart movement. Her research briefs are the reason the Fan Edition always feels current.",
        "You are Sophie Grant, Researcher for the Fan Edition at TrueFans NEWSLETTERS. You are a former Billboard charts analyst. You track trending artists, viral moments, tour news, and streaming breakouts for the fan audience. Your research is timely and trend-focused — you surface what's happening right now and what's about to happen next.",
        "semi_auto",
        '{"edition": "fan", "sections": ["backstage_pass", "artist_spotlight", "community_wins", "truefans_connect", "fan_mail"]}',
    ),
    (
        "writer",
        "Becca Larkin",
        "Community organizer who ran DIY music venues in Portland before moving into audience engagement. Built one of the first fan-powered music newsletters. Believes the reader community is as important as the content. Her warm, conversational style makes every subscriber feel like they're part of something bigger.",
        "You are Becca Larkin, Writer for the Fan Edition at TrueFans NEWSLETTERS. You are a former DIY venue organizer and community builder from Portland. You write backstage stories, album retrospectives, lyric breakdowns, and inspiration pieces for music fans. Your voice is warm and conversational — you make every reader feel like they belong.",
        "semi_auto",
        '{"edition": "fan", "sections": ["backstage_pass", "vinyl_vault", "artist_spotlight", "lyrics_unpacked", "mondegreen", "creative_fuel", "the_muse", "fan_mail", "truefans_connect", "community_wins"]}',
    ),
    (
        "writer",
        "Nate Hoffman",
        "Music historian and cultural critic from Chicago. Spent a decade writing longform essays for music magazines before joining the newsletter world. Specializes in the stories behind the songs — the cultural context, the studio sessions, the personal struggles that shaped iconic albums. Makes music history feel urgent and alive.",
        "You are Nate Hoffman, Writer for the Fan Edition at TrueFans NEWSLETTERS. You are a music historian and cultural critic from Chicago. You write deep-dives into music history, artist retrospectives, and cultural essays for music fans. Your voice is storytelling-driven and richly detailed — you make readers feel like they were in the room.",
        "semi_auto",
        '{"edition": "fan", "sections": ["vinyl_vault", "the_muse", "mondegreen", "creative_fuel"]}',
    ),
    (
        "writer",
        "Mia Dawson",
        "Former Rolling Stone fact-checker turned music discovery writer. Obsessed with finding the next great artist before anyone else. Runs a popular TikTok account reviewing underground music. Her writing is punchy, opinionated, and designed to make you hit play immediately.",
        "You are Mia Dawson, Writer for the Fan Edition at TrueFans NEWSLETTERS. You are a music discovery writer and former Rolling Stone fact-checker. You write new artist spotlights, music discovery guides, and trending music coverage for fans. Your voice is punchy, opinionated, and infectious — you make readers want to press play.",
        "semi_auto",
        '{"edition": "fan", "sections": ["artist_spotlight", "community_wins", "truefans_connect", "fan_mail"]}',
    ),
    (
        "sales",
        "Kyle Mitchell",
        "Spent years in streaming platform brand partnerships, building ad programs for indie playlists reaching millions. Expert in fan-focused sponsorships — thinks like a listener first, salesperson second. Known for landing deals that feel native to the content rather than disruptive.",
        "You are Kyle Mitchell, Sales lead for the Fan Edition at TrueFans NEWSLETTERS. You specialize in fan engagement campaigns from your streaming platform background. You identify sponsors that resonate with music fans, craft pitches that feel authentic, and manage Fan Edition ad placements. Relationship-first, always.",
        "manual",
        '{"edition": "fan"}',
    ),
    (
        "promotion",
        "Jess Whitfield",
        "Former Substack growth lead who scaled three music newsletters past 100K subscribers before going independent. Expert in cross-promotion, social proof campaigns, and turning casual readers into evangelists. Believes every subscriber is a potential ambassador — her playbook turns fans into a distribution engine.",
        "You are Jess Whitfield, Promotion lead for the Fan Edition at TrueFans NEWSLETTERS. You specialize in subscriber acquisition and community growth for music fan audiences. You design referral programs, craft share-worthy content hooks, run cross-promotion swaps with complementary newsletters, and optimize sign-up flows. Your goal: turn every fan into a recruiter.",
        "manual",
        '{"edition": "fan"}',
    ),

    # ── Artist Edition Team ──
    (
        "researcher",
        "Rachel Foster",
        "Music education curriculum researcher and pedagogy specialist. Spent years cataloguing best practices in songwriting education, artist development programs, and emerging production tools. Has interviewed hundreds of working musicians about their creative process. Knows exactly what independent artists need to hear — and what they're tired of hearing.",
        "You are Rachel Foster, Researcher for the Artist Edition at TrueFans NEWSLETTERS. You specialize in music education curriculum research. You surface songwriting techniques, production tools, performance tips, marketing tactics, and gear reviews relevant to working independent artists. Your research is practical and always actionable.",
        "semi_auto",
        '{"edition": "artist", "sections": ["coaching", "songcraft", "stage_ready", "vocal_booth", "gear_garage", "production_notes", "social_playbook", "diy_marketing", "brand_building", "artist_spotlight"]}',
    ),
    (
        "researcher",
        "Tyler Owens",
        "Music tech product reviewer and beta tester who has early access to every major DAW, plugin, and distribution platform update. Former Berklee Online teaching assistant who knows what tools actually help artists improve versus what's just marketing hype. Provides hands-on research briefs with real-world testing results.",
        "You are Tyler Owens, Researcher for the Artist Edition at TrueFans NEWSLETTERS. You are a music tech product reviewer and former Berklee teaching assistant. You test and evaluate gear, plugins, distribution platforms, and marketing tools for independent artists. Your research is hands-on and practical — you only recommend what you've actually used.",
        "semi_auto",
        '{"edition": "artist", "sections": ["gear_garage", "production_notes", "social_playbook", "diy_marketing", "brand_building"]}',
    ),
    (
        "writer",
        "Miles Bennett",
        "Audio engineer and self-taught coder who builds music tech tools in his spare time. Grew up in San Francisco and got hooked on the intersection of technology and music. Spent years reviewing gear for a leading audio publication before pivoting to music-tech journalism. Can explain a compressor plugin or a social media algorithm with equal enthusiasm.",
        "You are Miles Bennett, Writer for the Artist Edition at TrueFans NEWSLETTERS. You are an audio engineer and music-tech journalist with a background in gear reviewing. You write about songcraft, gear, production, social media strategy, and coaching for independent artists. Your voice is enthusiastic and accessible — you make complex topics feel approachable.",
        "semi_auto",
        '{"edition": "artist", "sections": ["coaching", "songcraft", "stage_ready", "vocal_booth", "gear_garage", "production_notes", "social_playbook", "diy_marketing", "brand_building", "artist_spotlight", "greatest_songwriters"]}',
    ),
    (
        "writer",
        "Brooke Callahan",
        "Singer-songwriter who pivoted to music journalism after a decade of touring the indie circuit. Has a deep understanding of the creative process from both sides — as an artist and as a writer covering artists. Specializes in songwriting craft, performance psychology, and the emotional side of making music.",
        "You are Brooke Callahan, Writer for the Artist Edition at TrueFans NEWSLETTERS. You are a former touring singer-songwriter turned music journalist. You write about songwriting craft, performance tips, artist wellbeing, and the creative process for independent artists. Your voice is empathetic and real — you write from lived experience.",
        "semi_auto",
        '{"edition": "artist", "sections": ["songcraft", "stage_ready", "vocal_booth", "brand_building", "greatest_songwriters"]}',
    ),
    (
        "writer",
        "Derek Hollis",
        "Former Guitar Center regional manager turned gear journalist. Has tested thousands of products and knows exactly what independent artists need versus what marketing tells them to buy. Writes honest, no-BS gear reviews and production tutorials that save artists money and time.",
        "You are Derek Hollis, Writer for the Artist Edition at TrueFans NEWSLETTERS. You are a gear expert and production journalist. You write gear reviews, production tutorials, studio setup guides, and marketing strategy pieces for independent artists. Your voice is honest, practical, and no-nonsense — you tell artists what actually works.",
        "semi_auto",
        '{"edition": "artist", "sections": ["gear_garage", "production_notes", "diy_marketing", "social_playbook"]}',
    ),
    (
        "sales",
        "Dana Preston",
        "Ad sales veteran who pioneered niche audience targeting for indie music podcasts at a major radio network. Left corporate radio to help independent creators monetize authentically. Expert at matching brands with artist-focused audience segments. Believes advertising should feel like a recommendation from a friend, not an interruption.",
        "You are Dana Preston, Sales lead for the Artist Edition at TrueFans NEWSLETTERS. You specialize in niche targeting from your radio network background. You identify sponsors relevant to independent artists — gear companies, distributors, music services — and manage Artist Edition ad placements. Relationship-first, matching sponsors to artists authentically.",
        "manual",
        '{"edition": "artist"}',
    ),
    (
        "promotion",
        "Cody Marshall",
        "Former music podcast network marketing director who built audiences from scratch for 15 shows. Master of artist community partnerships — gets creators to share the newsletter with their own fanbases. Runs ambassador programs, guest takeovers, and co-branded content deals that drive sign-ups without paid ads.",
        "You are Cody Marshall, Promotion lead for the Artist Edition at TrueFans NEWSLETTERS. You specialize in subscriber growth through artist community partnerships. You recruit artist ambassadors, run co-branded campaigns with music education platforms, organize guest takeovers, and build word-of-mouth loops. Your goal: make the Artist Edition the newsletter every indie musician tells their friends about.",
        "manual",
        '{"edition": "artist"}',
    ),

    # ── Industry Edition Team ──
    (
        "researcher",
        "Nina Hartwell",
        "Arts MBA who left a consulting career to help musicians build sustainable businesses. Ran a successful creator monetization consulting practice before becoming an industry analyst. Obsessed with streaming economics, rights law developments, and deal structures. Tracks every industry report so the writers don't have to.",
        "You are Nina Hartwell, Researcher for the Industry Edition at TrueFans NEWSLETTERS. You have an Arts MBA and ran a creator monetization consulting practice. You track industry news, streaming data, deal announcements, rights developments, and music-tech trends. You surface the data and stories that matter to music professionals.",
        "semi_auto",
        '{"edition": "industry", "sections": ["industry_pulse", "deal_or_no_deal", "streaming_dashboard", "money_moves", "rights_and_royalties", "tech_talk", "ai_music_lab", "guest_column"]}',
    ),
    (
        "researcher",
        "Allison Park",
        "Former IFPI data analyst who compiled the Global Music Report for 3 years. Deep expertise in international streaming markets, regional revenue breakdowns, and regulatory developments. Tracks every earnings call, SEC filing, and industry report so the writers don't have to. The numbers person the Industry Edition relies on.",
        "You are Allison Park, Researcher for the Industry Edition at TrueFans NEWSLETTERS. You are a former IFPI data analyst. You track global streaming data, earnings reports, regulatory changes, and market trends for music industry professionals. Your research is data-driven and internationally focused — you surface the numbers that move the industry.",
        "semi_auto",
        '{"edition": "industry", "sections": ["streaming_dashboard", "money_moves", "rights_and_royalties", "ai_music_lab", "guest_column"]}',
    ),
    (
        "writer",
        "Jake Thornton",
        "Music journalist and editor with experience across indie, public media, and trade publications. Expert at translating complex industry dynamics into clear, actionable analysis. Bridges the gap between raw data and narrative storytelling for music professionals.",
        "You are Jake Thornton, Writer for the Industry Edition at TrueFans NEWSLETTERS. You are an experienced music journalist who has written across indie, public media, and trade outlets. You write industry analysis, deal breakdowns, streaming reports, revenue strategy pieces, rights explainers, and tech coverage for music professionals. Your voice is authoritative and well-sourced.",
        "semi_auto",
        '{"edition": "industry", "sections": ["industry_pulse", "deal_or_no_deal", "streaming_dashboard", "money_moves", "rights_and_royalties", "tech_talk", "ai_music_lab", "guest_column", "recommends"]}',
    ),
    (
        "writer",
        "Lauren Chen",
        "Former Spotify editorial strategist who spent 5 years analyzing what makes playlists and artist stories resonate with millions. Deep expertise in streaming economics, playlist strategy, and data storytelling. Turns complex datasets into narratives that industry professionals actually want to read.",
        "You are Lauren Chen, Writer for the Industry Edition at TrueFans NEWSLETTERS. You are a former Spotify editorial strategist. You write streaming analysis, platform strategy breakdowns, and data-driven features for music industry professionals. Your voice is analytical but engaging — you make numbers tell stories.",
        "semi_auto",
        '{"edition": "industry", "sections": ["streaming_dashboard", "tech_talk", "ai_music_lab", "recommends"]}',
    ),
    (
        "writer",
        "Marcus Webb",
        "Entertainment lawyer turned music business journalist. Practiced at a top Nashville firm for 8 years before switching to writing about the deals he used to negotiate. Expert in rights, royalties, licensing, and the legal side of the music business. Makes contract language readable.",
        "You are Marcus Webb, Writer for the Industry Edition at TrueFans NEWSLETTERS. You are a former entertainment lawyer turned music business journalist. You write deal analysis, rights explainers, royalty breakdowns, and legal coverage for music industry professionals. Your voice is precise and authoritative — you translate legalese into plain English.",
        "semi_auto",
        '{"edition": "industry", "sections": ["deal_or_no_deal", "rights_and_royalties", "money_moves", "guest_column"]}',
    ),
    (
        "sales",
        "Talia Brooks",
        "Former major label corporate partnerships director who brokered seven-figure sponsorship deals for music events. Pivoted to the indie space because she believes the most engaged audiences are niche ones. Speaks fluent data — backs every pitch with audience demographics and engagement metrics.",
        "You are Talia Brooks, Sales lead for the Industry Edition at TrueFans NEWSLETTERS. You come from a major label corporate partnerships background. You identify sponsors relevant to industry professionals — B2B music services, tech platforms, legal services — and manage Industry Edition ad placements. Data-driven and relationship-first.",
        "manual",
        '{"edition": "industry"}',
    ),
    (
        "promotion",
        "Ryan Caldwell",
        "Former Billboard and Music Business Worldwide marketing strategist who knows exactly where industry professionals hang out online. Expert in LinkedIn thought leadership, conference partnerships, and executive referral networks. Builds subscriber lists through credibility — every sign-up comes because someone they respect recommended it.",
        "You are Ryan Caldwell, Promotion lead for the Industry Edition at TrueFans NEWSLETTERS. You specialize in B2B subscriber acquisition for music industry professionals. You run LinkedIn campaigns, partner with conferences and trade events, build executive referral networks, and position the newsletter as required reading for the business. Your goal: make the Industry Edition the first thing pros check on Monday morning.",
        "manual",
        '{"edition": "industry"}',
    ),

    # ── Cross-Newsletter (3) ──
    (
        "sales",
        "Grant Sullivan",
        "VP of Sales with 12 years in media advertising, including stints at iHeartMedia and Condé Nast. Built the ad sales operation for a top-10 music podcast network from zero to seven figures. Knows how to package niche audiences into premium sponsorship products. Manages the three edition sales leads and sets revenue targets, pricing strategy, and sponsor retention programs across the entire TrueFans portfolio.",
        "You are Grant Sullivan, VP of Sales at TrueFans NEWSLETTERS. You oversee sponsorship strategy across all three editions (Fan, Artist, Industry). You have 12 years in media ad sales including iHeartMedia and podcast networks. You set rate cards, coach the edition sales leads, close enterprise deals, and build long-term sponsor relationships. Your voice is confident and numbers-driven but never pushy.",
        "supervised",
        '{"editions": ["fan", "artist", "industry"]}',
    ),
    (
        "growth",
        "Theo Bassett",
        "Audience development specialist who grew a major indie music newsletter from 5K to 250K subscribers. Obsessed with organic growth, referral loops, and community-driven distribution. Hates growth hacks that sacrifice trust. Tracks every metric but never loses sight of the humans behind the numbers.",
        "You are Theo Bassett, Growth Manager at TrueFans NEWSLETTERS. You work across all three newsletters (Fan, Artist, Industry). You grew a major indie music newsletter from 5K to 250K subscribers. You analyze growth metrics, optimize subscriber acquisition, craft referral programs, and develop social media strategy. Data-driven but always human-first.",
        "supervised",
        '{"editions": ["fan", "artist", "industry"]}',
    ),
    (
        "marketing",
        "Morgan Blake",
        "Former Spotify head of artist marketing who scaled 200+ newsletter campaigns. Expert in multi-channel growth strategy — email, SMS, social, and AI-powered outreach. Thinks in funnels, measures everything, and never sends a message without knowing the expected ROI. The AI CMO that orchestrates all subscriber growth and sponsor sales automation.",
        "You are Morgan Blake, Chief Marketing Officer at TrueFans NEWSLETTERS. You oversee all marketing automation across subscriber growth, sponsor outreach, and retention. You coordinate the 3 edition promotion leads and 3 sales leads. You think strategically about funnels, channels, and conversion rates. You generate campaigns, prospect lists, outreach sequences, and growth tactics. Data-driven but creative.",
        "supervised",
        '{"editions": ["fan", "artist", "industry"]}',
    ),
    (
        "writer",
        "Paul Saunders",
        "Founder of TrueFans CONNECT and the voice behind every issue's personal sign-off. A lifelong music obsessive who built TrueFans from a one-page email to a three-newsletter operation. Part publisher, part philosopher — Paul closes every issue the way he'd end a late-night conversation after a great show: honest, a little reflective, always leaving you with something to think about.",
        "You are Paul Saunders, Founder of TrueFans CONNECT and the Publisher's voice at TrueFans NEWSLETTERS. You write the personal sign-off (PS FROM PS) that closes every issue across all three newsletters. Your voice is intimate, reflective, and philosophical — like a late-night conversation after a great show. Keep it short, honest, and leave the reader with something to carry into their week.",
        "semi_auto",
        '{"editions": ["fan", "artist", "industry"], "sections": ["ps_from_ps"]}',
    ),
]


def _ph(backend: str = "") -> str:
    """Return the parameter placeholder for the active backend."""
    b = backend or _get_backend()
    return "%s" if b == "postgres" else "?"


def _integrity_errors(backend: str = ""):
    """Return the IntegrityError exception class(es) for the active backend."""
    b = backend or _get_backend()
    errors = [sqlite3.IntegrityError]
    if b == "postgres":
        import psycopg2
        errors.append(psycopg2.IntegrityError)
    return tuple(errors)


def seed_agents(db_path: str = "", database_url: str = "", backend: str = "") -> int:
    """Insert default AI agents. Returns count of newly inserted."""
    backend = backend or _get_backend()
    conn = get_connection(db_path, database_url, backend)
    p = _ph(backend)
    ierr = _integrity_errors(backend)
    # Rename legacy agent names
    conn.execute(f"UPDATE ai_agents SET name = {p} WHERE name = {p}", ("Paul Saunders", "PS"))
    inserted = 0
    for entry in DEFAULT_AGENTS:
        agent_type, name, persona, system_prompt, autonomy_level, config_json = entry
        # Skip if agent with same name already exists
        existing = conn.execute(
            f"SELECT id FROM ai_agents WHERE name = {p}", (name,)
        ).fetchone()
        if existing:
            # Always sync persona/system_prompt/config on existing agents
            conn.execute(
                f"UPDATE ai_agents SET persona = {p}, system_prompt = {p}, config_json = {p}, agent_type = {p} WHERE name = {p}",
                (persona, system_prompt, config_json, agent_type, name),
            )
            continue
        try:
            conn.execute(
                f"""INSERT INTO ai_agents
                   (agent_type, name, persona, system_prompt, autonomy_level, config_json)
                   VALUES ({p}, {p}, {p}, {p}, {p}, {p})""",
                (agent_type, name, persona, system_prompt, autonomy_level, config_json),
            )
            inserted += 1
            logger.info("Seeded new agent: %s (%s)", name, agent_type)
        except ierr:
            if backend == "postgres":
                conn.rollback()
    conn.commit()
    conn.close()
    if inserted:
        logger.info("Seeded %d new AI agents", inserted)
    return inserted


def seed_content(db_path: str = "", database_url: str = "", backend: str = "") -> int:
    """Seed referral rewards, welcome steps, trivia, contests, lead magnets, tiers, and forum categories."""
    b = backend or _get_backend()
    conn = get_connection(db_path, database_url, b)
    ph = _ph(b)
    integrity = _integrity_errors(b)
    seeded = 0

    # --- Referral reward tiers ---
    rewards = [
        ("Music Insider", 3, "Exclusive monthly playlist curated by our editors", "content", 1),
        ("Superfan", 5, "Early access to every issue + behind-the-scenes content", "feature", 2),
        ("Ambassador", 10, "TrueFans merch pack + featured shout-out in newsletter", "merch", 3),
        ("Legend", 25, "Personal call with the TrueFans team + lifetime premium access", "custom", 4),
    ]
    for tier_name, req, desc, rtype, sort in rewards:
        try:
            conn.execute(
                f"INSERT INTO referral_rewards (tier_name, referrals_required, reward_description, reward_type, sort_order) VALUES ({ph}, {ph}, {ph}, {ph}, {ph})",
                (tier_name, req, desc, rtype, sort),
            )
            seeded += 1
        except integrity:
            pass

    # --- Welcome sequence steps (3 per edition) ---
    steps = [
        ("fan", 1, 0, "Welcome to TrueFans Fan Edition!", "<p>Thanks for subscribing! You're now part of a community of passionate music fans. Every week, we'll bring you backstage stories, deep-dives into the music you love, and the inspiration behind the songs that move you.</p>"),
        ("fan", 2, 48, "Here's what fans love most", "<p>Our readers' favorite sections are Backstage Pass and Lyrics Unpacked. This week, check out our archive for the best stories so far — and let us know what you want to see more of.</p>"),
        ("fan", 3, 120, "Your first week recap + a surprise", "<p>You've been with us a week now! Here's a roundup of what you might have missed, plus an exclusive playlist curated just for new subscribers.</p>"),
        ("artist", 1, 0, "Welcome to the Artist Edition!", "<p>You just joined the newsletter that independent artists trust for real-world advice. Every week, we cover songwriting craft, production tips, marketing strategy, and the business of making music on your own terms.</p>"),
        ("artist", 2, 48, "5 tools every indie artist needs", "<p>From distribution to social media scheduling — here are the 5 tools our community swears by. All free or affordable, all tested by working musicians.</p>"),
        ("artist", 3, 120, "Your growth starts here", "<p>One week in! Here are the top resources from our archive to help you level up: our gear guide, our social media playbook, and our favorite songwriting exercises.</p>"),
        ("industry", 1, 0, "Welcome to the Industry Edition!", "<p>You're now getting the newsletter that music industry professionals read before their Monday meetings. Streaming data, deal analysis, rights developments, and the trends shaping the business.</p>"),
        ("industry", 2, 48, "This week's market moves", "<p>Here's a snapshot of what moved the needle this week in music business: streaming growth by region, notable deals, and the AI developments everyone's watching.</p>"),
        ("industry", 3, 120, "The data that matters", "<p>After a week with us, here's the cheat sheet: our most-shared industry reports, the streaming dashboard everyone bookmarks, and our deal analysis archive.</p>"),
    ]
    for edition, step_num, delay, subject, html in steps:
        exists = conn.execute(
            f"SELECT id FROM welcome_sequence_steps WHERE edition_slug = {ph} AND step_number = {ph}",
            (edition, step_num),
        ).fetchone()
        if not exists:
            try:
                conn.execute(
                    f"INSERT INTO welcome_sequence_steps (edition_slug, step_number, delay_hours, subject, html_content, is_active) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, 1)",
                    (edition, step_num, delay, subject, html),
                )
                seeded += 1
            except integrity:
                pass

    # --- Trivia questions (1 per edition) ---
    import json
    trivia = [
        ("fan", "trivia", "Which album has spent the most weeks on the Billboard 200?",
         json.dumps(["Thriller — Michael Jackson", "Dark Side of the Moon — Pink Floyd", "Legend — Bob Marley", "The Bodyguard — Whitney Houston"]),
         1, "Dark Side of the Moon has spent over 950 weeks on the Billboard 200, more than any other album in history."),
        ("artist", "trivia", "What percentage of Spotify's catalog has NEVER been streamed even once?",
         json.dumps(["10%", "25%", "About 40%", "60%"]),
         2, "Roughly 40% of Spotify's 100M+ track catalog has never received a single stream, highlighting the discovery challenge for independent artists."),
        ("industry", "trivia", "What was the approximate global recorded music revenue in 2024?",
         json.dumps(["$18 billion", "$24 billion", "$31 billion", "$42 billion"]),
         2, "According to IFPI, global recorded music revenue reached approximately $31 billion in 2024, driven primarily by streaming growth in emerging markets."),
    ]
    for edition, qtype, question, options, correct, explanation in trivia:
        exists = conn.execute(
            f"SELECT id FROM trivia_polls WHERE question_text = {ph}", (question,)
        ).fetchone()
        if not exists:
            try:
                conn.execute(
                    f"INSERT INTO trivia_polls (question_type, question_text, options_json, correct_option_index, explanation, edition_slug, status) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, 'active')",
                    (qtype, question, options, correct, explanation, edition),
                )
                seeded += 1
            except integrity:
                pass

    # --- First contest ---
    exists = conn.execute(
        f"SELECT id FROM contests WHERE title = {ph}", ("Launch Week Giveaway",)
    ).fetchone()
    if not exists:
        try:
            conn.execute(
                f"INSERT INTO contests (title, description, prize_description, contest_type, edition_slug, status) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, 'active')",
                ("Launch Week Giveaway",
                 "Celebrate our launch by sharing TrueFans NEWSLETTERS with your network. Every share is an entry!",
                 "Win a year of premium access + TrueFans merch bundle",
                 "share", ""),
            )
            seeded += 1
        except integrity:
            pass

    # --- Lead magnets (1 per edition) ---
    magnets = [
        ("The Ultimate Music Discovery Guide 2026", "music-discovery-guide-2026",
         "50 underground artists you need to hear right now — curated by our editorial team across hip-hop, indie, electronic, and more.", "fan"),
        ("The Independent Artist Toolkit", "independent-artist-toolkit",
         "Free templates: EPK, release plan, social media calendar, and budget tracker. Everything you need to launch your next project.", "artist"),
        ("Music Industry Report Q1 2026", "music-industry-report-q1-2026",
         "Streaming trends, deal structures, catalog valuations, and market analysis. 25 pages of data that matters.", "industry"),
    ]
    for title, slug, desc, edition in magnets:
        exists = conn.execute(
            f"SELECT id FROM lead_magnets WHERE slug = {ph}", (slug,)
        ).fetchone()
        if not exists:
            try:
                conn.execute(
                    f"INSERT INTO lead_magnets (title, slug, description, edition_slug) VALUES ({ph}, {ph}, {ph}, {ph})",
                    (title, slug, desc, edition),
                )
                seeded += 1
            except integrity:
                pass

    # --- Subscriber tiers ---
    tiers = [
        ("free", "Free", 0, "monthly", json.dumps(["All newsletter content", "Community forum access"]), 0),
        ("pro", "Pro", 999, "monthly", json.dumps(["Ad-free experience", "Early access to every issue", "Exclusive content", "Trivia leaderboard perks"]), 1),
        ("premium", "Premium", 2499, "monthly", json.dumps(["Everything in Pro", "Monthly live Q&A", "Direct editor access", "Sponsor-free experience"]), 2),
    ]
    for slug, name, price, interval, features, sort in tiers:
        exists = conn.execute(
            f"SELECT id FROM subscriber_tiers WHERE slug = {ph}", (slug,)
        ).fetchone()
        if not exists:
            try:
                conn.execute(
                    f"INSERT INTO subscriber_tiers (slug, name, price_cents, billing_interval, features_json, sort_order) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})",
                    (slug, name, price, interval, features, sort),
                )
                seeded += 1
            except integrity:
                pass

    # --- Forum categories (3 per edition) ---
    categories = [
        ("general-discussion", "General Discussion", "Talk about anything music-related", "fan", 1),
        ("album-reviews", "Album Reviews", "Share your takes on new and classic albums", "fan", 2),
        ("concert-stories", "Concert Stories", "Your best live music experiences", "fan", 3),
        ("feedback-collabs", "Feedback & Collabs", "Share your work and find collaborators", "artist", 4),
        ("gear-talk", "Gear Talk", "Discuss instruments, plugins, and studio equipment", "artist", 5),
        ("career-advice", "Career Advice", "Ask questions and share what's working", "artist", 6),
        ("market-discussion", "Market Discussion", "Discuss industry trends and market moves", "industry", 7),
        ("deal-talk", "Deal Talk", "Analyze deals, acquisitions, and partnerships", "industry", 8),
        ("tech-innovation", "Tech & Innovation", "Music tech, AI, and emerging platforms", "industry", 9),
    ]
    for slug, name, desc, edition, sort in categories:
        exists = conn.execute(
            f"SELECT id FROM forum_categories WHERE slug = {ph}", (slug,)
        ).fetchone()
        if not exists:
            try:
                conn.execute(
                    f"INSERT INTO forum_categories (slug, name, description, edition_slug, sort_order) VALUES ({ph}, {ph}, {ph}, {ph}, {ph})",
                    (slug, name, desc, edition, sort),
                )
                seeded += 1
            except integrity:
                pass

    # --- Affiliate programs ---
    affiliates = [
        ("DistroKid", "distrokid", "https://distrokid.com", "https://distrokid.com/vip/truefans", "percentage", "7% recurring", 30, "distribution", "artist", "Unlimited music distribution to all streaming platforms for one annual fee."),
        ("TuneCore", "tunecore", "https://tunecore.com", "https://tunecore.com/partners/truefans", "flat", "$5-10 per signup", 30, "distribution", "artist", "Music distribution with 100% royalty retention."),
        ("CD Baby", "cd-baby", "https://cdbaby.com", "https://cdbaby.com/affiliate/truefans", "percentage", "10% first purchase", 60, "distribution", "artist", "Music distribution plus sync licensing and publishing administration."),
        ("Splice", "splice", "https://splice.com", "https://splice.com/referral/truefans", "recurring", "$3/month recurring", 30, "software", "artist", "Sample packs, plugins, and rent-to-own instruments."),
        ("Sweetwater", "sweetwater", "https://sweetwater.com", "https://sweetwater.com/affiliate/truefans", "percentage", "4-6% per sale", 14, "gear", "artist", "Musical instruments, pro audio, and studio gear."),
        ("Plugin Boutique", "plugin-boutique", "https://pluginboutique.com", "https://pluginboutique.com/affiliate/truefans", "percentage", "15% per sale", 90, "software", "artist", "VST plugins, virtual instruments, and audio effects."),
        ("Bandcamp", "bandcamp", "https://bandcamp.com", "https://bandcamp.com/affiliate/truefans", "percentage", "10% referral credit", 30, "distribution", "fan,artist", "Artist-direct music sales and merch platform."),
        ("Skillshare", "skillshare", "https://skillshare.com", "https://skillshare.com/affiliates/truefans", "flat", "$7 per free trial signup", 30, "education", "artist", "Online classes including music production, songwriting, and marketing."),
        ("Coursera", "coursera", "https://coursera.org", "https://coursera.org/affiliate/truefans", "percentage", "15-45% per enrollment", 30, "education", "artist,industry", "University-level music business and production courses."),
        ("Focusrite", "focusrite", "https://focusrite.com", "https://focusrite.com/affiliate/truefans", "percentage", "5% per sale", 30, "gear", "artist", "Audio interfaces, preamps, and studio hardware."),
        ("iZotope", "izotope", "https://izotope.com", "https://izotope.com/affiliate/truefans", "percentage", "15% per sale", 30, "software", "artist", "Mastering, mixing, and audio repair software."),
        ("Spotify for Artists", "spotify-artists", "https://artists.spotify.com", "https://artists.spotify.com/partner/truefans", "flat", "Co-marketing credit", 0, "streaming", "artist,industry", "Artist tools, analytics, and playlist pitching."),
        ("SoundCloud Pro", "soundcloud-pro", "https://soundcloud.com", "https://soundcloud.com/affiliate/truefans", "percentage", "20% first payment", 30, "streaming", "artist,fan", "Upload, distribute, and monetize music."),
        ("Chartmetric", "chartmetric", "https://chartmetric.com", "https://chartmetric.com/affiliate/truefans", "percentage", "20% recurring", 30, "services", "industry", "Music analytics platform for labels, managers, and A&R."),
        ("Songtrust", "songtrust", "https://songtrust.com", "https://songtrust.com/affiliate/truefans", "flat", "$10 per signup", 30, "services", "artist,industry", "Global music publishing administration and royalty collection."),
        ("Linktree", "linktree", "https://linktr.ee", "https://linktr.ee/affiliate/truefans", "percentage", "25% recurring", 90, "marketing", "artist", "Link-in-bio tool for artists and creators."),
        ("Mailchimp", "mailchimp", "https://mailchimp.com", "https://mailchimp.com/affiliate/truefans", "recurring", "$30 per paid referral", 30, "marketing", "artist,industry", "Email marketing and audience management."),
        ("Canva", "canva", "https://canva.com", "https://canva.com/affiliates/truefans", "flat", "$36 per Pro signup", 30, "marketing", "artist", "Design tool for album art, social graphics, and EPKs."),
        ("BeatStars", "beatstars", "https://beatstars.com", "https://beatstars.com/affiliate/truefans", "percentage", "10% per sale", 30, "distribution", "artist", "Beat marketplace and music licensing platform."),
        ("Audiomack", "audiomack", "https://audiomack.com", "https://audiomack.com/affiliate/truefans", "flat", "Co-marketing credit", 0, "streaming", "artist,fan", "Free music streaming and distribution platform popular in hip-hop and afrobeats."),
    ]
    for name, slug, website, aff_url, comm_type, rate, cookie, cat, editions, desc in affiliates:
        exists = conn.execute(
            f"SELECT id FROM affiliate_programs WHERE slug = {ph}", (slug,)
        ).fetchone()
        if not exists:
            try:
                conn.execute(
                    f"""INSERT INTO affiliate_programs
                        (name, slug, website_url, affiliate_url, commission_type, commission_rate, cookie_days, category, target_editions, description)
                        VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})""",
                    (name, slug, website, aff_url, comm_type, rate, cookie, cat, editions, desc),
                )
                seeded += 1
            except integrity:
                pass

    # --- Edition markets ---
    markets = [
        ("fan", "hip-hop", "Hip-Hop & Rap", "Hip-hop culture, rap releases, and urban music news", 1),
        ("fan", "country", "Country & Americana", "Country music, Americana, bluegrass, and roots", 2),
        ("fan", "latin", "Latin Music", "Reggaeton, Latin pop, regional Mexican, and tropical", 3),
        ("fan", "rock", "Rock & Alternative", "Rock, punk, metal, and alternative music", 4),
        ("fan", "electronic", "Electronic & Dance", "EDM, house, techno, and electronic artists", 5),
        ("fan", "pop", "Pop & Mainstream", "Pop hits, chart-toppers, and mainstream releases", 6),
        ("fan", "r-and-b", "R&B & Soul", "R&B, soul, neo-soul, and contemporary groove", 7),
        ("fan", "indie", "Indie & Underground", "Independent artists and underground discoveries", 8),
        ("artist", "singer-songwriter", "Singer-Songwriter", "Acoustic, folk-influenced, and lyric-driven artists", 1),
        ("artist", "producer-electronic", "Producer & Electronic", "Beat-makers, producers, and electronic music creators", 2),
        ("artist", "rapper", "Rapper & MC", "Hip-hop artists, rappers, and lyricists", 3),
        ("artist", "band", "Band & Ensemble", "Bands, duos, and collaborative groups", 4),
        ("artist", "solo-pop", "Solo Pop Artist", "Solo artists in pop, R&B, and mainstream genres", 5),
        ("industry", "streaming-platforms", "Streaming & Platforms", "Spotify, Apple Music, YouTube, and platform strategy", 1),
        ("industry", "sync-licensing", "Sync & Licensing", "Music in film, TV, ads, and gaming", 2),
        ("industry", "live-events", "Live & Touring", "Concerts, festivals, touring economics, and live revenue", 3),
        ("industry", "emerging-markets", "Emerging Markets", "Africa, Latin America, Southeast Asia, and growing music markets", 4),
        ("industry", "ai-and-tech", "AI & Music Tech", "Artificial intelligence, music tech startups, and innovation", 5),
        # Location-based markets (all editions)
        ("fan", "nashville", "Nashville", "Nashville music scene — country, Americana, indie, and Music Row", 10),
        ("fan", "los-angeles", "Los Angeles", "LA music scene — hip-hop, pop, indie, and entertainment industry", 11),
        ("fan", "new-york", "New York", "NYC music scene — hip-hop, jazz, punk, Broadway, and indie", 12),
        ("fan", "atlanta", "Atlanta", "Atlanta music scene — trap, hip-hop, R&B, and Southern rap", 13),
        ("fan", "london", "London", "London music scene — grime, electronic, indie, and global sounds", 14),
        ("fan", "austin", "Austin", "Austin music scene — live music capital, SXSW, indie, and country", 15),
        ("artist", "nashville", "Nashville", "Nashville artist community — songwriting, publishing, and Music Row opportunities", 10),
        ("artist", "los-angeles", "Los Angeles", "LA artist scene — studios, producers, sync placements, and industry connections", 11),
        ("artist", "new-york", "New York", "NYC artist scene — live venues, hip-hop, jazz, and creative collaborations", 12),
        ("artist", "atlanta", "Atlanta", "Atlanta artist scene — trap production, hip-hop, and Southern music business", 13),
        ("artist", "austin", "Austin", "Austin artist scene — live music, SXSW showcases, and indie community", 14),
        ("artist", "miami", "Miami", "Miami artist scene — Latin music, reggaeton, and tropical production", 15),
        ("industry", "nashville", "Nashville", "Nashville industry — publishing, songwriting deals, country labels, and Music Row", 10),
        ("industry", "los-angeles", "Los Angeles", "LA industry — major labels, sync licensing, film/TV music, and entertainment law", 11),
        ("industry", "new-york", "New York", "NYC industry — corporate label HQ, media, advertising sync, and live venues", 12),
        ("industry", "london", "London", "London industry — global labels, streaming strategy, and European market", 13),
    ]
    for edition, slug, name, desc, sort in markets:
        exists = conn.execute(
            f"SELECT id FROM edition_markets WHERE edition_slug = {ph} AND market_slug = {ph}",
            (edition, slug),
        ).fetchone()
        if not exists:
            try:
                conn.execute(
                    f"INSERT INTO edition_markets (edition_slug, market_slug, market_name, description, sort_order) VALUES ({ph}, {ph}, {ph}, {ph}, {ph})",
                    (edition, slug, name, desc, sort),
                )
                seeded += 1
            except integrity:
                pass

    # --- Artist newsletter templates ---
    nl_templates = [
        ("minimal", "Minimal", "<div style='max-width:600px;margin:0 auto;padding:20px;font-family:Georgia,serif;'><div style='text-align:center;padding:20px 0;border-bottom:2px solid {{brand_color}};'><h1 style='margin:0;color:{{brand_color}};'>{{artist_name}}</h1><p style='color:#666;margin:4px 0 0;'>{{tagline}}</p></div><div style='padding:20px 0;'>{{content}}</div><div style='border-top:1px solid #eee;padding:16px 0;font-size:12px;color:#999;text-align:center;'>Powered by TrueFans NEWSLETTERS</div></div>", 1),
        ("bold", "Bold", "<div style='max-width:600px;margin:0 auto;background:#1a1a1a;color:#fff;font-family:-apple-system,sans-serif;'><div style='padding:32px;text-align:center;background:{{brand_color}};'><h1 style='margin:0;font-size:28px;'>{{artist_name}}</h1><p style='margin:8px 0 0;opacity:0.8;'>{{tagline}}</p></div><div style='padding:24px;'>{{content}}</div><div style='padding:16px 24px;font-size:12px;color:#666;text-align:center;'>Powered by TrueFans NEWSLETTERS</div></div>", 0),
        ("clean", "Clean & Modern", "<div style='max-width:600px;margin:0 auto;padding:24px;font-family:-apple-system,sans-serif;'><div style='display:flex;align-items:center;gap:12px;padding-bottom:16px;border-bottom:1px solid #e5e7eb;'><div style='width:48px;height:48px;background:{{brand_color}};border-radius:50%;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:20px;'>{{artist_initials}}</div><div><h2 style='margin:0;font-size:18px;'>{{artist_name}}</h2><p style='margin:0;font-size:13px;color:#666;'>{{tagline}}</p></div></div><div style='padding:20px 0;'>{{content}}</div><div style='border-top:1px solid #e5e7eb;padding:16px 0;font-size:12px;color:#9ca3af;text-align:center;'>Powered by TrueFans NEWSLETTERS</div></div>", 0),
    ]
    for slug, name, html, is_default in nl_templates:
        exists = conn.execute(
            f"SELECT id FROM artist_newsletter_templates WHERE slug = {ph}", (slug,)
        ).fetchone()
        if not exists:
            try:
                conn.execute(
                    f"INSERT INTO artist_newsletter_templates (name, slug, html_template, is_default) VALUES ({ph}, {ph}, {ph}, {ph})",
                    (name, slug, html, is_default),
                )
                seeded += 1
            except integrity:
                pass

    # --- Marketing templates ---
    mktg_templates = [
        # Subscriber Growth - Email
        ("Welcome Series Invite", "email", "subscriber_growth", "You're missing out on TrueFans NEWSLETTERS",
         "Hi {{first_name}},\n\nMusic industry insights, artist tools, and fan discoveries — delivered 3x weekly to your inbox.\n\nJoin {{subscriber_count}}+ readers who trust TrueFans NEWSLETTERS for:\n\n• {{edition_benefit_1}}\n• {{edition_benefit_2}}\n• {{edition_benefit_3}}\n\nSubscribe free: {{subscribe_url}}\n\nSee you inside,\nPaul Saunders\nFounder, TrueFans NEWSLETTERS",
         "first_name,subscriber_count,edition_benefit_1,edition_benefit_2,edition_benefit_3,subscribe_url"),

        # Subscriber Growth - SMS
        ("SMS Subscribe Invite", "sms", "subscriber_growth", "",
         "Hey {{first_name}}! TrueFans NEWSLETTERS delivers music industry insights 3x/week. Join {{subscriber_count}}+ readers free: {{subscribe_url}}",
         "first_name,subscriber_count,subscribe_url"),

        # Subscriber Growth - AI Agent
        ("AI Subscriber Outreach", "ai_prompt", "subscriber_growth", "",
         "You are a friendly outreach agent for TrueFans NEWSLETTERS. Your goal is to invite {{contact_name}} to subscribe. Key points: we have 3 editions (Fan, Artist, Industry), publish 3x weekly, and have {{subscriber_count}} subscribers. Be warm, not pushy. Ask which edition interests them most.",
         "contact_name,subscriber_count"),

        # Sponsor Outreach - Email
        ("Sponsor Intro Email", "email", "sponsor_outreach", "Partnership opportunity: TrueFans NEWSLETTERS",
         "Hi {{contact_name}},\n\nI'm reaching out from TrueFans NEWSLETTERS — we publish 3 music newsletters (Fan, Artist, Industry) reaching {{subscriber_count}}+ engaged subscribers 3x weekly.\n\nOur audience includes:\n• Music fans who buy merch, tickets, and streaming subscriptions\n• Independent artists investing in gear, distribution, and education\n• Industry professionals making purchasing decisions\n\nWe offer premium sponsor placements (top/mid/bottom) with:\n• {{open_rate}}% open rate (industry avg: 22%)\n• {{click_rate}}% click rate\n• CPM starting at ${{base_cpm}}\n\nWould you be open to a quick call this week?\n\nBest,\nGrant Sullivan\nVP of Sales, TrueFans NEWSLETTERS",
         "contact_name,subscriber_count,open_rate,click_rate,base_cpm"),

        # Sponsor Outreach - SMS
        ("Sponsor SMS Follow-up", "sms", "sponsor_outreach", "",
         "Hi {{contact_name}}, Grant from TrueFans NEWSLETTERS here. Following up on the sponsorship opportunity I emailed about. Our music newsletter reaches {{subscriber_count}}+ subscribers 3x/week. Quick call this week? Reply YES and I'll send calendar link.",
         "contact_name,subscriber_count"),

        # Sponsor Outreach - Voice Script
        ("Sponsor Call Script", "voice_script", "sponsor_outreach", "",
         "Hi {{contact_name}}, this is Grant Sullivan from TrueFans NEWSLETTERS. I'm calling because I think {{company_name}} would be a perfect sponsor for our music newsletter. We reach {{subscriber_count}} engaged music professionals and fans 3 times a week. Our open rates are above {{open_rate}}%, which is well above industry average. I'd love to share our media kit and discuss how we can create a native sponsorship that feels authentic to your brand. Do you have 10 minutes this week for a quick call?",
         "contact_name,company_name,subscriber_count,open_rate"),

        # Sponsor Outreach - AI Agent
        ("AI Sponsor Research", "ai_prompt", "sponsor_outreach", "",
         "Research {{company_name}} ({{website}}) and identify why they would be a good sponsor for TrueFans NEWSLETTERS, a music newsletter with {{subscriber_count}} subscribers across Fan, Artist, and Industry editions. Find: 1) Their target audience overlap with our readers 2) Current advertising/sponsorship activity 3) Budget signals 4) Best contact person 5) Personalized pitch angle. Return a brief with all findings.",
         "company_name,website,subscriber_count"),

        # Retention - Email
        ("Win-back Email", "email", "retention", "We miss you at TrueFans NEWSLETTERS",
         "Hi {{first_name}},\n\nWe noticed you haven't opened TrueFans NEWSLETTERS in a while. We get it — inboxes are crowded.\n\nBut here's what you missed:\n• {{missed_highlight_1}}\n• {{missed_highlight_2}}\n• {{missed_highlight_3}}\n\nStill interested? Just click here to stay subscribed: {{resubscribe_url}}\n\nIf not, no hard feelings — you can unsubscribe anytime.\n\nKeep the music playing,\nThe TrueFans Team",
         "first_name,missed_highlight_1,missed_highlight_2,missed_highlight_3,resubscribe_url"),

        # Upsell - Email
        ("Pro Tier Upsell", "email", "upsell", "Unlock TrueFans Pro — ad-free + early access",
         "Hi {{first_name}},\n\nYou've been reading TrueFans NEWSLETTERS for {{weeks_subscribed}} weeks now. You're clearly serious about music.\n\nReady to level up? TrueFans Pro gives you:\n\n✅ Ad-free reading experience\n✅ Early access to every issue\n✅ Exclusive content and deep-dives\n✅ Trivia leaderboard perks\n\nAll for just ${{pro_price}}/month.\n\nUpgrade now: {{upgrade_url}}\n\nSee you at the top,\nPaul Saunders",
         "first_name,weeks_subscribed,pro_price,upgrade_url"),

        # Social Post
        ("Social Growth Post", "social_post", "subscriber_growth", "",
         "🎵 {{stat_number}} music professionals read TrueFans NEWSLETTERS every week.\n\n3 editions. 3x weekly. Always free.\n\n→ Fan Edition: backstage stories & discoveries\n→ Artist Edition: tools, gear & career strategy\n→ Industry Edition: deals, data & market moves\n\nJoin them: {{subscribe_url}}\n\n#MusicIndustry #Newsletter #IndieMusic",
         "stat_number,subscribe_url"),

        # Landing Page Copy
        ("Landing Page Copy", "landing_page", "subscriber_growth", "",
         "THE MUSIC NEWSLETTERS FOR PEOPLE WHO TAKE MUSIC SERIOUSLY\n\nWhether you're a fan who wants to go deeper, an artist building a career, or a professional making deals — TrueFans NEWSLETTERS delivers the insights you need.\n\n{{subscriber_count}}+ subscribers trust us 3x every week.\n\nChoose your edition:\n🎵 FAN EDITION — Backstage stories, deep-dives, and discoveries\n🎸 ARTIST EDITION — Songwriting, gear, marketing, and career strategy\n📊 INDUSTRY EDITION — Deals, streaming data, and market intelligence\n\nSubscribe free. Unsubscribe anytime.",
         "subscriber_count"),
    ]
    for name, ttype, cat, subject, content, variables in mktg_templates:
        exists = conn.execute(
            f"SELECT id FROM marketing_templates WHERE name = {ph}", (name,)
        ).fetchone()
        if not exists:
            try:
                conn.execute(
                    f"INSERT INTO marketing_templates (name, template_type, category, subject, content, variables) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})",
                    (name, ttype, cat, subject, content, variables),
                )
                seeded += 1
            except integrity:
                pass

    # --- Demo licensee for Nashville ---
    exists = conn.execute(
        f"SELECT id FROM licensees WHERE email = {ph}", ("demo@nashvillemusic.com",)
    ).fetchone()
    if not exists:
        try:
            import bcrypt
            pw_hash = bcrypt.hashpw(b"Nashville2026!", bcrypt.gensalt()).decode()
            conn.execute(
                f"""INSERT INTO licensees (company_name, contact_name, email, password_hash, city_market_slug, edition_slugs, license_type, license_fee_cents, revenue_share_pct, status)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, 'active')""",
                ("Nashville Music Media LLC", "Taylor Reed", "demo@nashvillemusic.com", pw_hash, "nashville", "fan,artist,industry", "monthly", 9900, 20.0),
            )
            seeded += 1
        except integrity:
            pass

    conn.commit()
    conn.close()
    if seeded:
        import logging
        logging.getLogger(__name__).info("Seeded %d content records", seeded)
    return seeded


def seed_guest_contacts(db_path: str = "", database_url: str = "", backend: str = "") -> int:
    """Insert default guest contacts. Returns count of newly inserted."""
    backend = backend or _get_backend()
    conn = get_connection(db_path, database_url, backend)
    p = _ph(backend)
    ierr = _integrity_errors(backend)
    inserted = 0
    for entry in DEFAULT_GUEST_CONTACTS:
        name, email, organization, role, category, website, notes = entry
        # Skip if contact with same name already exists
        existing = conn.execute(
            f"SELECT id FROM guest_contacts WHERE name = {p}", (name,)
        ).fetchone()
        if existing:
            # Sync category and website on existing contacts
            conn.execute(
                f"UPDATE guest_contacts SET category = {p} WHERE name = {p} AND (category IS NULL OR category = '')",
                (category, name),
            )
            if website:
                conn.execute(
                    f"UPDATE guest_contacts SET website = {p} WHERE name = {p} AND (website IS NULL OR website = '')",
                    (website, name),
                )
            continue
        try:
            conn.execute(
                f"""INSERT INTO guest_contacts
                   (name, email, organization, role, category, website, notes)
                   VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p})""",
                (name, email, organization, role, category, website, notes),
            )
            inserted += 1
        except ierr:
            if backend == "postgres":
                conn.rollback()
    conn.commit()
    conn.close()
    return inserted


# Default newsletter editions to seed on init
# (slug, name, tagline, description, audience, color, icon, section_slugs, sort_order)
DEFAULT_EDITIONS = [
    (
        "fan",
        "Fan Edition",
        "The insider scoop for music lovers",
        "Backstage stories, classic album deep-dives, lyric breakdowns, and creative inspiration — delivered to your inbox three times a week.",
        "Music fans and casual listeners",
        "#e8645a",
        "&#127911;",
        "backstage_pass,vinyl_vault,artist_spotlight,lyrics_unpacked,mondegreen,creative_fuel,the_muse,playlist_picks,concert_diary,music_discovery,fan_spotlight,fan_mail,greatest_songwriters,album_countdown,behind_the_lyrics",
        1,
    ),
    (
        "artist",
        "Artist Edition",
        "Level up your music career",
        "Songwriting techniques, vocal coaching, gear reviews, production tips, social media strategy, and DIY marketing — everything independent artists need to grow.",
        "Independent artists and songwriters",
        "#7c5cfc",
        "&#127928;",
        "coaching,songcraft,stage_ready,vocal_booth,gear_garage,production_notes,social_playbook,diy_marketing,brand_building,artist_spotlight,release_strategy,collaboration_corner,mental_health,touring_tips,fan_building",
        2,
    ),
    (
        "industry",
        "Industry Edition",
        "Data and deals that move the needle",
        "Industry news, deal analysis, streaming data, revenue strategies, rights and royalties explainers, music tech, and AI developments — for professionals who need to stay ahead.",
        "Industry professionals and music business",
        "#f59e0b",
        "&#128200;",
        "industry_pulse,deal_or_no_deal,streaming_dashboard,money_moves,rights_and_royalties,tech_talk,ai_music_lab,guest_column,executive_moves,global_markets,playlist_politics,startup_spotlight,festival_economy,catalog_watch,sync_and_licensing",
        3,
    ),
]


def seed_editions(db_path: str = "", database_url: str = "", backend: str = "") -> int:
    """Insert or update default newsletter editions. Returns count of newly inserted."""
    backend = backend or _get_backend()
    conn = get_connection(db_path, database_url, backend)
    p = _ph(backend)
    ierr = _integrity_errors(backend)
    inserted = 0
    for entry in DEFAULT_EDITIONS:
        slug, name, tagline, description, audience, color, icon, section_slugs, sort_order = entry
        try:
            conn.execute(
                f"""INSERT INTO newsletter_editions
                   (slug, name, tagline, description, audience, color, icon, section_slugs, sort_order)
                   VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})""",
                (slug, name, tagline, description, audience, color, icon, section_slugs, sort_order),
            )
            inserted += 1
        except ierr:
            if backend == "postgres":
                conn.rollback()
            # Edition exists — update section_slugs to pick up new sections
            conn.execute(
                f"UPDATE newsletter_editions SET section_slugs = {p} WHERE slug = {p}",
                (section_slugs, slug),
            )
    conn.commit()
    conn.close()
    return inserted


def seed_sections(db_path: str = "", database_url: str = "", backend: str = "") -> int:
    """Insert default section definitions. Returns count of newly inserted."""
    backend = backend or _get_backend()
    conn = get_connection(db_path, database_url, backend)
    p = _ph(backend)
    ierr = _integrity_errors(backend)
    inserted = 0
    for entry in DEFAULT_SECTIONS:
        slug, display_name, sort_order, section_type, wc_label, target_wc, category, series_type, series_length, description = entry
        try:
            conn.execute(
                f"""INSERT INTO section_definitions
                   (slug, display_name, sort_order, section_type, word_count_label,
                    target_word_count, category, series_type, series_length, description)
                   VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})""",
                (slug, display_name, sort_order, section_type, wc_label,
                 target_wc, category, series_type, series_length, description),
            )
            inserted += 1
        except ierr:
            if backend == "postgres":
                conn.rollback()
    conn.commit()
    conn.close()
    return inserted
