"""Automated growth metrics collection.

Collects daily subscriber counts, churn, engagement averages, and
persists them to the growth_metrics table for dashboard reporting.
This module is INACTIVE by default — it checks the analytics config
flag before performing any work.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from weeklyamp.core.models import AppConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


class GrowthCollector:
    """Compute and store daily growth metrics."""

    def __init__(self, repo: Repository, config: AppConfig) -> None:
        self.repo = repo
        self.config = config

    @property
    def _enabled(self) -> bool:
        return self.config.analytics.tracking_enabled

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def collect_daily_metrics(self) -> Optional[int]:
        """Compute today's growth snapshot and save to growth_metrics.

        Returns the new row id, or ``None`` if the feature is disabled.
        """
        if not self._enabled:
            logger.debug("Growth collection disabled — skipping")
            return None

        today = date.today().isoformat()
        conn = self.repo._conn()
        try:
            # Total active subscribers
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM subscribers WHERE status = 'active'"
            ).fetchone()
            total_subscribers: int = row["c"] if row else 0

            # New subscribers today (subscribed_at >= today)
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM subscribers WHERE subscribed_at >= ?",
                (today,),
            ).fetchone()
            new_subscribers: int = row["c"] if row else 0

            # Churned subscribers today (status changed to unsubscribed today)
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM subscribers "
                "WHERE status = 'unsubscribed' AND synced_at >= ?",
                (today,),
            ).fetchone()
            churned_subscribers: int = row["c"] if row else 0

            # Average open / click rates from recent engagement_metrics
            row = conn.execute(
                "SELECT AVG(open_rate) AS avg_or, AVG(click_rate) AS avg_cr "
                "FROM engagement_metrics ORDER BY id DESC LIMIT 10"
            ).fetchone()
            open_rate_avg: float = round(row["avg_or"] or 0.0, 2) if row else 0.0
            click_rate_avg: float = round(row["avg_cr"] or 0.0, 2) if row else 0.0

            conn.close()

            # Persist via repo helper
            row_id = self.repo.save_growth_metric(
                metric_date=today,
                total_subscribers=total_subscribers,
                new_subscribers=new_subscribers,
                churned_subscribers=churned_subscribers,
                open_rate_avg=open_rate_avg,
                click_rate_avg=click_rate_avg,
            )
            logger.info(
                "Collected daily metrics for %s: total=%d new=%d churned=%d",
                today, total_subscribers, new_subscribers, churned_subscribers,
            )
            return row_id
        except Exception:
            logger.exception("Failed to collect daily metrics")
            conn.close()
            return None

    def collect_engagement_for_issue(self, issue_id: int) -> Optional[int]:
        """Query email_tracking_events to compute opens/clicks for an issue
        and save to engagement_metrics.

        Returns the engagement row id, or ``None`` if disabled.
        """
        if not self._enabled:
            logger.debug("Growth collection disabled — skipping engagement collection")
            return None

        conn = self.repo._conn()
        try:
            # Count distinct opens
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM email_tracking_events "
                "WHERE issue_id = ? AND event_type = 'open'",
                (issue_id,),
            ).fetchone()
            opens: int = row["c"] if row else 0

            # Count distinct clicks
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM email_tracking_events "
                "WHERE issue_id = ? AND event_type = 'click'",
                (issue_id,),
            ).fetchone()
            clicks: int = row["c"] if row else 0

            # Total sends (count subscribers who were sent this issue)
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM email_tracking_events "
                "WHERE issue_id = ? AND event_type = 'send'",
                (issue_id,),
            ).fetchone()
            sends: int = row["c"] if row else 0

            conn.close()

            open_rate = round(opens / sends, 4) if sends > 0 else 0.0
            click_rate = round(clicks / sends, 4) if sends > 0 else 0.0

            row_id = self.repo.save_engagement(
                issue_id=issue_id,
                ghl_campaign_id="",
                sends=sends,
                opens=opens,
                clicks=clicks,
                open_rate=open_rate,
                click_rate=click_rate,
            )
            logger.info(
                "Engagement for issue %d: sends=%d opens=%d clicks=%d",
                issue_id, sends, opens, clicks,
            )
            return row_id
        except Exception:
            logger.exception("Failed to collect engagement for issue %d", issue_id)
            conn.close()
            return None

    def get_dashboard_summary(self, days: int = 30) -> dict:
        """Return a summary dict with trend data for the growth dashboard.

        Returns a dict with keys:
        - ``latest``: most recent day's metrics (dict or None)
        - ``trend``: list of daily metric dicts in chronological order
        - ``total_growth``: net subscriber change over the period
        - ``avg_open_rate``: average open rate over the period
        - ``avg_click_rate``: average click rate over the period
        """
        if not self._enabled:
            return {
                "latest": None,
                "trend": [],
                "total_growth": 0,
                "avg_open_rate": 0.0,
                "avg_click_rate": 0.0,
            }

        trend = self.repo.get_growth_trend(days)

        latest = trend[-1] if trend else None

        total_growth = 0
        open_rates: list[float] = []
        click_rates: list[float] = []
        for m in trend:
            total_growth += m.get("new_subscribers", 0) - m.get("churned_subscribers", 0)
            if m.get("open_rate_avg"):
                open_rates.append(m["open_rate_avg"])
            if m.get("click_rate_avg"):
                click_rates.append(m["click_rate_avg"])

        avg_open = round(sum(open_rates) / len(open_rates), 2) if open_rates else 0.0
        avg_click = round(sum(click_rates) / len(click_rates), 2) if click_rates else 0.0

        return {
            "latest": latest,
            "trend": trend,
            "total_growth": total_growth,
            "avg_open_rate": avg_open,
            "avg_click_rate": avg_click,
        }
