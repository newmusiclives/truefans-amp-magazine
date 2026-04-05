"""AI subscriber segmentation engine.

Clusters subscribers by engagement patterns to enable auto-personalized
content ordering and targeted campaigns.
INACTIVE by default — requires configuration.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime
from typing import Optional

from weeklyamp.core.models import AppConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


class SegmentationEngine:
    """Cluster subscribers by engagement patterns for personalization."""

    def __init__(self, repo: Repository, config: AppConfig) -> None:
        self.repo = repo
        self.config = config

    # ---- Manual Segments ----

    def create_segment(self, name: str, description: str = "", segment_type: str = "manual", criteria_json: str = "{}") -> int:
        conn = self.repo._conn()
        cur = conn.execute(
            "INSERT INTO subscriber_segments (name, description, segment_type, criteria_json) VALUES (?, ?, ?, ?)",
            (name, description, segment_type, criteria_json),
        )
        conn.commit()
        seg_id = cur.lastrowid
        conn.close()
        return seg_id

    def get_segments(self) -> list[dict]:
        conn = self.repo._conn()
        rows = conn.execute("SELECT * FROM subscriber_segments ORDER BY created_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def add_to_segment(self, segment_id: int, subscriber_id: int, score: float = 0.0) -> None:
        conn = self.repo._conn()
        conn.execute(
            "INSERT OR IGNORE INTO subscriber_segment_members (segment_id, subscriber_id, score) VALUES (?, ?, ?)",
            (segment_id, subscriber_id, score),
        )
        conn.execute(
            "UPDATE subscriber_segments SET subscriber_count = (SELECT COUNT(*) FROM subscriber_segment_members WHERE segment_id = ?) WHERE id = ?",
            (segment_id, segment_id),
        )
        conn.commit()
        conn.close()

    def get_segment_members(self, segment_id: int, limit: int = 100) -> list[dict]:
        conn = self.repo._conn()
        rows = conn.execute(
            """SELECT ssm.*, s.email, s.first_name, s.last_name
               FROM subscriber_segment_members ssm
               JOIN subscribers s ON s.id = ssm.subscriber_id
               WHERE ssm.segment_id = ?
               ORDER BY ssm.score DESC LIMIT ?""",
            (segment_id, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---- AI Auto-Segmentation ----

    def compute_engagement_segments(self) -> dict:
        """Cluster subscribers into engagement-based segments using behavioral data.

        Creates/updates segments: power_readers, casual_readers, at_risk, dormant, new_subscribers
        """
        conn = self.repo._conn()

        # Get all active subscribers with engagement data
        subscribers = conn.execute(
            """SELECT s.id, s.email, s.created_at,
                      COUNT(CASE WHEN ete.event_type = 'open' THEN 1 END) as opens,
                      COUNT(CASE WHEN ete.event_type = 'click' THEN 1 END) as clicks,
                      MAX(ete.created_at) as last_engagement
               FROM subscribers s
               LEFT JOIN email_tracking_events ete ON ete.subscriber_id = s.id
               WHERE s.status = 'active'
               GROUP BY s.id""",
        ).fetchall()
        conn.close()

        # Define segment criteria
        segments = {
            "power_readers": {"name": "Power Readers", "desc": "High engagement — opens and clicks consistently", "members": []},
            "casual_readers": {"name": "Casual Readers", "desc": "Moderate engagement — opens sometimes", "members": []},
            "at_risk": {"name": "At Risk", "desc": "Declining engagement — haven't opened recently", "members": []},
            "dormant": {"name": "Dormant", "desc": "No engagement in 30+ days", "members": []},
            "new_subscribers": {"name": "New Subscribers", "desc": "Subscribed in the last 14 days", "members": []},
        }

        now = datetime.utcnow()
        for sub in subscribers:
            sub = dict(sub)
            opens = sub.get("opens", 0)
            clicks = sub.get("clicks", 0)
            created = sub.get("created_at", "")

            # Calculate days since last engagement
            last_eng = sub.get("last_engagement")
            days_inactive = 999
            if last_eng:
                try:
                    last_dt = datetime.fromisoformat(str(last_eng).replace("Z", "+00:00").split("+")[0])
                    days_inactive = (now - last_dt).days
                except (ValueError, TypeError):
                    pass

            # Calculate days since subscription
            days_subscribed = 999
            if created:
                try:
                    created_dt = datetime.fromisoformat(str(created).replace("Z", "+00:00").split("+")[0])
                    days_subscribed = (now - created_dt).days
                except (ValueError, TypeError):
                    pass

            # Classify
            score = opens * 1.0 + clicks * 3.0  # clicks are worth more
            if days_subscribed <= 14:
                segments["new_subscribers"]["members"].append((sub["id"], score))
            elif score >= 20 and days_inactive <= 7:
                segments["power_readers"]["members"].append((sub["id"], score))
            elif score >= 5 and days_inactive <= 14:
                segments["casual_readers"]["members"].append((sub["id"], score))
            elif days_inactive > 30:
                segments["dormant"]["members"].append((sub["id"], score))
            elif days_inactive > 14:
                segments["at_risk"]["members"].append((sub["id"], score))
            else:
                segments["casual_readers"]["members"].append((sub["id"], score))

        # Persist segments
        result = {}
        for slug, seg_data in segments.items():
            conn = self.repo._conn()
            existing = conn.execute("SELECT id FROM subscriber_segments WHERE name = ?", (seg_data["name"],)).fetchone()
            if existing:
                seg_id = existing["id"]
                conn.execute("DELETE FROM subscriber_segment_members WHERE segment_id = ?", (seg_id,))
            else:
                cur = conn.execute(
                    "INSERT INTO subscriber_segments (name, description, segment_type, criteria_json) VALUES (?, ?, 'ai', ?)",
                    (seg_data["name"], seg_data["desc"], json.dumps({"type": slug})),
                )
                seg_id = cur.lastrowid
            conn.commit()
            conn.close()

            for sub_id, score in seg_data["members"]:
                self.add_to_segment(seg_id, sub_id, score)

            result[slug] = len(seg_data["members"])

        logger.info("Engagement segments computed: %s", result)
        return result

    def personalize_section_order(self, subscriber_id: int, section_slugs: list[str]) -> list[str]:
        """Reorder sections based on subscriber's engagement profile.

        Sections the subscriber clicks on most get moved toward the top.
        """
        conn = self.repo._conn()
        profiles = conn.execute(
            "SELECT section_slug, engagement_score FROM subscriber_interest_profiles WHERE subscriber_id = ? ORDER BY engagement_score DESC",
            (subscriber_id,),
        ).fetchall()
        conn.close()

        if not profiles:
            return section_slugs

        score_map = {p["section_slug"]: p["engagement_score"] for p in profiles}
        return sorted(section_slugs, key=lambda s: score_map.get(s, 0), reverse=True)
