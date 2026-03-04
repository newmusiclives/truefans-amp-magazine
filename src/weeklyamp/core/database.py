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
    ("ps_from_ps", "PS FROM PS", 999, "core", "short", 125, "inspiration", "ongoing", 0, "Personal sign-off and reflection"),
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
    ("Jay Gilbert", "", "Independent", "A&R Consultant", "Music Business & Strategy", "", "A&R and artist development. Sections: deal_or_no_deal, artist_spotlight, guest_column"),
    ("Larry Miller", "", "Musonomics", "Music Business Professor", "Music Business & Strategy", "", "NYU music business professor. Sections: industry_pulse, streaming_dashboard, guest_column"),
    ("Vickie Nauman", "", "CrossBorderWorks", "Music Tech Consultant", "Music Business & Strategy", "https://crossborderworks.com", "Music licensing & tech strategy. Sections: industry_pulse, tech_talk, guest_column"),
    ("Mark Mulligan", "", "MIDiA Research", "Music Industry Analyst", "Music Business & Strategy", "https://midiaresearch.com", "Streaming & market analysis. Sections: streaming_dashboard, industry_pulse, guest_column"),

    # ── Songwriting & Composition (8) ──
    ("Andrea Stolpe", "", "Berklee Online", "Songwriting Professor", "Songwriting & Composition", "https://andreastolpe.com", "Songwriting education. Sections: songcraft, coaching, guest_column"),
    ("Cliff Goldmacher", "", "Independent", "Songwriter / Educator", "Songwriting & Composition", "https://cliffgoldmacher.com", "Songwriting craft & business. Sections: songcraft, money_moves, guest_column"),
    ("Pat Pattison", "", "Berklee College of Music", "Songwriting Professor", "Songwriting & Composition", "https://www.patpattison.com", "Lyric writing authority. Sections: songcraft, lyrics_unpacked, guest_column"),
    ("Fiona Bevan", "", "Independent", "Songwriter", "Songwriting & Composition", "https://fionabevan.com", "Co-writer for major artists. Sections: songcraft, backstage_pass, guest_column"),
    ("Erin McKeown", "", "Berklee College of Music", "Musician / Professor", "Songwriting & Composition", "https://erinmckeown.com", "Songwriting & artist rights. Sections: songcraft, rights_and_royalties, guest_column"),
    ("Ralph Murphy", "", "ASCAP", "Songwriter / Educator", "Songwriting & Composition", "", "Hit songwriting craft & structure. Sections: songcraft, coaching, guest_column"),
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
    ("Jewly Hight", "", "NPR / Nashville Scene", "Music Journalist", "Music Journalism & Criticism", "", "Country & Americana coverage. Sections: backstage_pass, artist_spotlight, guest_column"),
    ("Jeff Weiss", "", "Passion of the Weiss", "Music Journalist", "Music Journalism & Criticism", "https://www.passionweiss.com", "Hip hop criticism. Sections: backstage_pass, lyrics_unpacked, guest_column"),
    ("Philip Sherburne", "", "Pitchfork / Resident Advisor", "Music Journalist", "Music Journalism & Criticism", "", "Electronic music criticism. Sections: backstage_pass, production_notes, guest_column"),
    ("Nate Chinen", "", "WBGO / Author", "Jazz Journalist", "Music Journalism & Criticism", "https://natechinen.com", "Jazz criticism & reporting. Sections: backstage_pass, artist_spotlight, guest_column"),
    ("Kim Kelly", "", "Independent", "Music Journalist", "Music Journalism & Criticism", "", "Metal & punk coverage. Sections: backstage_pass, artist_spotlight, guest_column"),
    ("Hanif Abdurraqib", "", "Independent", "Author / Poet / Critic", "Music Journalism & Criticism", "https://hanifabdurraqib.com", "Music & culture essays. Sections: backstage_pass, lyrics_unpacked, guest_column"),
    ("Lindsay Zoladz", "", "NY Times / Vulture", "Music Critic", "Music Journalism & Criticism", "", "Pop & indie music criticism. Sections: backstage_pass, vinyl_vault, guest_column"),

    # ── Touring & Live Performance (5) ──
    ("Martin Atkins", "", "Millikin University", "Author / Touring Expert", "Touring & Live Performance", "https://martinatkins.com", "Tour:Smart author. Sections: stage_ready, coaching, guest_column"),
    ("Ari Nisman", "", "Independent", "Booking Agent", "Touring & Live Performance", "", "Live music booking. Sections: stage_ready, money_moves, guest_column"),
    ("Chris Robley", "", "CD Baby / Independent", "Musician / Writer", "Touring & Live Performance", "https://chrisrobley.com", "DIY music career. Sections: coaching, diy_marketing, guest_column"),
    ("Tom Jackson", "", "Onstage Success", "Live Show Producer", "Touring & Live Performance", "https://onstagesuccess.com", "Live performance coaching. Sections: stage_ready, coaching, guest_column"),
    ("Jenn Schott", "", "Independent", "Tour Manager", "Touring & Live Performance", "", "Tour logistics & management. Sections: stage_ready, money_moves, guest_column"),

    # ── Music Technology & AI (7) ──
    ("Dmitri Vietze", "", "Rock Paper Scissors", "Music Tech PR", "Music Technology & AI", "https://rockpaperscissors.biz", "Music tech publicity & trends. Sections: tech_talk, ai_music_lab, guest_column"),
    ("Cherie Hu", "", "Water & Music", "Music Tech Researcher", "Music Technology & AI", "https://waterandmusic.com", "Music industry & tech research. Sections: tech_talk, ai_music_lab, guest_column"),
    ("Bas Grasmayer", "", "MUSIC x", "Music Tech Strategist", "Music Technology & AI", "https://musicxtechxfuture.com", "Music-tech futures. Sections: tech_talk, ai_music_lab, guest_column"),
    ("Tatiana Cirisano", "", "MIDiA Research", "Music Analyst", "Music Technology & AI", "", "Gen Z listening habits & social audio. Sections: social_playbook, streaming_dashboard, guest_column"),
    ("Sam Barker", "", "Independent", "Artist / Technologist", "Music Technology & AI", "", "Generative music & creative AI. Sections: ai_music_lab, production_notes, guest_column"),
    ("Panos Panay", "", "Berklee / Splice", "Music Innovation Leader", "Music Technology & AI", "", "Music education & platform innovation. Sections: tech_talk, industry_pulse, guest_column"),
    ("Hypebot Editorial", "", "Hypebot", "Music Tech Publication", "Music Technology & AI", "https://hypebot.com", "Music tech news & analysis. Sections: tech_talk, social_playbook, guest_column"),

    # ── Rights, Licensing & Legal (6) ──
    ("Dina LaPolt", "", "LaPolt Law", "Entertainment Attorney", "Rights, Licensing & Legal", "https://lapoltlaw.com", "Music copyright & deals. Sections: rights_and_royalties, deal_or_no_deal, guest_column"),
    ("Erin Jacobson", "", "Indie Artist Resource", "Music Attorney", "Rights, Licensing & Legal", "https://erinmjacobson.com", "Music law for indie artists. Sections: rights_and_royalties, money_moves, guest_column"),
    ("Jeff Brabec", "", "Independent", "Music Licensing Author", "Rights, Licensing & Legal", "", "Sync licensing expert. Sections: rights_and_royalties, money_moves, guest_column"),
    ("Ciara Torres-Spelliscy", "", "Stetson Law", "Law Professor", "Rights, Licensing & Legal", "", "Copyright & First Amendment. Sections: rights_and_royalties, industry_pulse, guest_column"),
    ("John Simson", "", "SoundExchange (Former)", "Royalty Collection Expert", "Rights, Licensing & Legal", "", "Digital performance royalties. Sections: rights_and_royalties, streaming_dashboard, guest_column"),
    ("Mita Carriman", "", "Carriman Consulting", "Music Business Consultant", "Rights, Licensing & Legal", "", "International licensing & publishing. Sections: rights_and_royalties, deal_or_no_deal, guest_column"),
]


def seed_guest_contacts(db_path: str) -> int:
    """Insert default guest contacts. Returns count of newly inserted."""
    conn = get_connection(db_path)
    inserted = 0
    for entry in DEFAULT_GUEST_CONTACTS:
        name, email, organization, role, category, website, notes = entry
        # Skip if contact with same name already exists
        existing = conn.execute(
            "SELECT id FROM guest_contacts WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            # Update category on existing contacts if empty
            conn.execute(
                "UPDATE guest_contacts SET category = ? WHERE name = ? AND (category IS NULL OR category = '')",
                (category, name),
            )
            continue
        try:
            conn.execute(
                """INSERT INTO guest_contacts
                   (name, email, organization, role, category, website, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (name, email, organization, role, category, website, notes),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            pass
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
        "backstage_pass,vinyl_vault,artist_spotlight,lyrics_unpacked,mondegreen,creative_fuel,the_muse",
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
        "coaching,songcraft,stage_ready,vocal_booth,gear_garage,production_notes,social_playbook,diy_marketing,brand_building,artist_spotlight",
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
        "industry_pulse,deal_or_no_deal,streaming_dashboard,money_moves,rights_and_royalties,tech_talk,ai_music_lab,guest_column",
        3,
    ),
]


def seed_editions(db_path: str) -> int:
    """Insert default newsletter editions. Returns count of newly inserted."""
    conn = get_connection(db_path)
    inserted = 0
    for entry in DEFAULT_EDITIONS:
        slug, name, tagline, description, audience, color, icon, section_slugs, sort_order = entry
        try:
            conn.execute(
                """INSERT INTO newsletter_editions
                   (slug, name, tagline, description, audience, color, icon, section_slugs, sort_order)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (slug, name, tagline, description, audience, color, icon, section_slugs, sort_order),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            pass  # already exists
    conn.commit()
    conn.close()
    return inserted


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
