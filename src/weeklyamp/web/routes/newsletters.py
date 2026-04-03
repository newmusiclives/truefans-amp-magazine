"""Public newsletters page — edition details with section breakdowns."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from jinja2 import Environment, FileSystemLoader

from weeklyamp.core.config import load_config
from weeklyamp.db.repository import Repository
from weeklyamp.web.deps import get_repo as _get_repo

_TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent.parent / "templates" / "web"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)

router = APIRouter()


@router.get("/newsletters/archive", response_class=HTMLResponse)
async def newsletters_archive():
    repo = _get_repo()
    issues = repo.get_published_issues(limit=50)
    tpl = _env.get_template("archive.html")
    return tpl.render(issues=issues)


@router.get("/newsletters/archive/{issue_number}", response_class=HTMLResponse)
async def newsletter_issue(issue_number: int):
    repo = _get_repo()
    cfg = load_config()
    # Find the issue by number
    issues = repo.get_published_issues(limit=100)
    issue = next((i for i in issues if i["issue_number"] == issue_number), None)
    if not issue:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)
    assembled = repo.get_assembled(issue["id"])
    if not assembled:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)
    # Audio player
    audio = repo.get_audio_issue(issue["id"])
    audio_url = audio.get("audio_url", "") if audio and audio.get("status") == "complete" else ""
    # SEO description from plain text
    plain = assembled.get("plain_content") or ""
    description = " ".join(plain.split())[:200].rsplit(" ", 1)[0] if plain.strip() else ""
    # Related issues
    related = repo.get_related_issues(issue.get("edition_slug", ""), issue["id"], limit=3)
    tpl = _env.get_template("archive_issue.html")
    return tpl.render(issue=issue, content=assembled["html_content"],
        description=description, site_domain=cfg.site_domain, related_issues=related,
        audio_url=audio_url)


@router.get("/feed.xml")
async def rss_feed():
    from fastapi.responses import Response
    cfg = load_config()
    site_domain = cfg.site_domain.rstrip("/")
    nl_name = cfg.newsletter.name
    nl_tagline = cfg.newsletter.tagline

    repo = _get_repo()
    issues = repo.get_published_issues(limit=20)

    items = []
    for issue in issues:
        assembled = repo.get_assembled(issue["id"])
        pub_date = issue.get("publish_date", issue.get("created_at", ""))
        description = assembled["plain_content"][:500] + "..." if assembled and assembled.get("plain_content") else f"Issue #{issue['issue_number']}"
        items.append(
            f"""    <item>
      <title>{nl_name} #{issue['issue_number']}{(' — ' + issue['title']) if issue.get('title') else ''}</title>
      <link>{site_domain}/newsletters/archive/{issue['issue_number']}</link>
      <guid>{site_domain}/newsletters/archive/{issue['issue_number']}</guid>
      <pubDate>{pub_date}</pubDate>
      <description><![CDATA[{description}]]></description>
    </item>"""
        )

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{nl_name}</title>
    <link>{site_domain}</link>
    <description>{nl_tagline}</description>
    <language>en-us</language>
    <atom:link href="{site_domain}/feed.xml" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>"""
    return Response(content=xml, media_type="application/xml")


@router.get("/newsletters", response_class=HTMLResponse)
async def newsletters_page():
    repo = _get_repo()
    editions = repo.get_editions(active_only=True)

    # Resolve section_slugs to full section details
    all_sections = repo.get_all_sections()
    sections_map = {s["slug"]: s for s in all_sections}

    editions_with_sections = []
    for ed in editions:
        slugs = [s.strip() for s in ed.get("section_slugs", "").split(",") if s.strip()]
        resolved = [sections_map[s] for s in slugs if s in sections_map]
        editions_with_sections.append({**ed, "sections": resolved})

    tpl = _env.get_template("newsletters.html")
    return tpl.render(editions=editions_with_sections)


@router.get("/audio/{issue_id}")
async def serve_audio(issue_id: int):
    from weeklyamp.content.audio import get_audio_file_path
    from fastapi.responses import FileResponse
    path = get_audio_file_path(issue_id)
    if not path:
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("Audio not available", status_code=404)
    return FileResponse(str(path), media_type="audio/mpeg", filename=f"truefans_issue_{issue_id}.mp3")


@router.get("/feed/podcast.xml", response_class=HTMLResponse)
async def podcast_feed(request: Request):
    repo = _get_repo()
    cfg = load_config()
    audio_issues = repo.get_audio_issues(limit=50)
    # Build simple RSS podcast feed
    items = ""
    for ai in audio_issues:
        if ai.get("status") == "complete" and ai.get("audio_url"):
            issue_num = ai.get("issue_number", "")
            items += f"""<item>
  <title>TrueFans NEWSLETTERS — Issue #{issue_num}</title>
  <enclosure url="{cfg.site_domain}{ai['audio_url']}" type="audio/mpeg" length="{ai.get('file_size_bytes', 0)}"/>
  <pubDate>{ai.get('created_at', '')}</pubDate>
</item>\n"""

    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
<channel>
  <title>TrueFans NEWSLETTERS Audio</title>
  <description>Audio versions of TrueFans NEWSLETTERS</description>
  <link>{cfg.site_domain}</link>
  <language>en-us</language>
  {items}
</channel>
</rss>"""
    from fastapi.responses import Response
    return Response(content=feed, media_type="application/rss+xml")


@router.get("/articles/{edition_slug}/{section_slug}/{issue_number}", response_class=HTMLResponse)
async def standalone_article(edition_slug: str, section_slug: str, issue_number: int, request: Request):
    repo = _get_repo()
    config = load_config()
    # Find the issue
    conn = repo._conn()
    issue = conn.execute("SELECT * FROM issues WHERE issue_number = ? AND edition_slug = ?", (issue_number, edition_slug)).fetchone()
    if not issue:
        conn.close()
        return HTMLResponse("Article not found", status_code=404)
    issue = dict(issue)
    # Find the draft for this section
    draft = conn.execute(
        "SELECT * FROM drafts WHERE issue_id = ? AND section_slug = ? AND status IN ('approved','revised') ORDER BY version DESC LIMIT 1",
        (issue["id"], section_slug),
    ).fetchone()
    conn.close()
    if not draft:
        return HTMLResponse("Article not found", status_code=404)
    draft = dict(draft)
    # Get section display name
    sections = repo.get_all_sections()
    section = next((s for s in sections if s.get("slug") == section_slug), {})
    display_name = section.get("display_name", section_slug.replace("_", " ").title())

    import markdown
    from weeklyamp.web.sanitize import sanitize_html
    content_html = sanitize_html(markdown.markdown(draft["content"] or "", extensions=["extra"]))
    description = " ".join((draft["content"] or "").split()[:30])

    tpl = _env.get_template("article.html")
    return HTMLResponse(tpl.render(
        issue=issue, section_slug=section_slug, display_name=display_name,
        content_html=content_html, description=description,
        site_domain=config.site_domain, edition_slug=edition_slug))
