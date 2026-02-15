"""Content relevance scoring and section matching."""

from __future__ import annotations

import re

# Keyword sets per section for basic relevance scoring
SECTION_KEYWORDS: dict[str, list[str]] = {
    # Music Industry
    "backstage_pass": [
        "story", "interview", "behind the scenes", "making of", "recording",
        "studio", "biography", "career", "journey", "legend", "iconic",
    ],
    "industry_pulse": [
        "music industry", "record label", "music business", "streaming",
        "billboard", "chart", "trend", "market", "revenue", "acquisition",
        "merger", "lawsuit", "regulation", "policy",
    ],
    "deal_or_no_deal": [
        "record deal", "contract", "negotiate", "advance", "signing",
        "360 deal", "distribution deal", "publishing deal", "terms",
        "independent", "major label", "deal structure",
    ],
    "streaming_dashboard": [
        "spotify", "apple music", "streaming numbers", "playlist",
        "streams", "listeners", "algorithm", "discovery", "analytics",
        "tidal", "youtube music", "deezer",
    ],
    # Artist Development
    "coaching": [
        "inspiration", "motivation", "lesson", "advice", "mindset",
        "success", "practice", "discipline", "creative", "growth",
    ],
    "greatest_songwriters": [
        "songwriter", "songwriting", "lyricist", "compose", "classic",
        "greatest", "legendary", "hall of fame", "singer-songwriter",
    ],
    "stage_ready": [
        "live performance", "stage presence", "concert", "tour",
        "setlist", "soundcheck", "venue", "audience", "performer",
        "stage fright", "showmanship", "live show",
    ],
    "songcraft": [
        "songwriting", "melody", "chord progression", "verse", "chorus",
        "bridge", "hook", "co-writing", "creative process", "writer's block",
        "composition", "arrangement",
    ],
    "vocal_booth": [
        "vocal", "singing", "voice", "pitch", "range", "technique",
        "warm up", "breathing", "falsetto", "belt", "harmony",
        "vocal health", "vocal coach",
    ],
    "artist_spotlight": [
        "independent artist", "emerging", "debut", "breakout", "unsigned",
        "indie artist", "rising star", "new release", "feature",
        "spotlight", "profile", "interview",
    ],
    # Technology
    "tech_talk": [
        "technology", "tech", "software", "digital", "streaming",
        "social media", "marketing", "distribution", "platform", "AI",
        "production", "DAW", "plugin", "audio",
    ],
    "ai_music_lab": [
        "artificial intelligence", "AI music", "machine learning",
        "generative", "synthesizer", "neural", "algorithm", "automation",
        "AI tools", "music AI", "stem separation", "mastering AI",
    ],
    "gear_garage": [
        "guitar", "keyboard", "microphone", "interface", "monitors",
        "headphones", "pedal", "amp", "instrument", "gear review",
        "equipment", "budget gear", "home studio",
    ],
    "social_playbook": [
        "social media", "instagram", "tiktok", "youtube", "content strategy",
        "followers", "engagement", "viral", "reels", "shorts",
        "social algorithm", "posting schedule",
    ],
    "production_notes": [
        "recording", "mixing", "mastering", "production", "DAW",
        "EQ", "compression", "reverb", "arrangement", "session",
        "producer", "beat", "sample",
    ],
    # Business
    "recommends": [
        "book", "course", "tool", "resource", "recommend", "review",
        "guide", "tutorial", "software", "app", "plugin", "gear",
    ],
    "money_moves": [
        "revenue", "income", "monetize", "money", "financial",
        "budget", "investing", "merch", "sync", "licensing",
        "royalties", "passive income", "diversify",
    ],
    "brand_building": [
        "brand", "identity", "logo", "aesthetic", "visual",
        "image", "persona", "niche", "positioning", "story",
        "branding", "artist brand",
    ],
    "rights_and_royalties": [
        "copyright", "royalty", "publishing", "licensing", "sync",
        "mechanical", "performance rights", "ASCAP", "BMI", "SESAC",
        "intellectual property", "rights",
    ],
    "diy_marketing": [
        "marketing", "promotion", "email list", "newsletter",
        "press release", "playlist pitching", "PR", "campaign",
        "launch strategy", "indie marketing", "grassroots",
    ],
    # Inspiration
    "mondegreen": [
        "lyric", "misheard", "meaning", "analysis", "interpretation",
        "words", "verse", "chorus", "mondegreen", "song meaning",
    ],
    "ps_from_ps": [
        "takeaway", "action", "summary", "reflection", "personal",
    ],
    "creative_fuel": [
        "inspiration", "creative prompt", "idea", "spark", "exercise",
        "challenge", "creativity", "muse", "journal", "brainstorm",
    ],
    "vinyl_vault": [
        "classic album", "vinyl", "retrospective", "reissue", "hidden gem",
        "underrated", "anniversary", "catalog", "deep cut", "music history",
    ],
    "the_muse": [
        "breakthrough", "eureka", "inspiration story", "creative moment",
        "turning point", "discovery", "epiphany", "creative journey",
    ],
    "lyrics_unpacked": [
        "lyrics", "lyric analysis", "meaning", "metaphor", "symbolism",
        "poetry", "wordplay", "storytelling", "verse", "interpretation",
    ],
    # Community
    "fan_mail": [
        "reader", "question", "feedback", "letter", "fan",
        "community", "response", "ask", "shout out",
    ],
    "truefans_connect": [
        "community", "truefans", "connect", "network", "collaboration",
        "platform", "member", "feature", "highlight",
    ],
    "community_wins": [
        "achievement", "win", "milestone", "success", "celebration",
        "congratulations", "progress", "accomplishment",
    ],
    # Guest Content
    "guest_column": [
        "guest", "expert", "opinion", "perspective", "industry",
        "thought leadership", "contributor", "editorial",
    ],
}


def score_content(title: str, summary: str, section_slug: str) -> float:
    """Score content relevance to a section (0.0-1.0)."""
    keywords = SECTION_KEYWORDS.get(section_slug, [])
    if not keywords:
        return 0.0

    text = f"{title} {summary}".lower()
    matches = sum(1 for kw in keywords if kw.lower() in text)
    return min(matches / max(len(keywords) * 0.3, 1), 1.0)


def match_sections(title: str, summary: str, threshold: float = 0.2) -> list[tuple[str, float]]:
    """Return list of (section_slug, score) pairs above threshold."""
    results = []
    for slug in SECTION_KEYWORDS:
        score = score_content(title, summary, slug)
        if score >= threshold:
            results.append((slug, score))
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def score_and_tag_content(repo, content_id: int, title: str, summary: str) -> None:
    """Score a raw_content item and update its matched_sections + relevance_score."""
    matches = match_sections(title, summary)
    if matches:
        best_score = matches[0][1]
        section_slugs = ",".join(slug for slug, _ in matches)
        conn = repo._conn()
        conn.execute(
            "UPDATE raw_content SET relevance_score = ?, matched_sections = ? WHERE id = ?",
            (best_score, section_slugs, content_id),
        )
        conn.commit()
        conn.close()
