"""Web scraper for blog/article content."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from weeklyamp.utils.http import fetch_url
from weeklyamp.utils.text import clean_html, truncate


@dataclass
class ScrapedArticle:
    title: str
    url: str
    author: str
    summary: str
    full_text: str
    published_date: str = ""  # ISO date string if found


def scrape_articles(base_url: str, max_articles: int = 10) -> list[ScrapedArticle]:
    """Scrape article links from a site's homepage/blog page."""
    try:
        resp = fetch_url(base_url)
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    articles: list[ScrapedArticle] = []

    # Find article links — common patterns
    seen_urls: set[str] = set()
    for tag in soup.select("article a[href], .post a[href], h2 a[href], h3 a[href]"):
        href = tag.get("href", "")
        if not href or href.startswith("#"):
            continue
        url = urljoin(base_url, href)
        if url in seen_urls:
            continue
        seen_urls.add(url)

        title = tag.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        articles.append(ScrapedArticle(
            title=title,
            url=url,
            author="",
            summary="",
            full_text="",
        ))

        if len(articles) >= max_articles:
            break

    return articles


def scrape_article_content(url: str) -> Optional[ScrapedArticle]:
    """Fetch and extract content from a single article page."""
    try:
        resp = fetch_url(url)
    except Exception:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Title
    title = ""
    title_tag = soup.find("h1")
    if title_tag:
        title = title_tag.get_text(strip=True)
    elif soup.title:
        title = soup.title.get_text(strip=True)

    # Author
    author = ""
    author_tag = soup.find(class_=lambda c: c and "author" in c.lower()) if soup else None
    if author_tag:
        author = author_tag.get_text(strip=True)

    # Published date — check meta tags and time elements
    published_date = ""
    for meta_name in ("article:published_time", "datePublished", "date", "DC.date"):
        meta = soup.find("meta", attrs={"property": meta_name}) or soup.find("meta", attrs={"name": meta_name})
        if meta and meta.get("content"):
            published_date = meta["content"][:10]  # YYYY-MM-DD
            break
    if not published_date:
        time_tag = soup.find("time", attrs={"datetime": True})
        if time_tag:
            published_date = time_tag["datetime"][:10]

    # Main content
    content_tag = (
        soup.find("article")
        or soup.find(class_=lambda c: c and "content" in c.lower())
        or soup.find(class_=lambda c: c and "post" in c.lower())
    )

    full_text = ""
    if content_tag:
        # Get paragraphs
        paragraphs = content_tag.find_all("p")
        full_text = "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

    summary = truncate(full_text, 500) if full_text else ""

    return ScrapedArticle(
        title=title,
        url=url,
        author=author,
        summary=summary,
        full_text=full_text[:5000],
        published_date=published_date,
    )
