"""Tests for the background worker scheduler in weeklyamp.workers.scheduler.

Coverage of `workers/scheduler.py` was 9% before this file. The module
itself is mostly thin try/except wrappers around feature-flagged code,
so the highest-value tests are:

  1. start_scheduler is gated correctly by WEEKLYAMP_WORKERS_ENABLED
  2. When enabled, the expected jobs are registered
  3. stop_scheduler is safe to call when nothing is running
  4. Each job swallows exceptions (the scheduler must never crash on a
     bad job — better to log + continue than to take down all jobs)
  5. Each feature-flagged job is a no-op when its flag is off
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import weeklyamp.workers.scheduler as scheduler_mod


# ---- start_scheduler / stop_scheduler ----


def test_start_scheduler_returns_none_when_disabled(monkeypatch):
    monkeypatch.delenv("WEEKLYAMP_WORKERS_ENABLED", raising=False)
    assert scheduler_mod.start_scheduler() is None


def test_start_scheduler_returns_none_when_flag_false(monkeypatch):
    monkeypatch.setenv("WEEKLYAMP_WORKERS_ENABLED", "false")
    assert scheduler_mod.start_scheduler() is None


def test_start_scheduler_registers_expected_jobs(monkeypatch):
    monkeypatch.setenv("WEEKLYAMP_WORKERS_ENABLED", "true")

    fake_scheduler = MagicMock()
    fake_scheduler.get_jobs.return_value = [object()] * 14

    fake_module = SimpleNamespace(BackgroundScheduler=lambda: fake_scheduler)
    with patch.dict(
        "sys.modules",
        {"apscheduler.schedulers.background": fake_module},
    ):
        result = scheduler_mod.start_scheduler()

    assert result is fake_scheduler
    fake_scheduler.start.assert_called_once()

    # Spot-check a few critical job IDs are registered. We don't lock
    # down the full list — that would just duplicate the source — but
    # these four are load-bearing and a regression on any of them
    # would be a serious incident.
    registered_ids = {
        call.kwargs.get("id") or (call.args[3] if len(call.args) > 3 else None)
        for call in fake_scheduler.add_job.call_args_list
    }
    for required in (
        "scheduled_sends",
        "welcome_queue",
        "billing_dunning",
        "billing_invoices",
    ):
        assert required in registered_ids, f"missing job: {required}"

    # Cleanup global state so other tests aren't affected
    scheduler_mod._scheduler = None


def test_stop_scheduler_is_safe_when_not_started():
    scheduler_mod._scheduler = None
    # Should not raise
    scheduler_mod.stop_scheduler()


def test_stop_scheduler_calls_shutdown():
    fake = MagicMock()
    scheduler_mod._scheduler = fake
    scheduler_mod.stop_scheduler()
    fake.shutdown.assert_called_once_with(wait=False)
    scheduler_mod._scheduler = None


# ---- Per-job exception safety + feature-flag no-ops ----
#
# We pick a representative job from each "shape" in the module:
#   - _research_fetch       — unconditional, no feature flag
#   - _welcome_queue        — feature-flagged via cfg.welcome_sequence.enabled
#   - _scheduled_sends      — feature-flagged via cfg.scheduler.enabled
#   - _marketing_outreach   — gated on agents.default_autonomy
#   - _billing_dunning      — gated on paid_tiers.enabled + dunning_enabled
#
# For each: assert (a) it never raises and (b) when the relevant flag
# is off, the inner work isn't invoked.


def _cfg(**overrides):
    """Build a fake config namespace with sensible defaults."""
    base = SimpleNamespace(
        welcome_sequence=SimpleNamespace(enabled=False),
        scheduler=SimpleNamespace(enabled=False),
        reengagement=SimpleNamespace(enabled=False),
        agents=SimpleNamespace(default_autonomy="suggest"),
        paid_tiers=SimpleNamespace(enabled=False, dunning_enabled=False, dunning_grace_days=3),
        spotify=SimpleNamespace(enabled=False),
        audio=SimpleNamespace(enabled=False),
        sponsor_portal=SimpleNamespace(enabled=False),
        email=SimpleNamespace(),
        db_path=":memory:",
        db_backend="sqlite",
        database_url="",
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def test_research_fetch_swallows_exceptions():
    with patch("weeklyamp.web.deps.get_repo", side_effect=RuntimeError("boom")):
        scheduler_mod._research_fetch()  # must not raise


def test_welcome_queue_noop_when_disabled():
    fake_cfg = _cfg()  # welcome_sequence.enabled=False
    sentinel = MagicMock()
    with patch("weeklyamp.web.deps.get_config", return_value=fake_cfg), \
         patch("weeklyamp.web.deps.get_repo", return_value=sentinel), \
         patch("weeklyamp.content.welcome_sequence.WelcomeManager") as wm:
        scheduler_mod._welcome_queue()
        wm.assert_not_called()


def test_welcome_queue_swallows_exceptions():
    with patch("weeklyamp.web.deps.get_config", side_effect=RuntimeError("boom")):
        scheduler_mod._welcome_queue()  # must not raise


def test_scheduled_sends_noop_when_disabled():
    fake_cfg = _cfg()  # scheduler.enabled=False
    with patch("weeklyamp.web.deps.get_config", return_value=fake_cfg), \
         patch("weeklyamp.web.deps.get_repo", return_value=MagicMock()), \
         patch("weeklyamp.delivery.scheduler.SendScheduler") as ss:
        scheduler_mod._scheduled_sends()
        ss.assert_not_called()


def test_scheduled_sends_swallows_exceptions():
    fake_cfg = _cfg(scheduler=SimpleNamespace(enabled=True))
    with patch("weeklyamp.web.deps.get_config", return_value=fake_cfg), \
         patch("weeklyamp.web.deps.get_repo", side_effect=RuntimeError("boom")):
        scheduler_mod._scheduled_sends()  # must not raise


def test_marketing_outreach_noop_when_not_autonomous():
    fake_cfg = _cfg()  # agents.default_autonomy="suggest"
    with patch("weeklyamp.web.deps.get_config", return_value=fake_cfg), \
         patch("weeklyamp.web.deps.get_repo") as gr:
        scheduler_mod._marketing_outreach()
        gr.assert_not_called()


def test_marketing_outreach_swallows_exceptions():
    fake_cfg = _cfg(agents=SimpleNamespace(default_autonomy="autonomous"))
    with patch("weeklyamp.web.deps.get_config", return_value=fake_cfg), \
         patch("weeklyamp.web.deps.get_repo", side_effect=RuntimeError("boom")):
        scheduler_mod._marketing_outreach()  # must not raise


def test_billing_dunning_noop_when_disabled():
    fake_cfg = _cfg()  # paid_tiers disabled
    with patch.object(scheduler_mod, "_load_config", return_value=fake_cfg, create=True), \
         patch("weeklyamp.db.repository.Repository") as Repo:
        scheduler_mod._billing_dunning()
        Repo.assert_not_called()


def test_billing_dunning_swallows_exceptions():
    with patch.object(scheduler_mod, "_load_config", side_effect=RuntimeError("boom"), create=True):
        scheduler_mod._billing_dunning()  # must not raise
