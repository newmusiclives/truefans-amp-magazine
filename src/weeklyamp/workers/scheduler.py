"""Background task scheduler using APScheduler.

All jobs are disabled by default. The scheduler only starts when
WEEKLYAMP_WORKERS_ENABLED=true is set in environment.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_scheduler = None


def _research_fetch():
    """Fetch content from all configured RSS/scrape sources."""
    try:
        from weeklyamp.web.deps import get_repo
        from weeklyamp.research.sources import fetch_all_sources
        repo = get_repo()
        results = fetch_all_sources(repo)
        logger.info("research_fetch completed: %s", results)
    except Exception:
        logger.exception("research_fetch failed")


def _welcome_queue():
    """Process pending welcome sequence sends."""
    try:
        from weeklyamp.web.deps import get_config, get_repo
        from weeklyamp.content.welcome_sequence import WelcomeManager
        cfg = get_config()
        if not cfg.welcome_sequence.enabled:
            return
        repo = get_repo()
        mgr = WelcomeManager(repo, cfg.welcome_sequence, cfg.email)
        pending = mgr.process_welcome_queue()
        if pending:
            logger.info("welcome_queue: %d sends pending", len(pending))
    except Exception:
        logger.exception("welcome_queue failed")


def _scheduled_sends():
    """Process pending scheduled newsletter sends."""
    try:
        from weeklyamp.web.deps import get_config, get_repo
        from weeklyamp.delivery.scheduler import SendScheduler
        cfg = get_config()
        if not cfg.scheduler.enabled:
            return
        repo = get_repo()
        sched = SendScheduler(repo, cfg.scheduler, cfg.email)
        sched.process_pending()
    except Exception:
        logger.exception("scheduled_sends failed")


def _reengagement_check():
    """Check for and suppress long-inactive subscribers."""
    try:
        from weeklyamp.web.deps import get_config, get_repo
        from weeklyamp.content.reengagement import ReengagementManager
        cfg = get_config()
        if not cfg.reengagement.enabled:
            return
        repo = get_repo()
        mgr = ReengagementManager(repo, cfg.reengagement)
        count = mgr.auto_suppress_inactive()
        if count:
            logger.info("reengagement_check: suppressed %d subscribers", count)
    except Exception:
        logger.exception("reengagement_check failed")


def start_scheduler():
    """Initialize and start the background scheduler.

    Returns the scheduler instance, or None if disabled.
    Only starts when WEEKLYAMP_WORKERS_ENABLED=true.
    """
    global _scheduler

    if os.environ.get("WEEKLYAMP_WORKERS_ENABLED", "false").lower() != "true":
        logger.info("Background workers disabled (set WEEKLYAMP_WORKERS_ENABLED=true to enable)")
        return None

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning("apscheduler not installed — background workers unavailable")
        return None

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(_research_fetch, "interval", hours=6, id="research_fetch", name="Fetch RSS/scrape sources")
    _scheduler.add_job(_welcome_queue, "interval", minutes=30, id="welcome_queue", name="Process welcome sequence")
    _scheduler.add_job(_scheduled_sends, "interval", seconds=60, id="scheduled_sends", name="Process scheduled sends")
    _scheduler.add_job(_reengagement_check, "cron", hour=3, id="reengagement_check", name="Re-engagement check")

    _scheduler.start()
    logger.info("Background scheduler started with %d jobs", len(_scheduler.get_jobs()))
    return _scheduler


def stop_scheduler():
    """Gracefully stop the background scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")
        _scheduler = None
