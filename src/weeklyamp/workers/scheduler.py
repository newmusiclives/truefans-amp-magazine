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

    # Billing automation
    _scheduler.add_job(_billing_dunning, "cron", hour=6, id="billing_dunning", name="Billing dunning check")
    _scheduler.add_job(_billing_invoice_generation, "cron", day=1, hour=2, id="billing_invoices", name="Monthly invoice generation")

    # Spotify release scanning
    _scheduler.add_job(_spotify_release_scan, "cron", hour=8, id="spotify_releases", name="Spotify release scan")

    # Audio/TTS generation (runs after scheduled sends to generate audio for published issues)
    _scheduler.add_job(_audio_generation, "cron", hour=12, id="audio_generation", name="Audio newsletter generation")

    # Ad marketplace daily auction
    _scheduler.add_job(_ad_auction, "cron", hour=5, id="ad_auction", name="Daily ad marketplace auction")

    _scheduler.start()
    logger.info("Background scheduler started with %d jobs", len(_scheduler.get_jobs()))
    return _scheduler


def _billing_dunning():
    """Check for past-due subscriptions and progress dunning state."""
    try:
        config = _load_config()
        if not config.paid_tiers.enabled or not config.paid_tiers.dunning_enabled:
            return
        from weeklyamp.db.repository import Repository
        repo = Repository(config.db_path)
        past_due = repo.get_past_due_subscriptions()
        from datetime import datetime, timedelta
        grace_days = config.paid_tiers.dunning_grace_days
        for billing in past_due:
            state = billing.get("dunning_state", "")
            started = billing.get("dunning_started_at")
            if not started:
                repo.update_dunning_state(billing["payment_subscription_id"], "grace")
                continue
            try:
                start_dt = datetime.fromisoformat(started)
            except (ValueError, TypeError):
                continue
            days_elapsed = (datetime.utcnow() - start_dt).days
            if state == "grace" and days_elapsed >= grace_days:
                repo.update_dunning_state(billing["payment_subscription_id"], "retry_1")
            elif state == "retry_1" and days_elapsed >= grace_days * 2:
                repo.update_dunning_state(billing["payment_subscription_id"], "retry_2")
            elif state == "retry_2" and days_elapsed >= grace_days * 3:
                repo.update_dunning_state(billing["payment_subscription_id"], "retry_3")
            elif state == "retry_3" and days_elapsed >= grace_days * 4:
                repo.update_billing_status(billing["payment_subscription_id"], "cancelled")
                repo.update_dunning_state(billing["payment_subscription_id"], "cancelled")
        logger.info("Dunning check complete: %d past-due subscriptions", len(past_due))
    except Exception:
        logger.exception("Billing dunning job failed")


def _billing_invoice_generation():
    """Monthly: Generate invoices for all licensees and artist newsletters."""
    try:
        config = _load_config()
        from weeklyamp.billing.invoices import InvoiceManager
        from weeklyamp.db.repository import Repository
        repo = Repository(config.db_path)
        mgr = InvoiceManager(repo, config)
        lic_ids = mgr.generate_all_licensee_invoices()
        art_ids = mgr.generate_all_artist_newsletter_invoices()
        logger.info("Invoice generation: %d licensee, %d artist newsletter", len(lic_ids), len(art_ids))
    except Exception:
        logger.exception("Invoice generation job failed")


def _spotify_release_scan():
    """Daily: Scan for new releases from artists in profiles."""
    try:
        config = _load_config()
        if not config.spotify.enabled:
            return
        from weeklyamp.content.spotify import SpotifyClient
        from weeklyamp.db.repository import Repository
        repo = Repository(config.db_path)
        client = SpotifyClient(config.spotify)
        conn = repo._conn()
        artists = conn.execute(
            "SELECT id, spotify_id FROM artist_profiles WHERE spotify_id != '' AND is_active = 1"
        ).fetchall()
        conn.close()
        synced = 0
        for artist in artists:
            try:
                client.sync_releases(repo, artist["spotify_id"])
                synced += 1
            except Exception:
                continue
        logger.info("Spotify release scan: checked %d artists, synced %d", len(artists), synced)
    except Exception:
        logger.exception("Spotify release scan job failed")


def _audio_generation():
    """Generate audio/TTS versions of published issues."""
    try:
        config = _load_config()
        if not config.audio.enabled:
            return
        from weeklyamp.content.audio import generate_audio_for_issue
        from weeklyamp.db.repository import Repository
        repo = Repository(config.db_path)
        conn = repo._conn()
        issues = conn.execute(
            "SELECT ai.issue_id, ai.html_content FROM assembled_issues ai "
            "JOIN issues i ON i.id = ai.issue_id "
            "WHERE i.status = 'published' AND ai.audio_url = '' "
            "ORDER BY ai.id DESC LIMIT 3"
        ).fetchall()
        conn.close()
        for issue in issues:
            try:
                generate_audio_for_issue(repo, config, issue["issue_id"])
            except Exception:
                logger.exception("Audio generation failed for issue %s", issue["issue_id"])
        logger.info("Audio generation: processed %d issues", len(issues))
    except Exception:
        logger.exception("Audio generation job failed")


def _ad_auction():
    """Daily: Run ad marketplace auction for tomorrow's sponsor slots."""
    try:
        config = _load_config()
        if not config.sponsor_portal.enabled:
            return
        from weeklyamp.billing.ad_marketplace import AdMarketplace
        from weeklyamp.db.repository import Repository
        repo = Repository(config.db_path)
        marketplace = AdMarketplace(repo, config)
        results = marketplace.run_daily_auction()
        logger.info("Ad auction: %d winners", len(results.get("winners", [])))
    except Exception:
        logger.exception("Ad auction job failed")


def stop_scheduler():
    """Gracefully stop the background scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")
        _scheduler = None
