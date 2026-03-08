"""Tests for web routes using Starlette TestClient."""

from __future__ import annotations

import pytest


# ---- Landing page ----

def test_landing_page_returns_200(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_landing_page_contains_html(client):
    resp = client.get("/")
    assert "html" in resp.text.lower()


# ---- Health check ----

def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_returns_status_ok(client):
    resp = client.get("/health")
    data = resp.json()
    assert data["status"] == "ok"
    assert data["db"] == "connected"


# ---- Subscribe ----

def test_subscribe_page_returns_200(client):
    resp = client.get("/subscribe")
    assert resp.status_code == 200


def test_subscribe_post_valid_data_returns_redirect(client):
    resp = client.post(
        "/subscribe",
        data={
            "email": "test@example.com",
            "first_name": "Test",
            "editions": "fan",
        },
        follow_redirects=False,
    )
    # Should redirect (303) to /subscribe/confirm
    assert resp.status_code == 303
    assert "/subscribe/confirm" in resp.headers.get("location", "")


def test_subscribe_post_invalid_email_returns_error(client):
    resp = client.post(
        "/subscribe",
        data={
            "email": "not-an-email",
            "editions": "fan",
        },
    )
    assert resp.status_code == 200
    assert "valid email" in resp.text.lower()


def test_subscribe_post_no_editions_returns_error(client):
    resp = client.post(
        "/subscribe",
        data={
            "email": "good@example.com",
            # no editions selected
        },
    )
    assert resp.status_code == 200
    assert "select at least one" in resp.text.lower()


# ---- Submit ----

def test_submit_page_returns_200(client):
    resp = client.get("/submit")
    assert resp.status_code == 200


def test_submit_post_valid_data_returns_success(client):
    resp = client.post(
        "/submit",
        data={
            "artist_name": "Test Artist",
            "artist_email": "artist@example.com",
            "submission_type": "new_release",
            "title": "My Song",
            "description": "A great song",
        },
    )
    assert resp.status_code == 200
    assert "received" in resp.text.lower() or "thank" in resp.text.lower()


# ---- API endpoint ----

def test_api_submissions_without_key_returns_error(client, monkeypatch):
    # Set an API key so the endpoint expects auth
    monkeypatch.setenv("TRUEFANS_SUBMISSIONS_API_KEY", "secret-key-123")
    resp = client.post(
        "/api/v1/submissions",
        json={"artist_name": "Test"},
    )
    assert resp.status_code in (401, 403)


def test_api_submissions_with_wrong_key_returns_401(client, monkeypatch):
    monkeypatch.setenv("TRUEFANS_SUBMISSIONS_API_KEY", "secret-key-123")
    resp = client.post(
        "/api/v1/submissions",
        json={"artist_name": "Test"},
        headers={"X-TrueFans-API-Key": "wrong-key"},
    )
    assert resp.status_code == 401


# ---- Rate limiting on subscribe ----

def test_subscribe_rate_limiting_returns_429(client):
    """After exceeding subscribe rate limit, should get 429."""
    # Clear any existing rate limit state for this route
    import weeklyamp.web.routes.subscribe as sub_mod
    with sub_mod._subscribe_lock:
        sub_mod._subscribe_attempts.clear()

    # Fill up the rate limit
    max_attempts, _ = sub_mod._get_rate_config()
    for _ in range(max_attempts):
        client.post(
            "/subscribe",
            data={
                "email": "ratelimit@example.com",
                "first_name": "RL",
                "editions": "fan",
            },
            follow_redirects=False,
        )

    # Next request should be rate-limited
    resp = client.post(
        "/subscribe",
        data={
            "email": "ratelimit2@example.com",
            "first_name": "RL",
            "editions": "fan",
        },
    )
    assert resp.status_code == 429


# ---- Dashboard auth redirect ----

def test_dashboard_redirects_to_login_when_auth_enabled(client, monkeypatch):
    """When auth is enabled, /dashboard should redirect to /login."""
    import weeklyamp.web.security as sec
    monkeypatch.setenv("WEEKLYAMP_ADMIN_HASH", sec.hash_password("test-password"))
    sec._cached_admin_hash = None

    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("location", "")

    sec._cached_admin_hash = None
