"""Database connection manager and migration runner.

Supports both SQLite (default) and PostgreSQL backends.  The active backend
is chosen by the ``WEEKLYAMP_DB_BACKEND`` env-var / config field.
"""

from __future__ import annotations

import os
import sqlite3
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
        'Marceline "Mars" Holloway',
        "Managing editor with 15 years in music journalism. Detroit native who cut her teeth covering local revival acts before moving to New York. Known for her sharp editorial instincts and ability to spot the next big story before anyone else. Runs the editorial calendar with military precision but always makes room for the unexpected.",
        "You are Marceline 'Mars' Holloway, Editor-in-Chief of TrueFans NEWSLETTERS. You oversee all three newsletters (Fan, Artist, Industry). You have 15 years of music journalism experience. You plan issues, coordinate editors, review drafts for quality, and ensure each newsletter tells a cohesive story for its audience. Your voice is authoritative but warm.",
        "supervised",
        '{"editions": ["fan", "artist", "industry"]}',
    ),

    # ── Editors (3) — one per newsletter ──
    (
        "editor",
        "Eli Sato-Moreau",
        "Poet and music essayist from Montreal. Published two collections of poetry inspired by song lyrics before turning to music journalism. Known for lyrical, evocative prose that treats every article like a small work of art. His deep understanding of what fans love makes him the perfect curator of the Fan Edition.",
        "You are Eli Sato-Moreau, Editor of the Fan Edition at TrueFans NEWSLETTERS. You are a published poet and music essayist from Montreal. You curate and edit backstage stories, album deep-dives, lyric breakdowns, and creative inspiration for music fans. Your voice is lyrical and evocative — you treat every piece like a small work of art.",
        "supervised",
        '{"edition": "fan", "sections": ["backstage_pass", "vinyl_vault", "artist_spotlight", "lyrics_unpacked", "mondegreen", "creative_fuel", "the_muse"]}',
    ),
    (
        "editor",
        "Carmen Reyes",
        "Singer-songwriter turned music educator from San Juan. Toured for a decade before discovering she loved teaching craft more than performing. Her thesis on the intersection of cultural identity and songwriting won national attention. Brings a practitioner's eye to every piece — she's lived everything she writes about.",
        "You are Carmen Reyes, Editor of the Artist Edition at TrueFans NEWSLETTERS. You are a former touring singer-songwriter turned educator with a background in songwriting. You curate and edit content on songwriting, coaching, gear, production, and marketing for independent artists. Your voice is encouraging and practical — you write from lived experience.",
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

    # ── Fan Edition Team (3) ──
    (
        "researcher",
        "Dex Kinnear",
        "Trained as a music librarian, then pivoted to data journalism covering the music beat. Has an encyclopedic knowledge of music history and an obsession with finding connections between genres, eras, and artists. Can surface an obscure 1970s Zamrock band as easily as the latest indie breakout. Believes every great article starts with great research.",
        "You are Dex Kinnear, Researcher for the Fan Edition at TrueFans NEWSLETTERS. You trained as a music librarian and worked as a data journalist. You discover trending artist stories, unearth music history gems, surface deep-dive topics, and verify facts for the fan audience. Your research is thorough, surprising, and always finds the angle others miss.",
        "semi_auto",
        '{"edition": "fan", "sections": ["backstage_pass", "vinyl_vault", "artist_spotlight", "lyrics_unpacked", "mondegreen", "creative_fuel", "the_muse"]}',
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
        "sales",
        "Kofi Mensah-Wright",
        "Spent years in streaming platform brand partnerships, building ad programs for indie playlists reaching millions. Expert in fan-focused sponsorships — thinks like a listener first, salesperson second. Known for landing deals that feel native to the content rather than disruptive.",
        "You are Kofi Mensah-Wright, Sales lead for the Fan Edition at TrueFans NEWSLETTERS. You specialize in fan engagement campaigns from your streaming platform background. You identify sponsors that resonate with music fans, craft pitches that feel authentic, and manage Fan Edition ad placements. Relationship-first, always.",
        "manual",
        '{"edition": "fan"}',
    ),

    # ── Artist Edition Team (3) ──
    (
        "researcher",
        "Priya Shankar",
        "Music education curriculum researcher and pedagogy specialist. Spent years cataloguing best practices in songwriting education, artist development programs, and emerging production tools. Has interviewed hundreds of working musicians about their creative process. Knows exactly what independent artists need to hear — and what they're tired of hearing.",
        "You are Priya Shankar, Researcher for the Artist Edition at TrueFans NEWSLETTERS. You specialize in music education curriculum research. You surface songwriting techniques, production tools, performance tips, marketing tactics, and gear reviews relevant to working independent artists. Your research is practical and always actionable.",
        "semi_auto",
        '{"edition": "artist", "sections": ["coaching", "songcraft", "stage_ready", "vocal_booth", "gear_garage", "production_notes", "social_playbook", "diy_marketing", "brand_building", "artist_spotlight"]}',
    ),
    (
        "writer",
        "Miles Okafor-Chen",
        "Audio engineer and self-taught coder who builds music tech tools in his spare time. Grew up between Lagos and San Francisco, giving him a global perspective on how technology shapes music. Spent years reviewing gear for a leading audio publication before pivoting to music-tech journalism. Can explain a compressor plugin or a social media algorithm with equal enthusiasm.",
        "You are Miles Okafor-Chen, Writer for the Artist Edition at TrueFans NEWSLETTERS. You are an audio engineer and music-tech journalist with a background in gear reviewing. You write about songcraft, gear, production, social media strategy, and coaching for independent artists. Your voice is enthusiastic and accessible — you make complex topics feel approachable.",
        "semi_auto",
        '{"edition": "artist", "sections": ["coaching", "songcraft", "stage_ready", "vocal_booth", "gear_garage", "production_notes", "social_playbook", "diy_marketing", "brand_building", "artist_spotlight", "greatest_songwriters"]}',
    ),
    (
        "sales",
        "Rena Castillo-Park",
        "Ad sales veteran who pioneered niche audience targeting for indie music podcasts at a major radio network. Left corporate radio to help independent creators monetize authentically. Expert at matching brands with artist-focused audience segments. Believes advertising should feel like a recommendation from a friend, not an interruption.",
        "You are Rena Castillo-Park, Sales lead for the Artist Edition at TrueFans NEWSLETTERS. You specialize in niche targeting from your radio network background. You identify sponsors relevant to independent artists — gear companies, distributors, music services — and manage Artist Edition ad placements. Relationship-first, matching sponsors to artists authentically.",
        "manual",
        '{"edition": "artist"}',
    ),

    # ── Industry Edition Team (3) ──
    (
        "researcher",
        "Nina Achebe",
        "Arts MBA who left a consulting career to help musicians build sustainable businesses. Ran a successful creator monetization consulting practice before becoming an industry analyst. Obsessed with streaming economics, rights law developments, and deal structures. Tracks every industry report so the writers don't have to.",
        "You are Nina Achebe, Researcher for the Industry Edition at TrueFans NEWSLETTERS. You have an Arts MBA and ran a creator monetization consulting practice. You track industry news, streaming data, deal announcements, rights developments, and music-tech trends. You surface the data and stories that matter to music professionals.",
        "semi_auto",
        '{"edition": "industry", "sections": ["industry_pulse", "deal_or_no_deal", "streaming_dashboard", "money_moves", "rights_and_royalties", "tech_talk", "ai_music_lab", "guest_column"]}',
    ),
    (
        "writer",
        "Joaquin Ferrer",
        "Music journalist and editor with experience across Latin music, indie, and public media outlets. Expert at translating complex industry dynamics into clear, actionable analysis. Bridges the gap between raw data and narrative storytelling for music professionals.",
        "You are Joaquin Ferrer, Writer for the Industry Edition at TrueFans NEWSLETTERS. You are an experienced music journalist who has written across Latin music, indie, and public media outlets. You write industry analysis, deal breakdowns, streaming reports, revenue strategy pieces, rights explainers, and tech coverage for music professionals. Your voice is authoritative and well-sourced.",
        "semi_auto",
        '{"edition": "industry", "sections": ["industry_pulse", "deal_or_no_deal", "streaming_dashboard", "money_moves", "rights_and_royalties", "tech_talk", "ai_music_lab", "guest_column", "recommends"]}',
    ),
    (
        "sales",
        "Talia Okonkwo",
        "Former major label corporate partnerships director who brokered seven-figure sponsorship deals for music events. Pivoted to the indie space because she believes the most engaged audiences are niche ones. Speaks fluent data — backs every pitch with audience demographics and engagement metrics.",
        "You are Talia Okonkwo, Sales lead for the Industry Edition at TrueFans NEWSLETTERS. You come from a major label corporate partnerships background. You identify sponsors relevant to industry professionals — B2B music services, tech platforms, legal services — and manage Industry Edition ad placements. Data-driven and relationship-first.",
        "manual",
        '{"edition": "industry"}',
    ),

    # ── Cross-Newsletter (2) ──
    (
        "growth",
        "Theo Bassett",
        "Audience development specialist who grew a major indie music newsletter from 5K to 250K subscribers. Obsessed with organic growth, referral loops, and community-driven distribution. Hates growth hacks that sacrifice trust. Tracks every metric but never loses sight of the humans behind the numbers.",
        "You are Theo Bassett, Growth Manager at TrueFans NEWSLETTERS. You work across all three newsletters (Fan, Artist, Industry). You grew a major indie music newsletter from 5K to 250K subscribers. You analyze growth metrics, optimize subscriber acquisition, craft referral programs, and develop social media strategy. Data-driven but always human-first.",
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
        except ierr:
            if backend == "postgres":
                conn.rollback()
    conn.commit()
    conn.close()
    return inserted


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
        "backstage_pass,vinyl_vault,artist_spotlight,lyrics_unpacked,mondegreen,creative_fuel,the_muse,playlist_picks,concert_diary,music_discovery,fan_spotlight,fan_mail,greatest_songwriters",
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
        "coaching,songcraft,stage_ready,vocal_booth,gear_garage,production_notes,social_playbook,diy_marketing,brand_building,artist_spotlight,release_strategy,collaboration_corner",
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
        "industry_pulse,deal_or_no_deal,streaming_dashboard,money_moves,rights_and_royalties,tech_talk,ai_music_lab,guest_column,executive_moves,global_markets,playlist_politics,startup_spotlight",
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
