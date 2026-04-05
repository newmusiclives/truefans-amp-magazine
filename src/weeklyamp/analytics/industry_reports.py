"""Industry reports & data analytics product.

Aggregates anonymized data from the platform to generate insights
on genre trends, engagement patterns, streaming data, and market overviews.
Exposed via metered API for labels, distributors, and DSPs.
INACTIVE by default — requires data_product.enabled=true.
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


class IndustryReportGenerator:
    """Generate anonymized industry trend reports from platform data."""

    def __init__(self, repo: Repository, config: AppConfig) -> None:
        self.repo = repo
        self.config = config

    def generate_genre_trends(self, period: str = "") -> dict:
        """Analyze genre popularity trends from subscriber preferences and submissions."""
        if not period:
            period = datetime.utcnow().strftime("%Y-%m")

        conn = self.repo._conn()

        # Genre distribution from subscriber preferences
        genre_counts = conn.execute(
            "SELECT genre, COUNT(*) as count FROM subscriber_genres GROUP BY genre ORDER BY count DESC"
        ).fetchall()

        # Genre from submissions
        submission_genres = conn.execute(
            "SELECT genre, COUNT(*) as count FROM artist_submissions WHERE genre != '' GROUP BY genre ORDER BY count DESC"
        ).fetchall()

        conn.close()

        data = {
            "subscriber_genre_distribution": [{"genre": r["genre"], "subscribers": r["count"]} for r in genre_counts],
            "submission_genre_distribution": [{"genre": r["genre"], "submissions": r["count"]} for r in submission_genres],
            "top_genres": [r["genre"] for r in genre_counts[:10]],
        }

        report_id = self._save_report("genre_trends", period, data)
        return {"report_id": report_id, "period": period, "data": data}

    def generate_engagement_patterns(self, period: str = "") -> dict:
        """Analyze content engagement patterns — which sections perform best."""
        if not period:
            period = datetime.utcnow().strftime("%Y-%m")

        conn = self.repo._conn()

        # Section performance
        section_perf = conn.execute(
            """SELECT section_slug, AVG(click_rate) as avg_click_rate, SUM(total_clicks) as total_clicks,
                      COUNT(*) as issues_measured
               FROM section_engagement_scores
               GROUP BY section_slug
               ORDER BY avg_click_rate DESC"""
        ).fetchall()

        # Open rates by day of week
        day_perf = conn.execute(
            """SELECT CASE CAST(strftime('%w', created_at) AS INTEGER)
                        WHEN 0 THEN 'Sunday' WHEN 1 THEN 'Monday' WHEN 2 THEN 'Tuesday'
                        WHEN 3 THEN 'Wednesday' WHEN 4 THEN 'Thursday' WHEN 5 THEN 'Friday'
                        WHEN 6 THEN 'Saturday' END as day_name,
                      COUNT(*) as opens
               FROM email_tracking_events
               WHERE event_type = 'open'
               GROUP BY day_name ORDER BY opens DESC"""
        ).fetchall()

        conn.close()

        data = {
            "section_performance": [dict(r) for r in section_perf],
            "engagement_by_day": [dict(r) for r in day_perf],
            "top_sections": [r["section_slug"] for r in section_perf[:5]],
        }

        report_id = self._save_report("engagement_patterns", period, data)
        return {"report_id": report_id, "period": period, "data": data}

    def generate_streaming_data(self, period: str = "") -> dict:
        """Aggregate streaming data from Spotify cache (if enabled)."""
        if not self.config.spotify.enabled:
            return {"error": "Spotify integration not enabled"}

        if not period:
            period = datetime.utcnow().strftime("%Y-%m")

        conn = self.repo._conn()

        # Top artists by followers
        top_artists = conn.execute(
            "SELECT artist_name, spotify_followers, genres FROM spotify_artist_cache ORDER BY spotify_followers DESC LIMIT 50"
        ).fetchall()

        # Recent releases
        recent_releases = conn.execute(
            "SELECT artist_name, album_name, album_type, release_date FROM spotify_releases ORDER BY release_date DESC LIMIT 50"
        ).fetchall()

        conn.close()

        # Aggregate genre data from artist cache
        genre_counts: dict[str, int] = defaultdict(int)
        for artist in top_artists:
            genres = json.loads(artist.get("genres", "[]")) if isinstance(artist.get("genres"), str) else []
            for genre in genres:
                genre_counts[genre] += 1

        data = {
            "top_artists": [{"name": a["artist_name"], "followers": a["spotify_followers"]} for a in top_artists[:20]],
            "recent_releases": [dict(r) for r in recent_releases[:20]],
            "genre_distribution": sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:20],
        }

        report_id = self._save_report("streaming_data", period, data)
        return {"report_id": report_id, "period": period, "data": data}

    def generate_market_overview(self, period: str = "") -> dict:
        """Generate overall market overview combining all data sources."""
        if not period:
            period = datetime.utcnow().strftime("%Y-%m")

        conn = self.repo._conn()
        total_subs = self.repo.get_subscriber_count()
        total_artists = conn.execute("SELECT COUNT(*) as c FROM artist_profiles WHERE is_active = 1").fetchone()
        total_submissions = conn.execute("SELECT COUNT(*) as c FROM artist_submissions").fetchone()
        total_issues = conn.execute("SELECT COUNT(*) as c FROM issues WHERE status = 'published'").fetchone()
        conn.close()

        data = {
            "total_subscribers": total_subs,
            "total_artist_profiles": total_artists["c"] if total_artists else 0,
            "total_submissions": total_submissions["c"] if total_submissions else 0,
            "total_published_issues": total_issues["c"] if total_issues else 0,
            "period": period,
        }

        report_id = self._save_report("market_overview", period, data)
        return {"report_id": report_id, "period": period, "data": data}

    def get_report(self, report_id: int) -> Optional[dict]:
        conn = self.repo._conn()
        row = conn.execute("SELECT * FROM industry_reports WHERE id = ?", (report_id,)).fetchone()
        conn.close()
        if not row:
            return None
        result = dict(row)
        result["data"] = json.loads(result.get("data_json", "{}"))
        return result

    def get_reports(self, report_type: str = "", limit: int = 20) -> list[dict]:
        conn = self.repo._conn()
        if report_type:
            rows = conn.execute(
                "SELECT * FROM industry_reports WHERE report_type = ? ORDER BY created_at DESC LIMIT ?",
                (report_type, limit),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM industry_reports ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _save_report(self, report_type: str, period: str, data: dict) -> int:
        conn = self.repo._conn()
        summary = f"{report_type} report for {period}"
        cur = conn.execute(
            "INSERT INTO industry_reports (report_type, period, data_json, summary) VALUES (?, ?, ?, ?)",
            (report_type, period, json.dumps(data), summary),
        )
        conn.commit()
        report_id = cur.lastrowid
        conn.close()
        return report_id


# ---- API Key Metered Access ----

class DataProductAPI:
    """Metered API access for the data analytics product."""

    def __init__(self, repo: Repository, config: AppConfig) -> None:
        self.repo = repo
        self.config = config

    def validate_key(self, api_key_hash: str) -> Optional[dict]:
        """Validate a data product API key and check quota."""
        conn = self.repo._conn()
        row = conn.execute(
            "SELECT * FROM data_product_keys WHERE api_key_hash = ? AND is_active = 1",
            (api_key_hash,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        key = dict(row)
        if key["monthly_quota"] > 0 and key["current_month_usage"] >= key["monthly_quota"]:
            return None  # quota exceeded
        return key

    def record_usage(self, key_id: int, endpoint: str) -> None:
        """Record an API usage event."""
        conn = self.repo._conn()
        conn.execute(
            "INSERT INTO data_product_usage (key_id, endpoint) VALUES (?, ?)",
            (key_id, endpoint),
        )
        conn.execute(
            "UPDATE data_product_keys SET current_month_usage = current_month_usage + 1 WHERE id = ?",
            (key_id,),
        )
        conn.commit()
        conn.close()
