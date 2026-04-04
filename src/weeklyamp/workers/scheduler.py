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


def _marketing_prospect_scan():
    """Weekly: AI identifies new sponsor prospects."""
    try:
        from weeklyamp.web.deps import get_config, get_repo
        cfg = get_config()
        if not cfg.agents.default_autonomy == "autonomous":
            return  # Only run if fully autonomous
        repo = get_repo()
        from weeklyamp.agents.marketing import MarketingAgent
        agent_row = repo.get_agent_by_type("marketing")
        if not agent_row:
            return
        agent = MarketingAgent(repo, cfg, agent_row)
        task_id = repo.create_agent_task(agent_row["id"], "identify_prospects")
        agent.execute(task_id)
        logger.info("marketing_prospect_scan completed")
    except Exception:
        logger.exception("marketing_prospect_scan failed")


def _marketing_outreach():
    """Daily: Draft outreach for new prospects."""
    try:
        from weeklyamp.web.deps import get_config, get_repo
        cfg = get_config()
        if not cfg.agents.default_autonomy == "autonomous":
            return
        repo = get_repo()
        from weeklyamp.agents.marketing import MarketingAgent
        agent_row = repo.get_agent_by_type("marketing")
        if not agent_row:
            return
        agent = MarketingAgent(repo, cfg, agent_row)
        task_id = repo.create_agent_task(agent_row["id"], "draft_outreach_batch")
        agent.execute(task_id)
        logger.info("marketing_outreach completed")
    except Exception:
        logger.exception("marketing_outreach failed")


def _marketing_social():
    """Daily: Draft social posts for latest issues."""
    try:
        from weeklyamp.web.deps import get_config, get_repo
        cfg = get_config()
        if not cfg.agents.default_autonomy == "autonomous":
            return
        repo = get_repo()
        from weeklyamp.agents.marketing import MarketingAgent
        agent_row = repo.get_agent_by_type("marketing")
        if not agent_row:
            return
        agent = MarketingAgent(repo, cfg, agent_row)
        task_id = repo.create_agent_task(agent_row["id"], "draft_social_batch")
        agent.execute(task_id)
        logger.info("marketing_social completed")
    except Exception:
        logger.exception("marketing_social failed")


def _marketing_retention():
    """Daily: Check for at-risk subscribers and queue win-backs."""
    try:
        from weeklyamp.web.deps import get_config, get_repo
        cfg = get_config()
        if not cfg.agents.default_autonomy == "autonomous":
            return
        repo = get_repo()
        from weeklyamp.agents.marketing import MarketingAgent
        agent_row = repo.get_agent_by_type("marketing")
        if not agent_row:
            return
        agent = MarketingAgent(repo, cfg, agent_row)
        task_id = repo.create_agent_task(agent_row["id"], "identify_at_risk")
        agent.execute(task_id)
        # If at-risk found, draft win-backs
        task_id2 = repo.create_agent_task(agent_row["id"], "draft_winback_batch")
        agent.execute(task_id2)
        logger.info("marketing_retention completed")
    except Exception:
        logger.exception("marketing_retention failed")


def _marketing_weekly_report():
    """Weekly: Generate marketing performance report."""
    try:
        from weeklyamp.web.deps import get_config, get_repo
        cfg = get_config()
        if not cfg.agents.default_autonomy == "autonomous":
            return
        repo = get_repo()
        from weeklyamp.agents.marketing import MarketingAgent
        agent_row = repo.get_agent_by_type("marketing")
        if not agent_row:
            return
        agent = MarketingAgent(repo, cfg, agent_row)
        task_id = repo.create_agent_task(agent_row["id"], "weekly_marketing_report")
        agent.execute(task_id)
        logger.info("marketing_weekly_report completed")
    except Exception:
        logger.exception("marketing_weekly_report failed")


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

    # Marketing automation (only runs when agents.default_autonomy == "autonomous")
    _scheduler.add_job(_marketing_prospect_scan, "cron", day_of_week="mon", hour=9, id="marketing_prospect_scan", name="AI prospect identification")
    _scheduler.add_job(_marketing_outreach, "cron", hour=10, id="marketing_outreach", name="AI sponsor outreach drafts")
    _scheduler.add_job(_marketing_social, "cron", hour=11, id="marketing_social", name="AI social post drafts")
    _scheduler.add_job(_marketing_retention, "cron", hour=14, id="marketing_retention", name="AI retention check")
    _scheduler.add_job(_marketing_weekly_report, "cron", day_of_week="fri", hour=16, id="marketing_weekly_report", name="Weekly marketing report")

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
