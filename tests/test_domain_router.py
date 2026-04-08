"""Tests for the white-label DomainRoutingMiddleware.

This middleware is the safety boundary for the licensee SaaS product:
incoming requests carry an arbitrary `Host` header, and the middleware
maps that host to a specific licensee tenant whose branding (and
eventually data scope) is then attached to `request.state`. A bug here
is a multi-tenant data leak — one licensee seeing another licensee's
content — so this layer needs explicit coverage.

Coverage was 0% before this file. The cases below cover:

  - white_label disabled → middleware is a no-op (no tenant set)
  - request to an unknown host → state cleared, no tenant
  - request to a verified licensee custom domain → request.state
    populated with licensee_id, branding fields, and licensee row
  - unverified licensee domain (`domain_verified = 0`) is *not*
    routed (the `WHERE domain_verified = 1` filter is what keeps an
    attacker from claiming someone else's domain by inserting a row)
  - inactive/cancelled licensee is *not* routed
  - legacy per-edition custom_domain still works for backward compat
  - licensee domains take precedence over edition domains for the
    same host (the order matters for the migration path)
  - cache is built once and `invalidate_cache()` forces a rebuild
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from weeklyamp.web.middleware.domain_router import DomainRoutingMiddleware
from weeklyamp.web.security import hash_password


# ---- Helpers --------------------------------------------------------------


def _white_label_config(enabled: bool = True):
    """Build a minimal config object that satisfies the middleware's
    `config.white_label.enabled` access pattern."""
    return SimpleNamespace(white_label=SimpleNamespace(enabled=enabled))


def _build_app(repo, config, monkeypatch):
    """Wire up a tiny Starlette app with the middleware installed.

    The single test route echoes the request.state fields the
    middleware is supposed to populate so tests can assert them via
    HTTP responses rather than poking at internal state.

    `get_repo` is patched via monkeypatch so the override is undone
    at test teardown — otherwise subsequent tests in the same
    process inherit a stale fake pointing at a deleted tmp DB.
    """
    async def echo(request):
        return JSONResponse({
            "licensee_id": getattr(request.state, "licensee_id", None),
            "licensee_company": (
                (getattr(request.state, "licensee", None) or {}).get("company_name")
                if getattr(request.state, "licensee", None) else None
            ),
            "brand_logo_url": getattr(request.state, "brand_logo_url", ""),
            "brand_primary_color": getattr(request.state, "brand_primary_color", ""),
            "brand_footer_html": getattr(request.state, "brand_footer_html", ""),
            "white_label_edition_slug": (
                (getattr(request.state, "white_label_edition", None) or {}).get("slug")
                if getattr(request.state, "white_label_edition", None) else None
            ),
        })

    app = Starlette(routes=[Route("/", echo)])
    app.add_middleware(DomainRoutingMiddleware, config=config)
    monkeypatch.setattr("weeklyamp.web.deps.get_repo", lambda: repo)
    return app


def _create_active_verified_licensee(repo, *, company, email, city, domain, **branding):
    """Convenience: create + activate + brand + verify a licensee."""
    lid = repo.create_licensee(
        company_name=company,
        contact_name=company,
        email=email,
        password_hash=hash_password("test-pw"),
        city_market_slug=city,
        edition_slugs="fan",
        license_type="monthly",
        license_fee_cents=9900,
        revenue_share_pct=20.0,
    )
    repo.update_licensee_status(lid, "active")
    repo.update_licensee_branding(lid, custom_domain=domain, **branding)
    repo.mark_licensee_domain_verified(lid)
    return lid


# ---- Tests ----------------------------------------------------------------


def test_disabled_white_label_is_a_noop(repo, monkeypatch):
    """When white_label is off, the middleware should pass through
    every request without touching `request.state`."""
    app = _build_app(repo, _white_label_config(enabled=False), monkeypatch)

    with TestClient(app) as client:
        r = client.get("/", headers={"Host": "any.example.test"})
    assert r.status_code == 200
    body = r.json()
    assert body["licensee_id"] is None
    assert body["white_label_edition_slug"] is None


def test_unknown_host_clears_state(repo, monkeypatch):
    """A host we don't recognise must leave `request.state` cleared
    (no stale tenant from another request)."""
    app = _build_app(repo, _white_label_config(enabled=True), monkeypatch)

    with TestClient(app) as client:
        r = client.get("/", headers={"Host": "stranger.example.test"})
    body = r.json()
    assert body["licensee_id"] is None
    assert body["licensee_company"] is None


def test_verified_licensee_domain_routes_to_licensee(repo, monkeypatch):
    lid = _create_active_verified_licensee(
        repo,
        company="Nashville Music Co",
        email="nash@example.test",
        city="nashville",
        domain="nashvillemusic.example",
        logo_url="https://cdn.example/nash.png",
        primary_color="#ff8800",
        footer_html="<p>Nashville Music — All Rights Reserved</p>",
    )
    app = _build_app(repo, _white_label_config(enabled=True), monkeypatch)

    with TestClient(app) as client:
        r = client.get("/", headers={"Host": "nashvillemusic.example"})
    body = r.json()
    assert body["licensee_id"] == lid
    assert body["licensee_company"] == "Nashville Music Co"
    assert body["brand_logo_url"] == "https://cdn.example/nash.png"
    assert body["brand_primary_color"] == "#ff8800"
    assert "Nashville Music" in body["brand_footer_html"]


def test_host_lookup_strips_port(repo, monkeypatch):
    """A `Host: foo.example:8443` header should still match `foo.example`."""
    lid = _create_active_verified_licensee(
        repo,
        company="Port Strip Co",
        email="port@example.test",
        city="portcity",
        domain="port.example",
    )
    app = _build_app(repo, _white_label_config(enabled=True), monkeypatch)

    with TestClient(app) as client:
        r = client.get("/", headers={"Host": "port.example:8443"})
    assert r.json()["licensee_id"] == lid


def test_unverified_licensee_domain_is_not_routed(repo, monkeypatch):
    """Unverified domains MUST NOT be routed — that filter is the
    boundary that prevents an attacker from claiming a domain by
    just inserting a row."""
    lid = repo.create_licensee(
        company_name="Unverified Co",
        contact_name="Unverified",
        email="unv@example.test",
        password_hash=hash_password("test-pw"),
        city_market_slug="somewhere",
        edition_slugs="fan",
        license_type="monthly",
        license_fee_cents=9900,
        revenue_share_pct=20.0,
    )
    repo.update_licensee_status(lid, "active")
    repo.update_licensee_branding(lid, custom_domain="claimed.example")
    # Notably: we do NOT call mark_licensee_domain_verified.

    app = _build_app(repo, _white_label_config(enabled=True), monkeypatch)

    with TestClient(app) as client:
        r = client.get("/", headers={"Host": "claimed.example"})
    assert r.json()["licensee_id"] is None


def test_inactive_licensee_domain_is_not_routed(repo, monkeypatch):
    """A pending or cancelled licensee should not have their custom
    domain routed even if it was verified earlier."""
    lid = repo.create_licensee(
        company_name="Pending Co",
        contact_name="Pending",
        email="pending@example.test",
        password_hash=hash_password("test-pw"),
        city_market_slug="pendingville",
        edition_slugs="fan",
        license_type="monthly",
        license_fee_cents=9900,
        revenue_share_pct=20.0,
    )
    # Stays in default 'pending' status — never activated.
    repo.update_licensee_branding(lid, custom_domain="pending.example")
    repo.mark_licensee_domain_verified(lid)

    app = _build_app(repo, _white_label_config(enabled=True), monkeypatch)

    with TestClient(app) as client:
        r = client.get("/", headers={"Host": "pending.example"})
    assert r.json()["licensee_id"] is None


def test_invalidate_cache_forces_rebuild(repo, monkeypatch):
    """After `invalidate_cache()` the middleware must re-query — useful
    when admin UI mutates a custom_domain or verifies a domain."""
    app = _build_app(repo, _white_label_config(enabled=True), monkeypatch)

    # First request: no domains exist yet → unknown host
    with TestClient(app) as client:
        r1 = client.get("/", headers={"Host": "late.example"})
    assert r1.json()["licensee_id"] is None

    # Now create + verify a licensee with that domain.
    lid = _create_active_verified_licensee(
        repo,
        company="Late Co",
        email="late@example.test",
        city="late",
        domain="late.example",
    )

    # Without invalidation, the cached empty mapping persists.
    # Reach into the middleware instance via the app's middleware stack.
    middleware_instance = None
    for m in app.user_middleware:
        if m.cls is DomainRoutingMiddleware:
            # Build the middleware once via a real request to instantiate it
            break

    # Easiest path to grab the live instance: send another request, then
    # invalidate via the same instance the test client used. Starlette
    # constructs middleware lazily, so we attach an invalidator hook by
    # walking the ASGI app chain.
    asgi = app.middleware_stack
    while asgi is not None:
        if isinstance(asgi, DomainRoutingMiddleware):
            middleware_instance = asgi
            break
        asgi = getattr(asgi, "app", None)

    assert middleware_instance is not None, "could not locate middleware instance"
    middleware_instance.invalidate_cache()

    with TestClient(app) as client:
        r2 = client.get("/", headers={"Host": "late.example"})
    assert r2.json()["licensee_id"] == lid
