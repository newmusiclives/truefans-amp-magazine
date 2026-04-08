"""Multi-tenant isolation + territory exclusivity tests for licensees.

These tests are the foundation of Goal B safety. The platform sells
city-edition licenses where each licensee runs their own newsletter on
shared infrastructure, so cross-licensee data leaks would be catastrophic.

The territory exclusivity tests guard against accidentally selling the
same city to two operators.
"""

from __future__ import annotations

import pytest

from weeklyamp.db.repository import Repository
from weeklyamp.web.security import hash_password


def _create(repo, *, company, email, city, editions, **kwargs):
    return repo.create_licensee(
        company_name=company,
        contact_name=company,
        email=email,
        password_hash=hash_password("test-pw"),
        city_market_slug=city,
        edition_slugs=editions,
        license_type="monthly",
        license_fee_cents=9900,
        revenue_share_pct=20.0,
        **kwargs,
    )


# ---- Territory exclusivity ----

def test_first_licensee_in_city_succeeds(repo):
    lid = _create(repo, company="Nashville Music", email="a@nash.test",
                  city="nashville", editions="fan,artist")
    assert lid > 0


def test_second_licensee_same_city_overlapping_editions_blocked(repo):
    _create(repo, company="Nashville Music", email="a@nash.test",
            city="nashville", editions="fan,artist")
    repo.update_licensee_status(repo.get_licensee_by_email("a@nash.test")["id"], "active")
    with pytest.raises(Repository.TerritoryConflictError):
        _create(repo, company="Nashville Sound", email="b@nash.test",
                city="nashville", editions="fan,industry")


def test_second_licensee_same_city_disjoint_editions_allowed(repo):
    _create(repo, company="Nashville Fan", email="a@nash.test",
            city="nashville", editions="fan")
    repo.update_licensee_status(repo.get_licensee_by_email("a@nash.test")["id"], "active")
    # Different editions in the same city — allowed
    lid = _create(repo, company="Nashville Industry", email="b@nash.test",
                  city="nashville", editions="industry")
    assert lid > 0


def test_second_licensee_different_city_allowed(repo):
    _create(repo, company="Nashville Music", email="a@nash.test",
            city="nashville", editions="fan,artist,industry")
    lid = _create(repo, company="Asheville Music", email="b@avl.test",
                  city="asheville", editions="fan,artist,industry")
    assert lid > 0


def test_overlap_override_allowed_when_admin_forces(repo):
    _create(repo, company="Nashville Music", email="a@nash.test",
            city="nashville", editions="fan")
    repo.update_licensee_status(repo.get_licensee_by_email("a@nash.test")["id"], "active")
    # Admin forces creation despite overlap
    lid = _create(repo, company="Nashville 2", email="b@nash.test",
                  city="nashville", editions="fan",
                  allow_territory_overlap=True)
    assert lid > 0


def test_cancelled_licensee_does_not_block_new_one(repo):
    lid_a = _create(repo, company="Nashville Music", email="a@nash.test",
                    city="nashville", editions="fan,artist")
    repo.update_licensee_status(lid_a, "cancelled")
    # Cancelled licensee should NOT count as a territory holder
    lid_b = _create(repo, company="Nashville Sound", email="b@nash.test",
                    city="nashville", editions="fan,artist")
    assert lid_b > 0


# ---- Cross-tenant isolation ----

def test_licensee_lookup_by_email_isolated(repo):
    _create(repo, company="A Co", email="a@a.test",
            city="city-a", editions="fan")
    _create(repo, company="B Co", email="b@b.test",
            city="city-b", editions="fan")

    a = repo.get_licensee_by_email("a@a.test")
    b = repo.get_licensee_by_email("b@b.test")
    assert a["company_name"] == "A Co"
    assert b["company_name"] == "B Co"
    assert a["id"] != b["id"]
    # Critical: looking up A's email never returns B's row
    assert repo.get_licensee_by_email("a@a.test")["id"] == a["id"]


def test_licensee_revenue_isolated_per_id(repo):
    lid_a = _create(repo, company="A Co", email="a@a.test",
                    city="city-a", editions="fan")
    lid_b = _create(repo, company="B Co", email="b@b.test",
                    city="city-b", editions="fan")
    repo.create_license_revenue(lid_a, "2026-04", sponsor_cents=10000)
    repo.create_license_revenue(lid_b, "2026-04", sponsor_cents=99999)

    rev_a = repo.get_license_revenue(lid_a)
    rev_b = repo.get_license_revenue(lid_b)
    assert len(rev_a) == 1
    assert len(rev_b) == 1
    # Sums must not bleed
    assert rev_a[0]["sponsor_revenue_cents"] == 10000
    assert rev_b[0]["sponsor_revenue_cents"] == 99999
    # Empty result for an unrelated id
    assert repo.get_license_revenue(99999) == []
