"""Research guest contact websites for blog articles suitable for newsletter use."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from weeklyamp.db.repository import Repository
from weeklyamp.research.scraper import ScrapedArticle, scrape_article_content
from weeklyamp.utils.http import fetch_url
from weeklyamp.utils.text import truncate

log = logging.getLogger(__name__)

MAX_ARTICLES_PER_CONTACT = 2
MAX_ARTICLE_AGE_DAYS = 365  # 1 year — much music content is evergreen
MIN_ARTICLE_WORDS = 150  # skip thin content


@dataclass
class ResearchResult:
    contact_id: int
    contact_name: str
    articles_found: int
    articles_added: int


# URL path segments that indicate non-article pages
_SKIP_PATHS = {
    "about", "contact", "store", "shop", "cart", "checkout", "login",
    "signup", "register", "privacy", "terms", "legal", "faq", "help",
    "services", "pricing", "team", "careers", "jobs", "press",
    "subscribe", "newsletter", "category", "tag", "author", "page",
    "product", "booking", "calendar", "events", "gallery", "portfolio",
}

# URL path segments that suggest blog/article content
_ARTICLE_SIGNALS = {
    "blog", "post", "article", "news", "insights", "writing",
    "column", "opinion", "stories", "journal", "digest", "weekly",
    "podcast", "episode", "review", "guide", "tips", "lesson",
}


def _find_blog_url(base_url: str, soup: BeautifulSoup) -> Optional[str]:
    """Try to find the blog/articles index page from a site's homepage."""
    # Check common blog link patterns in navigation
    for a in soup.select("nav a[href], header a[href], .menu a[href]"):
        href = a.get("href", "").lower()
        text = a.get_text(strip=True).lower()
        if any(kw in text for kw in ("blog", "articles", "posts", "writing", "insights", "news")):
            return urljoin(base_url, a["href"])
        if any(kw in href for kw in ("/blog", "/articles", "/posts", "/news", "/insights")):
            return urljoin(base_url, a["href"])

    # Try common blog paths directly
    parsed = urlparse(base_url)
    for path in ("/blog", "/blog/", "/articles", "/posts", "/news", "/wordpress", "/journal"):
        try:
            test_url = f"{parsed.scheme}://{parsed.netloc}{path}"
            resp = fetch_url(test_url)
            if resp.status_code == 200:
                return test_url
        except Exception:
            continue

    return None


def _is_article_url(url: str, base_domain: str) -> bool:
    """Filter URLs to only likely blog/article pages."""
    parsed = urlparse(url)

    # Must be on the same domain (or subdomain)
    if base_domain not in parsed.netloc:
        return False

    path = parsed.path.lower().rstrip("/")
    segments = [s for s in path.split("/") if s]

    # Skip known non-article paths
    if any(seg in _SKIP_PATHS for seg in segments):
        return False

    # Skip file downloads, images, etc.
    if re.search(r'\.(pdf|jpg|png|gif|mp3|mp4|zip|doc)$', path, re.I):
        return False

    # Skip very short paths (likely section indexes, not articles)
    if len(segments) < 1:
        return False

    # Skip fragment-only or query-only URLs
    if not path or path == "/":
        return False

    return True


def _is_quality_article(detail: ScrapedArticle) -> bool:
    """Check if scraped content is substantial enough for newsletter use."""
    if not detail.full_text:
        return False

    word_count = len(detail.full_text.split())
    if word_count < MIN_ARTICLE_WORDS:
        return False

    # Skip if title suggests non-article page
    title_lower = (detail.title or "").lower()
    skip_titles = ["contact", "about", "store", "services", "home", "subscribe",
                   "sign up", "log in", "cart", "checkout", "privacy policy"]
    if any(t in title_lower for t in skip_titles):
        return False

    return True


def _format_for_newsletter(detail: ScrapedArticle, contact_name: str) -> tuple[str, str]:
    """Format scraped content into clean newsletter-ready text.

    Returns (content_full, content_summary).
    """
    # Clean up the full text — proper paragraph breaks
    paragraphs = [p.strip() for p in detail.full_text.split("\n\n") if p.strip()]
    full_text = "\n\n".join(paragraphs)

    # Create a newsletter-ready summary: opening context + key excerpt
    summary_parts = []

    # Attribution header
    summary_parts.append(f"**{detail.title}**")
    summary_parts.append(f"*By {contact_name}*")
    summary_parts.append("")

    # Take the most substantive opening paragraphs (skip very short ones)
    excerpt_words = 0
    for p in paragraphs:
        if excerpt_words > 250:
            break
        if len(p.split()) < 5:
            continue
        summary_parts.append(p)
        excerpt_words += len(p.split())

    if detail.url:
        summary_parts.append("")
        summary_parts.append(f"[Read the full article]({detail.url})")

    summary = "\n\n".join(summary_parts)

    return full_text, summary


def _scrape_blog_articles(base_url: str) -> list[ScrapedArticle]:
    """Find and scrape actual blog/article links from a website.

    Smarter than the generic scrape_articles — finds the blog page first,
    then filters for real article URLs only.
    """
    try:
        resp = fetch_url(base_url)
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    parsed = urlparse(base_url)
    base_domain = parsed.netloc.replace("www.", "")

    # Try to find a dedicated blog page
    blog_url = _find_blog_url(base_url, soup)
    if blog_url and blog_url != base_url:
        try:
            resp = fetch_url(blog_url)
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception:
            pass  # Fall back to homepage

    # Collect article links — prioritize <article> tags, then headings
    seen_urls: set[str] = set()
    candidates: list[ScrapedArticle] = []

    # Priority 1: links inside <article> elements
    for article_tag in soup.select("article"):
        for a in article_tag.select("a[href]"):
            href = a.get("href", "")
            if not href or href.startswith("#"):
                continue
            url = urljoin(blog_url or base_url, href)
            if url in seen_urls:
                continue
            seen_urls.add(url)

            title = a.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            if _is_article_url(url, base_domain):
                candidates.append(ScrapedArticle(
                    title=title, url=url, author="", summary="", full_text="",
                ))

    # Priority 2: h2/h3 links and .entry-title (common blog listing patterns)
    if len(candidates) < 10:
        for tag in soup.select("h2 a[href], h3 a[href], .entry-title a[href]"):
            href = tag.get("href", "")
            if not href or href.startswith("#"):
                continue
            url = urljoin(blog_url or base_url, href)
            if url in seen_urls:
                continue
            seen_urls.add(url)

            title = tag.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            if _is_article_url(url, base_domain):
                candidates.append(ScrapedArticle(
                    title=title, url=url, author="", summary="", full_text="",
                ))

    return candidates[:10]


def _is_recent(published_date: str) -> bool:
    """Check if an article's publish date is within the last 3 months."""
    if not published_date:
        return True  # Benefit of the doubt if no date found
    try:
        pub = datetime.strptime(published_date[:10], "%Y-%m-%d")
        cutoff = datetime.now() - timedelta(days=MAX_ARTICLE_AGE_DAYS)
        return pub >= cutoff
    except (ValueError, TypeError):
        return True


def research_contact_website(repo: Repository, contact_id: int) -> ResearchResult:
    """Scrape a single contact's website for blog articles and store them."""
    contact = repo.get_guest_contact(contact_id)
    if not contact:
        raise ValueError(f"Contact {contact_id} not found")

    website = contact.get("website", "").strip()
    if not website:
        return ResearchResult(contact_id, contact["name"], 0, 0)

    log.info("Researching website for %s: %s", contact["name"], website)
    candidates = _scrape_blog_articles(website)

    added = 0
    for article in candidates:
        if added >= MAX_ARTICLES_PER_CONTACT:
            break

        if repo.guest_article_url_exists(article.url):
            continue

        # Fetch full content
        detail = scrape_article_content(article.url)
        if not detail:
            continue

        # Quality gate — must be a real article with substance
        if not _is_quality_article(detail):
            log.debug("Skipping low-quality page: %s", detail.title)
            continue

        # Recency gate
        if not _is_recent(detail.published_date):
            log.debug("Skipping old article (%s): %s", detail.published_date, detail.title)
            continue

        # Format for newsletter use
        full_text, summary = _format_for_newsletter(detail, contact["name"])

        repo.create_guest_article(
            contact_id=contact_id,
            title=detail.title or article.title,
            author_name=contact["name"],
            original_url=article.url,
            content_full=full_text,
            content_summary=summary,
            permission_state="received",
            display_mode="summary",
        )
        added += 1

    log.info("Found %d candidates, added %d quality articles for %s",
             len(candidates), added, contact["name"])
    return ResearchResult(contact_id, contact["name"], len(candidates), added)


def research_all_contacts(repo: Repository) -> list[ResearchResult]:
    """Research websites for all contacts that have one."""
    contacts = repo.get_guest_contacts()
    results = []
    for contact in contacts:
        if not contact.get("website", "").strip():
            continue
        try:
            result = research_contact_website(repo, contact["id"])
            results.append(result)
        except Exception as e:
            log.error("Failed to research contact %s: %s", contact["name"], e)
    return results
