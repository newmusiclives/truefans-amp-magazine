"""Section rotation engine — selects rotating sections for each issue."""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Optional

from weeklyamp.db.repository import Repository


def select_rotating_sections(
    repo: Repository, max_rotating: int = 3, lookback: int = 4,
    max_per_category: int = 2,
) -> list[str]:
    """Select rotating sections for the next issue using weighted random selection.

    Sections that haven't been used recently are weighted more heavily.
    Category-aware: ensures variety across categories (max_per_category from same category).
    """
    rotating = repo.get_sections_by_type("rotating")
    if not rotating:
        return []

    # Get recent rotation log to see what's been used
    recent_logs = repo.get_recent_rotation_log(lookback)

    # Count recent appearances per slug
    appearance_count: dict[str, int] = defaultdict(int)
    for log in recent_logs:
        if log["was_included"]:
            appearance_count[log["section_slug"]] += 1

    # Build weights: less recently used = higher weight
    slugs = [s["slug"] for s in rotating]
    categories = {s["slug"]: s.get("category", "") for s in rotating}
    weights = []
    for slug in slugs:
        count = appearance_count.get(slug, 0)
        # Weight inversely proportional to recent usage
        weight = max(1, lookback + 1 - count)
        weights.append(weight)

    # Select sections with category diversity
    selected: list[str] = []
    category_counts: dict[str, int] = defaultdict(int)
    available = list(zip(slugs, weights))

    while len(selected) < max_rotating and available:
        # Filter out sections whose category is already at max
        filtered = [
            (s, w) for s, w in available
            if category_counts[categories.get(s, "")] < max_per_category
        ]
        if not filtered:
            # All categories at max, allow any remaining
            filtered = available

        f_slugs, f_weights = zip(*filtered)
        pick = random.choices(f_slugs, weights=f_weights, k=1)[0]

        if pick not in selected:
            selected.append(pick)
            cat = categories.get(pick, "")
            category_counts[cat] += 1

        # Remove pick from available
        available = [(s, w) for s, w in available if s != pick]

    return selected


def get_sections_for_issue(
    repo: Repository,
    issue_id: int,
    schedule_sections: Optional[list[str]] = None,
) -> list[dict]:
    """Get the full list of sections for an issue: core + selected rotating.

    If schedule_sections is provided (from multi-frequency config), use those
    instead of selecting rotating sections dynamically.
    """
    core = repo.get_sections_by_type("core")

    if schedule_sections:
        # Use schedule-defined sections
        all_slugs = set(schedule_sections)
        extra = [repo.get_section(s) for s in schedule_sections if s not in {c["slug"] for c in core}]
        extra = [s for s in extra if s]  # filter None
        sections = core + extra
    else:
        # Dynamically select rotating sections
        rotating_slugs = select_rotating_sections(repo)
        rotating = [repo.get_section(s) for s in rotating_slugs]
        rotating = [s for s in rotating if s]
        sections = core + rotating

        # Log rotation
        all_rotating = repo.get_sections_by_type("rotating")
        for sec in all_rotating:
            was_included = sec["slug"] in rotating_slugs
            repo.log_rotation(issue_id, sec["slug"], was_included)

    # Sort by sort_order
    sections.sort(key=lambda s: s.get("sort_order", 99))
    return sections
