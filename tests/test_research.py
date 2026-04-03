"""Tests for research and content discovery."""
import pytest


def _make_source(repo):
    """Helper to create a content source for FK satisfaction."""
    return repo.add_source("Test Source", "rss", "https://example.com/feed")


def test_add_raw_content(repo):
    """Test adding raw content to repository."""
    source_id = _make_source(repo)
    content_id = repo.add_raw_content(
        source_id=source_id,
        title="Test Article",
        url="https://example.com/test",
        author="Test Author",
        summary="A test article summary.",
    )
    assert content_id > 0


def test_get_unused_content(repo):
    """Test fetching unused content."""
    source_id = _make_source(repo)
    repo.add_raw_content(source_id=source_id, title="Unused Article", url="https://example.com/unused", summary="Summary")
    content = repo.get_unused_content(limit=10)
    assert len(content) >= 1
    assert any(c["title"] == "Unused Article" for c in content)


def test_content_url_exists(repo):
    """Test URL deduplication check."""
    source_id = _make_source(repo)
    url = "https://example.com/dedup-test"
    repo.add_raw_content(source_id=source_id, title="Dedup Test", url=url)
    assert repo.content_url_exists(url) is True
    assert repo.content_url_exists("https://example.com/nonexistent") is False


def test_mark_content_used(repo):
    """Test marking content as used."""
    source_id = _make_source(repo)
    content_id = repo.add_raw_content(source_id=source_id, title="To Use", url="https://example.com/use-me")
    repo.mark_content_used(content_id)
    # After marking, it shouldn't appear in unused content
    unused = repo.get_unused_content(limit=100)
    assert not any(c["id"] == content_id for c in unused)
