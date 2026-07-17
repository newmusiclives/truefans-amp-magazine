"""Tests for newsletter assembly."""
import pytest
from unittest.mock import patch


def test_assemble_newsletter_basic(repo):
    """Test basic newsletter assembly with approved drafts."""
    # Create an issue
    issue_id = repo.create_issue_with_schedule(issue_number=100, week_id="2026-W14", send_day="monday", edition_slug="fan")

    # Create and approve a draft
    draft_id = repo.create_draft(issue_id, "backstage_pass", "Test content for backstage pass.", ai_model="test")
    repo.update_draft_status(draft_id, "approved")

    # Mock AI generation to avoid actual API calls
    with patch("weeklyamp.content.assembly._generate_welcome_intro", return_value="Welcome!"):
        with patch("weeklyamp.content.assembly._generate_ps_closing", return_value="Thanks for reading!"):
            from weeklyamp.content.assembly import assemble_newsletter
            from weeklyamp.core.config import load_config
            config = load_config()
            html, plain = assemble_newsletter(repo, issue_id, config)

    assert "backstage_pass" in plain.lower() or "BACKSTAGE" in plain


def test_get_subscriber_segments(repo):
    """Test subscriber segmentation function."""
    from weeklyamp.content.assembly import get_subscriber_segments
    segments = get_subscriber_segments(repo)
    assert isinstance(segments, dict)


def _assemble_with_promo(repo, config, edition_slug="fan"):
    """Helper: assemble an edition with AI stubbed, return (html, plain)."""
    issue_id = repo.create_issue_with_schedule(
        issue_number=200, week_id="2026-W20", send_day="monday", edition_slug=edition_slug
    )
    draft_id = repo.create_draft(issue_id, "backstage_pass", "Body copy.", ai_model="test")
    repo.update_draft_status(draft_id, "approved")
    with patch("weeklyamp.content.assembly._generate_welcome_intro", return_value="Welcome!"):
        with patch("weeklyamp.content.assembly._generate_ps_closing", return_value="Thanks!"):
            from weeklyamp.content.assembly import assemble_newsletter
            return assemble_newsletter(repo, issue_id, config)


def test_promo_block_disabled_by_default(repo):
    """The promo block must not render unless explicitly enabled."""
    from weeklyamp.core.config import load_config
    config = load_config()
    assert config.promo.enabled is False
    html, _ = _assemble_with_promo(repo, config)
    assert "newmusiclives.beehiiv.com" not in html


def test_promo_block_routes_fan_to_amp_with_utm(repo):
    """Fan edition routes to AMP with UTM attribution params (unwrapped)."""
    from weeklyamp.core.config import load_config
    config = load_config()
    config.promo.enabled = True
    config.promo.track_clicks = False  # test the raw destination + UTM
    html, plain = _assemble_with_promo(repo, config, edition_slug="fan")
    assert "newmusiclives.beehiiv.com/subscribe" in html
    assert "utm_source=dispatch" in html
    assert "utm_campaign=fan" in html
    assert "utm_content=amp" in html
    assert "newmusiclives.beehiiv.com" in plain


def test_promo_block_artist_falls_back_to_edge_until_rise_url_set(repo):
    """Artist routes to RISE, but with no RISE URL yet it falls back to the
    EDGE waitlist rather than rendering nothing."""
    from weeklyamp.core.config import load_config
    config = load_config()
    config.promo.enabled = True
    config.promo.track_clicks = False
    assert config.promo.targets["rise"].url == ""  # RISE not live yet
    html, _ = _assemble_with_promo(repo, config, edition_slug="artist")
    assert "truefans-playbook.netlify.app" in html
    assert "utm_content=edge" in html


def test_promo_block_click_wrapping(repo):
    """With track_clicks on, the CTA is wrapped in /t/promo and the encoded
    destination still carries the UTM'd target URL."""
    import base64
    from urllib.parse import parse_qs, urlparse
    from weeklyamp.core.config import load_config
    config = load_config()
    config.promo.enabled = True
    config.promo.track_clicks = True  # default, but be explicit
    html, _ = _assemble_with_promo(repo, config, edition_slug="fan")
    assert "/t/promo?" in html
    assert "t=amp" in html
    # The encoded url= param decodes to the UTM-tagged Beehiiv destination.
    href = [seg for seg in html.split('"') if "/t/promo?" in seg][0]
    encoded = parse_qs(urlparse(href).query)["url"][0]
    dest = base64.urlsafe_b64decode(encoded.encode()).decode()
    assert "newmusiclives.beehiiv.com/subscribe" in dest
    assert "utm_content=amp" in dest


def test_promo_block_resolution_unit():
    """resolve_promo_target picks routed target, falls back to default."""
    from weeklyamp.core.models import PromoConfig
    from weeklyamp.content.promo import resolve_promo_target, build_promo_block
    cfg = PromoConfig(enabled=True)
    key, _ = resolve_promo_target(cfg, "industry")
    assert key == "amp"
    # Disabled -> nothing
    assert build_promo_block(PromoConfig(enabled=False), "fan") is None


def test_promo_admin_override_changes_effective_config(repo):
    """A stored admin_settings override changes the effective promo config,
    and the env kill-switch force-enables regardless of the stored value."""
    import json
    from weeklyamp.core.models import PromoConfig
    from weeklyamp.content.promo import effective_promo_config, PROMO_SETTINGS_KEY
    base = PromoConfig(enabled=False)
    repo.set_admin_setting(PROMO_SETTINGS_KEY, json.dumps({
        "enabled": True,
        "targets": {"amp": {"headline": "Custom AMP", "url": "https://amp.example"}},
        "routing": {"fan": "amp"},
    }))
    eff = effective_promo_config(repo, base)
    assert eff.enabled is True
    assert eff.targets["amp"].headline == "Custom AMP"
    # Stored says disabled, but env forces on.
    repo.set_admin_setting(PROMO_SETTINGS_KEY, json.dumps({"enabled": False}))
    eff2 = effective_promo_config(repo, base, env_forced=True)
    assert eff2.enabled is True


def test_promo_events_recorded_and_aggregated(repo):
    """record_promo_event writes rows; get_promo_performance aggregates."""
    repo.record_promo_event(target="amp", edition_slug="fan", event_type="click")
    repo.record_promo_event(target="amp", edition_slug="fan", event_type="click")
    repo.record_promo_event(target="edge", edition_slug="artist", event_type="click")
    perf = {(r["target"], r["edition_slug"]): r["clicks"] for r in repo.get_promo_performance()}
    assert perf[("amp", "fan")] == 2
    assert perf[("edge", "artist")] == 1
