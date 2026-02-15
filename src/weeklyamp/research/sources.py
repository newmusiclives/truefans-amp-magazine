"""Source manager — loads sources from config and DB, orchestrates fetching."""

from __future__ import annotations

from rich.console import Console

from weeklyamp.core.config import load_sources_config
from weeklyamp.db.repository import Repository
from weeklyamp.research.rss import parse_feed
from weeklyamp.research.scraper import scrape_articles

console = Console()


def sync_sources_from_config(repo: Repository) -> int:
    """Ensure all sources from sources.yaml are in the DB. Returns new count."""
    config_sources = load_sources_config()
    existing = {s["url"] for s in repo.get_active_sources()}
    added = 0
    for src in config_sources:
        if src["url"] not in existing:
            repo.add_source(
                name=src["name"],
                source_type=src["type"],
                url=src["url"],
                target_sections=src.get("target_sections", ""),
            )
            added += 1
    return added


def fetch_all_sources(repo: Repository) -> dict[str, int]:
    """Fetch content from all active sources. Returns {source_name: items_added}."""
    sources = repo.get_active_sources()
    results: dict[str, int] = {}

    for src in sources:
        name = src["name"]
        try:
            if src["source_type"] == "rss":
                items = _fetch_rss_source(repo, src)
            elif src["source_type"] == "scrape":
                items = _fetch_scrape_source(repo, src)
            else:
                items = 0
            results[name] = items
            repo.update_source_fetched(src["id"])
        except Exception as exc:
            console.print(f"  [red]Error fetching {name}:[/red] {exc}")
            results[name] = 0

    return results


def _fetch_rss_source(repo: Repository, source: dict) -> int:
    """Fetch items from an RSS source."""
    feed_items = parse_feed(source["url"])
    added = 0
    for item in feed_items:
        if item.url and not repo.content_url_exists(item.url):
            repo.add_raw_content(
                source_id=source["id"],
                title=item.title,
                url=item.url,
                author=item.author,
                summary=item.summary,
                published_at=item.published_at,
                matched_sections=source.get("target_sections", ""),
            )
            added += 1
    return added


def _fetch_scrape_source(repo: Repository, source: dict) -> int:
    """Fetch items from a scrape source."""
    articles = scrape_articles(source["url"])
    added = 0
    for article in articles:
        if article.url and not repo.content_url_exists(article.url):
            repo.add_raw_content(
                source_id=source["id"],
                title=article.title,
                url=article.url,
                author=article.author,
                summary=article.summary,
                full_text=article.full_text,
                matched_sections=source.get("target_sections", ""),
            )
            added += 1
    return added
