"""Programmatic ad marketplace — bid-based sponsor slot allocation.

Advertisers bid on sponsor positions (top/mid/bottom) for specific editions and dates.
A daily auction selects winners and assigns their ad creatives to upcoming issues.
INACTIVE by default — requires sponsor_portal.enabled=true.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from weeklyamp.core.models import AppConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


class AdMarketplace:
    """Bid-based sponsor slot auction system."""

    def __init__(self, repo: Repository, config: AppConfig) -> None:
        self.repo = repo
        self.config = config

    def place_bid(
        self,
        campaign_id: int,
        advertiser_id: int,
        edition_slug: str,
        position: str,
        bid_cents: int,
        target_date: str,
    ) -> int:
        """Place a bid on a sponsor slot."""
        conn = self.repo._conn()
        cur = conn.execute(
            """INSERT INTO ad_bids (campaign_id, advertiser_id, edition_slug, position, bid_cents, target_date, status)
               VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
            (campaign_id, advertiser_id, edition_slug, position, bid_cents, target_date),
        )
        conn.commit()
        bid_id = cur.lastrowid
        conn.close()
        return bid_id

    def get_pending_bids(self, target_date: str = "", edition_slug: str = "") -> list[dict]:
        """Get pending bids, optionally filtered by date and edition."""
        conn = self.repo._conn()
        sql = "SELECT * FROM ad_bids WHERE status = 'pending'"
        params: list = []
        if target_date:
            sql += " AND target_date = ?"
            params.append(target_date)
        if edition_slug:
            sql += " AND edition_slug = ?"
            params.append(edition_slug)
        sql += " ORDER BY bid_cents DESC"
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def run_daily_auction(self, target_date: str = "") -> dict:
        """Run the auction for a given date — highest bid per position wins.

        Returns dict with winning bids and results.
        """
        if not target_date:
            target_date = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")

        bids = self.get_pending_bids(target_date=target_date)
        if not bids:
            return {"date": target_date, "winners": [], "losers": []}

        # Group by (edition_slug, position), pick highest bid
        slot_winners: dict[tuple[str, str], dict] = {}
        for bid in bids:
            key = (bid["edition_slug"], bid["position"])
            if key not in slot_winners or bid["bid_cents"] > slot_winners[key]["bid_cents"]:
                slot_winners[key] = bid

        winning_ids = {b["id"] for b in slot_winners.values()}
        winners = []
        losers = []

        conn = self.repo._conn()
        for bid in bids:
            if bid["id"] in winning_ids:
                conn.execute("UPDATE ad_bids SET status = 'won' WHERE id = ?", (bid["id"],))
                winners.append(bid)
            else:
                conn.execute("UPDATE ad_bids SET status = 'lost' WHERE id = ?", (bid["id"],))
                losers.append(bid)
        conn.commit()
        conn.close()

        logger.info(
            "Auction for %s: %d winners, %d losers, total revenue $%.2f",
            target_date, len(winners), len(losers),
            sum(w["bid_cents"] for w in winners) / 100,
        )

        return {"date": target_date, "winners": winners, "losers": losers}

    def get_auction_results(self, target_date: str) -> dict:
        """Get auction results for a specific date."""
        conn = self.repo._conn()
        winners = conn.execute(
            "SELECT * FROM ad_bids WHERE target_date = ? AND status = 'won' ORDER BY bid_cents DESC",
            (target_date,),
        ).fetchall()
        conn.close()
        return {
            "date": target_date,
            "winners": [dict(r) for r in winners],
            "total_revenue_cents": sum(r["bid_cents"] for r in winners),
        }

    def cancel_bid(self, bid_id: int) -> bool:
        """Cancel a pending bid."""
        conn = self.repo._conn()
        result = conn.execute(
            "UPDATE ad_bids SET status = 'cancelled' WHERE id = ? AND status = 'pending'",
            (bid_id,),
        )
        conn.commit()
        changed = result.rowcount > 0
        conn.close()
        return changed
