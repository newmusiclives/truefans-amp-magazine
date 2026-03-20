"""Section engagement scoring engine.

Tracks per-section click engagement, computes time-decayed subscriber
interest profiles, and can reorder newsletter sections by engagement.
INACTIVE by default — enable via config.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Optional

from weeklyamp.core.models import SectionEngagementConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


class SectionScorer:
    """Record and score section-level engagement for personalisation."""

    def __init__(self, repo: Repository, config: SectionEngagementConfig) -> None:
        self.repo = repo
        self.config = config

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_section_click(
        self,
        subscriber_id: int,
        issue_id: int,
        section_slug: str,
        link_url: str = "",
    ) -> Optional[int]:
        """Record a section engagement (click) event via the repository.

        Returns the event id or ``None`` if the feature is disabled.
        """
        if not self.config.enabled:
            return None

        return self.repo.record_section_engagement(
            subscriber_id=subscriber_id,
            issue_id=issue_id,
            section_slug=section_slug,
            event_type="click",
            link_url=link_url,
        )

    # ------------------------------------------------------------------
    # Per-issue score computation
    # ------------------------------------------------------------------

    def compute_section_scores(self, issue_id: int) -> list[dict]:
        """Aggregate clicks per section for *issue_id*.

        Upserts results into ``section_engagement_scores`` and returns a
        list of ``{section_slug, total_clicks, unique_clickers, click_rate}``.
        """
        if not self.config.enabled:
            return []

        stats = self.repo.get_section_engagement_stats(issue_id=issue_id)

        # Get total subscriber count for click-rate calculation
        total_subs = self.repo.get_subscriber_count() or 1

        conn = self.repo._conn()
        for s in stats:
            click_rate = round(s["unique_clickers"] / total_subs, 4) if total_subs else 0.0
            s["click_rate"] = click_rate
            conn.execute(
                """INSERT INTO section_engagement_scores
                   (section_slug, issue_id, total_clicks, unique_clickers, click_rate, computed_at)
                   VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(section_slug, issue_id) DO UPDATE SET
                       total_clicks=excluded.total_clicks,
                       unique_clickers=excluded.unique_clickers,
                       click_rate=excluded.click_rate,
                       computed_at=CURRENT_TIMESTAMP""",
                (s["section_slug"], issue_id, s["total_clicks"], s["unique_clickers"], click_rate),
            )
        conn.commit()
        conn.close()

        logger.info("Computed section scores for issue %d: %d sections", issue_id, len(stats))
        return stats

    # ------------------------------------------------------------------
    # Subscriber interest profile
    # ------------------------------------------------------------------

    def build_subscriber_profile(self, subscriber_id: int) -> list[dict]:
        """Compute engagement score per section with time decay.

        ``score = sum(clicks * decay_factor)`` where
        ``decay_factor = exp(-days_since / score_decay_days)``.

        Results are upserted into ``subscriber_interest_profiles``.
        Returns the list of ``{section_slug, engagement_score, click_count}``.
        """
        if not self.config.enabled:
            return []

        decay_days = self.config.score_decay_days or 90
        now = datetime.utcnow()

        conn = self.repo._conn()
        rows = conn.execute(
            """SELECT section_slug, created_at
               FROM section_engagement_events
               WHERE subscriber_id = ?
               ORDER BY section_slug, created_at""",
            (subscriber_id,),
        ).fetchall()
        conn.close()

        # Aggregate per section
        section_data: dict[str, dict] = {}
        for r in rows:
            slug = r["section_slug"]
            created_str = r["created_at"]
            if isinstance(created_str, str):
                try:
                    created = datetime.fromisoformat(created_str.replace("Z", "+00:00")).replace(tzinfo=None)
                except ValueError:
                    created = now
            else:
                created = created_str.replace(tzinfo=None) if created_str else now

            days_since = max((now - created).total_seconds() / 86400, 0)
            decay_factor = math.exp(-days_since / decay_days)

            entry = section_data.setdefault(slug, {"score": 0.0, "clicks": 0})
            entry["score"] += decay_factor
            entry["clicks"] += 1

        # Upsert profiles
        profiles: list[dict] = []
        for slug, data in section_data.items():
            score = round(data["score"], 4)
            self.repo.upsert_subscriber_interest(
                subscriber_id=subscriber_id,
                section_slug=slug,
                engagement_score=score,
                click_count=data["clicks"],
            )
            profiles.append({
                "section_slug": slug,
                "engagement_score": score,
                "click_count": data["clicks"],
            })

        profiles.sort(key=lambda p: -p["engagement_score"])
        logger.info(
            "Built interest profile for subscriber %d: %d sections",
            subscriber_id, len(profiles),
        )
        return profiles

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def get_section_performance_dashboard(self) -> list[dict]:
        """Return all sections with total clicks, unique clickers, and avg click rate.

        Aggregates across all issues from ``section_engagement_scores``.
        """
        if not self.config.enabled:
            return []

        conn = self.repo._conn()
        rows = conn.execute(
            """SELECT section_slug,
                      SUM(total_clicks) as total_clicks,
                      SUM(unique_clickers) as unique_clickers,
                      AVG(click_rate) as avg_click_rate,
                      COUNT(DISTINCT issue_id) as issue_count
               FROM section_engagement_scores
               GROUP BY section_slug
               ORDER BY total_clicks DESC""",
        ).fetchall()
        conn.close()

        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Reorder sections
    # ------------------------------------------------------------------

    def reorder_sections_by_engagement(
        self, sections: list[dict], subscriber_id: int,
    ) -> list[dict]:
        """If the subscriber has an interest profile, reorder sections by
        engagement score.  Otherwise return the original order.
        """
        if not self.config.enabled or not self.config.reorder_by_engagement:
            return sections

        interests = self.repo.get_subscriber_interests(subscriber_id)
        if not interests or len(interests) < self.config.min_events_for_profile:
            return sections

        score_map = {i["section_slug"]: i["engagement_score"] for i in interests}

        scored: list[tuple[float, int, dict]] = []
        unscored: list[tuple[int, dict]] = []

        for idx, sec in enumerate(sections):
            slug = sec.get("slug", sec.get("section_slug", ""))
            if slug in score_map:
                scored.append((score_map[slug], idx, sec))
            else:
                unscored.append((idx, sec))

        scored.sort(key=lambda t: (-t[0], t[1]))

        return [s for _, _, s in scored] + [s for _, s in unscored]
