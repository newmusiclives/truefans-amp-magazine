"""Tests for scheduled send and edition filtering."""
import pytest


def test_get_subscribers_for_edition_empty(repo):
    """Test edition filtering returns empty when no subscribers."""
    result = repo.get_subscribers_for_edition("fan")
    assert isinstance(result, list)
    assert len(result) == 0


def test_get_subscribers_for_edition_with_data(repo):
    """Test edition filtering returns subscribers for the correct edition."""
    # Add a subscriber via subscribe_to_editions (returns subscriber id)
    sub_id = repo.subscribe_to_editions("test@example.com", ["fan"], source_channel="test")
    result = repo.get_subscribers_for_edition("fan")
    assert len(result) >= 1
    assert any(r["email"] == "test@example.com" for r in result)
