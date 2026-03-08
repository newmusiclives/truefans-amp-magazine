"""Tests for authentication, password hashing, rate limiting, and sessions."""

from __future__ import annotations

import time

import pytest

from weeklyamp.web.security import (
    _clear_attempts,
    _get_login_rate_config,
    _is_public,
    _is_rate_limited,
    _login_attempts,
    _login_lock,
    _record_attempt,
    create_session,
    hash_password,
    is_authenticated,
    verify_password,
)

# Get rate limit config for tests
_MAX_ATTEMPTS, _WINDOW_SECONDS = _get_login_rate_config()


# ---- Password hashing ----

def test_hash_password_returns_bcrypt_string():
    hashed = hash_password("hunter2")
    assert hashed.startswith("$2")
    assert len(hashed) == 60


def test_verify_password_correct():
    hashed = hash_password("correct-password")
    assert verify_password("correct-password", hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("correct-password")
    assert verify_password("wrong-password", hashed) is False


def test_verify_password_invalid_hash():
    assert verify_password("anything", "not-a-valid-hash") is False


def test_verify_password_empty_password():
    hashed = hash_password("real")
    assert verify_password("", hashed) is False


# ---- Rate limiting ----

def _clear_rate_state():
    """Helper to reset global rate-limiting state between tests."""
    with _login_lock:
        _login_attempts.clear()


def test_rate_limiting_allows_under_limit():
    _clear_rate_state()
    ip = "10.0.0.1"
    for _ in range(_MAX_ATTEMPTS - 1):
        _record_attempt(ip)
    assert _is_rate_limited(ip) is False


def test_rate_limiting_blocks_at_limit():
    _clear_rate_state()
    ip = "10.0.0.2"
    for _ in range(_MAX_ATTEMPTS):
        _record_attempt(ip)
    assert _is_rate_limited(ip) is True


def test_clear_attempts_resets_limit():
    _clear_rate_state()
    ip = "10.0.0.3"
    for _ in range(_MAX_ATTEMPTS):
        _record_attempt(ip)
    assert _is_rate_limited(ip) is True
    _clear_attempts(ip)
    assert _is_rate_limited(ip) is False


def test_rate_limiting_independent_per_ip():
    _clear_rate_state()
    ip1 = "10.0.0.10"
    ip2 = "10.0.0.11"
    for _ in range(_MAX_ATTEMPTS):
        _record_attempt(ip1)
    assert _is_rate_limited(ip1) is True
    assert _is_rate_limited(ip2) is False


# ---- is_authenticated ----

def test_is_authenticated_returns_true_when_no_password(monkeypatch):
    """When no admin hash/password is configured, auth is disabled."""
    import weeklyamp.web.security as sec
    monkeypatch.delenv("WEEKLYAMP_ADMIN_HASH", raising=False)
    monkeypatch.delenv("WEEKLYAMP_ADMIN_PASSWORD", raising=False)
    sec._cached_admin_hash = None

    # Build a minimal fake request
    from starlette.testclient import TestClient
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def endpoint(request: Request):
        result = is_authenticated(request)
        return JSONResponse({"auth": result})

    app = Starlette(routes=[Route("/check", endpoint)])
    client = TestClient(app)
    resp = client.get("/check")
    assert resp.json()["auth"] is True

    sec._cached_admin_hash = None


# ---- Session cookie ----

def test_create_session_sets_cookie():
    from starlette.responses import Response
    resp = Response("ok")
    create_session(resp, request=None)
    # The cookie should be set in the response headers
    cookie_header = resp.headers.get("set-cookie", "")
    assert "_session=" in cookie_header
    assert "httponly" in cookie_header.lower()


# ---- Public route detection ----

def test_is_public_exact_root():
    assert _is_public("/") is True


def test_is_public_health():
    assert _is_public("/health") is True


def test_is_public_login():
    assert _is_public("/login") is True


def test_is_public_subscribe():
    assert _is_public("/subscribe") is True


def test_is_public_submit():
    assert _is_public("/submit") is True


def test_is_public_static():
    assert _is_public("/static/style.css") is True


def test_is_public_api():
    assert _is_public("/api/v1/submissions") is True


def test_is_not_public_dashboard():
    assert _is_public("/dashboard") is False


def test_is_not_public_drafts():
    assert _is_public("/drafts") is False


def test_is_not_public_review():
    assert _is_public("/review") is False


def test_is_not_public_sections():
    assert _is_public("/sections") is False
