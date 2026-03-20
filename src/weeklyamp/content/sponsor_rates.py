"""Dynamic rate card engine for sponsor pricing and slot availability."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional


class RateCardEngine:
    """Calculate dynamic sponsor rates based on audience metrics and config."""

    POSITIONS = ["top", "mid", "bottom"]
    POSITION_LABELS = {"top": "Premium Top", "mid": "Mid-Content", "bottom": "Footer"}
    POSITION_MULTIPLIERS = {"top": 1.5, "mid": 1.0, "bottom": 0.7}

    def __init__(self, repo, config) -> None:
        self.repo = repo
        self.config = config  # SponsorPortalConfig

    def calculate_rates(self, edition_slug: str = "") -> dict:
        """Calculate CPM rates based on actual subscriber counts and open rates.

        Returns dict keyed by position with {cpm, per_issue, per_week, per_month}.
        """
        base_cpm = self.config.base_cpm
        weekly_discount = self.config.weekly_discount
        monthly_discount = self.config.monthly_discount

        # Get subscriber count
        sub_count = self.repo.get_subscriber_count()
        if sub_count < 1:
            sub_count = 1

        # Estimate per-thousand cost
        thousands = sub_count / 1000.0

        rates = {}
        for pos in self.POSITIONS:
            multiplier = self.POSITION_MULTIPLIERS[pos]
            cpm = round(base_cpm * multiplier, 2)
            per_issue = round(cpm * thousands, 2)
            per_week = round(per_issue * 3 * weekly_discount, 2)   # 3 issues/week
            per_month = round(per_issue * 12 * monthly_discount, 2)  # ~12 issues/month

            rates[pos] = {
                "label": self.POSITION_LABELS[pos],
                "cpm": cpm,
                "per_issue": per_issue,
                "per_week": per_week,
                "per_month": per_month,
                "multiplier": multiplier,
            }

        return rates

    def get_available_slots(self, weeks_ahead: int = 4) -> list[dict]:
        """Check upcoming issues for open sponsor slots.

        Returns list of available date/edition/position combos.
        """
        editions = self.repo.get_editions(active_only=True)
        all_blocks = self.repo.get_all_sponsor_blocks()

        # Build set of filled slots
        filled = set()
        for b in all_blocks:
            filled.add((b["edition_slug"], b["edition_number"], b["position"]))

        available = []
        today = datetime.now().date()

        for week_offset in range(weeks_ahead):
            week_start = today + timedelta(weeks=week_offset)
            week_label = week_start.strftime("%b %d") + " - " + (week_start + timedelta(days=6)).strftime("%b %d, %Y")

            for ed in editions:
                for edition_num in [1, 2, 3]:
                    for pos in self.POSITIONS:
                        key = (ed["slug"], edition_num, pos)
                        if key not in filled:
                            available.append({
                                "week_label": week_label,
                                "week_offset": week_offset,
                                "edition_slug": ed["slug"],
                                "edition_name": ed.get("name", ed["slug"]),
                                "edition_number": edition_num,
                                "position": pos,
                                "position_label": self.POSITION_LABELS[pos],
                            })

        return available

    def get_media_kit_data(self) -> dict:
        """Compile data for the public media kit / advertise page."""
        editions = self.repo.get_editions(active_only=True)
        sub_count = self.repo.get_subscriber_count()

        edition_descriptions = {
            "fan": "Passionate music fans who discover, share, and support artists",
            "artist": "Independent and emerging artists building their careers",
            "industry": "Music industry professionals, labels, and decision-makers",
        }

        edition_data = []
        for ed in editions:
            slug = ed["slug"]
            edition_data.append({
                "slug": slug,
                "name": ed.get("name", slug.title()),
                "description": edition_descriptions.get(slug, ""),
                "subscriber_count": sub_count // max(len(editions), 1),
            })

        # Estimate engagement rates (placeholder defaults)
        avg_open_rate = 45.0
        avg_click_rate = 8.0

        rates = self.calculate_rates()
        available_slots = self.get_available_slots(weeks_ahead=4)

        return {
            "total_subscribers": sub_count,
            "avg_open_rate": avg_open_rate,
            "avg_click_rate": avg_click_rate,
            "issues_per_week": 3,
            "editions": edition_data,
            "rates": rates,
            "available_slots": available_slots,
            "available_slot_count": len(available_slots),
        }
