"""Public newsletters page — edition details with section breakdowns."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
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
    tpl = _env.get_template("archive_issue.html")
    return tpl.render(issue=issue, content=assembled["html_content"])


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
