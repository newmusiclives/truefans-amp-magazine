"""Public newsletters page — edition details with section breakdowns."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from jinja2 import Environment, FileSystemLoader

from weeklyamp.core.config import load_config
from weeklyamp.db.repository import Repository
from weeklyamp.web.deps import get_repo as _get_repo, get_config as _get_config

_TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent.parent / "templates" / "web"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)

router = APIRouter()


@router.get("/preview/{issue_id}", response_class=HTMLResponse)
async def newsletter_preview(issue_id: int, request: Request):
    repo = _get_repo()
    config = _get_config()
    issue = repo.get_issue(issue_id)
    if not issue:
        return HTMLResponse("Issue not found", status_code=404)
    assembled = repo.get_assembled(issue_id)
    if not assembled:
        return HTMLResponse("Issue not assembled yet", status_code=404)
    subscriber_count = repo.get_subscriber_count()
    tpl = _env.get_template("newsletter_preview.html")
    return HTMLResponse(tpl.render(
        issue=issue, html_content=assembled.get("html_content", ""),
        subscriber_count=subscriber_count, config=config))


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


def _build_rss(
    issues: list[dict],
    repo,
    *,
    title: str,
    description: str,
    site_domain: str,
    self_url: str,
) -> str:
    """Render an RSS 2.0 feed from a list of issue dicts."""
    items = []
    for issue in issues:
        assembled = repo.get_assembled(issue["id"])
        pub_date = issue.get("publish_date", issue.get("created_at", ""))
        plain = (assembled or {}).get("plain_content") or ""
        desc = plain[:500] + "..." if plain else f"Issue #{issue['issue_number']}"
        item_title = f"{title} #{issue['issue_number']}"
        if issue.get("title"):
            item_title += f" — {issue['title']}"
        permalink = f"{site_domain}/newsletters/archive/{issue['issue_number']}"
        items.append(
            f"""    <item>
      <title>{item_title}</title>
      <link>{permalink}</link>
      <guid>{permalink}</guid>
      <pubDate>{pub_date}</pubDate>
      <description><![CDATA[{desc}]]></description>
    </item>"""
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{title}</title>
    <link>{site_domain}</link>
    <description>{description}</description>
    <language>en-us</language>
    <atom:link href="{self_url}" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>"""


def _build_json_feed(
    issues: list[dict],
    repo,
    *,
    title: str,
    description: str,
    site_domain: str,
    self_url: str,
) -> dict:
    """Render a JSON Feed 1.1 (https://jsonfeed.org/version/1.1) document."""
    items = []
    for issue in issues:
        assembled = repo.get_assembled(issue["id"])
        plain = (assembled or {}).get("plain_content") or ""
        permalink = f"{site_domain}/newsletters/archive/{issue['issue_number']}"
        items.append({
            "id": permalink,
            "url": permalink,
            "title": (
                f"{title} #{issue['issue_number']}"
                + (f" — {issue['title']}" if issue.get("title") else "")
            ),
            "content_text": plain,
            "date_published": issue.get("publish_date") or issue.get("created_at") or "",
        })
    return {
        "version": "https://jsonfeed.org/version/1.1",
        "title": title,
        "home_page_url": site_domain,
        "feed_url": self_url,
        "description": description,
        "items": items,
    }


@router.get("/feed.xml")
async def rss_feed():
    from fastapi.responses import Response
    cfg = load_config()
    site_domain = cfg.site_domain.rstrip("/")
    repo = _get_repo()
    issues = repo.get_published_issues(limit=20)
    xml = _build_rss(
        issues, repo,
        title=cfg.newsletter.name,
        description=cfg.newsletter.tagline,
        site_domain=site_domain,
        self_url=f"{site_domain}/feed.xml",
    )
    return Response(content=xml, media_type="application/rss+xml")


@router.get("/feed.json")
async def json_feed_global():
    from fastapi.responses import JSONResponse
    cfg = load_config()
    site_domain = cfg.site_domain.rstrip("/")
    repo = _get_repo()
    issues = repo.get_published_issues(limit=20)
    feed = _build_json_feed(
        issues, repo,
        title=cfg.newsletter.name,
        description=cfg.newsletter.tagline,
        site_domain=site_domain,
        self_url=f"{site_domain}/feed.json",
    )
    return JSONResponse(feed, media_type="application/feed+json")


@router.get("/feed/{edition_slug}.xml")
async def rss_feed_per_edition(edition_slug: str):
    from fastapi.responses import Response
    cfg = load_config()
    site_domain = cfg.site_domain.rstrip("/")
    repo = _get_repo()
    edition = next(
        (e for e in repo.get_editions() if e.get("slug") == edition_slug),
        None,
    )
    if not edition:
        return Response(content="Not found", status_code=404)
    all_issues = repo.get_published_issues(limit=100)
    issues = [i for i in all_issues if i.get("edition_slug") == edition_slug][:20]
    xml = _build_rss(
        issues, repo,
        title=f"{cfg.newsletter.name} — {edition.get('name', edition_slug)}",
        description=edition.get("tagline", "") or cfg.newsletter.tagline,
        site_domain=site_domain,
        self_url=f"{site_domain}/feed/{edition_slug}.xml",
    )
    return Response(content=xml, media_type="application/rss+xml")


@router.get("/feed/{edition_slug}.json")
async def json_feed_per_edition(edition_slug: str):
    from fastapi.responses import JSONResponse, Response
    cfg = load_config()
    site_domain = cfg.site_domain.rstrip("/")
    repo = _get_repo()
    edition = next(
        (e for e in repo.get_editions() if e.get("slug") == edition_slug),
        None,
    )
    if not edition:
        return Response(content="Not found", status_code=404)
    all_issues = repo.get_published_issues(limit=100)
    issues = [i for i in all_issues if i.get("edition_slug") == edition_slug][:20]
    feed = _build_json_feed(
        issues, repo,
        title=f"{cfg.newsletter.name} — {edition.get('name', edition_slug)}",
        description=edition.get("tagline", "") or cfg.newsletter.tagline,
        site_domain=site_domain,
        self_url=f"{site_domain}/feed/{edition_slug}.json",
    )
    return JSONResponse(feed, media_type="application/feed+json")


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
  <title>TrueFans SIGNAL — Issue #{issue_num}</title>
  <enclosure url="{cfg.site_domain}{ai['audio_url']}" type="audio/mpeg" length="{ai.get('file_size_bytes', 0)}"/>
  <pubDate>{ai.get('created_at', '')}</pubDate>
</item>\n"""

    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
<channel>
  <title>TrueFans SIGNAL Audio</title>
  <description>Audio versions of TrueFans SIGNAL</description>
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
