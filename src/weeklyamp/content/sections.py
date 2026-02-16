"""Section registry — reads active sections from the database."""

from __future__ import annotations

from collections import defaultdict

from weeklyamp.db.repository import Repository


def get_section_slugs(repo: Repository) -> list[str]:
    """Return ordered list of active section slugs."""
    sections = repo.get_active_sections()
    return [s["slug"] for s in sections]


def get_section_map(repo: Repository) -> dict[str, dict]:
    """Return {slug: section_dict} for all active sections."""
    sections = repo.get_active_sections()
    return {s["slug"]: s for s in sections}


def validate_section(repo: Repository, slug: str) -> bool:
    """Check if a section slug exists and is active."""
    section = repo.get_section(slug)
    return section is not None and bool(section.get("is_active", False))


def get_sections_by_category(repo: Repository) -> dict[str, list[dict]]:
    """Return active sections grouped by category."""
    sections = repo.get_active_sections()
    grouped: dict[str, list[dict]] = defaultdict(list)
    for s in sections:
        cat = s.get("category") or "uncategorized"
        grouped[cat].append(s)
    return dict(grouped)


def build_week_section_plan(
    repo: Repository,
    schedules: list[dict],
) -> dict[str, list[str]]:
    """Build a section plan ensuring at least 1 section from each category per week.

    Takes the configured send schedules (with their assigned section_slugs)
    and fills in any missing category coverage by rotating sections across days.

    Returns {day_of_week: [slugs]}.
    """
    sections_by_cat = get_sections_by_category(repo)
    all_categories = set(sections_by_cat.keys())

    # Build initial plan from schedule config
    plan: dict[str, list[str]] = {}
    for sched in schedules:
        day = sched["day_of_week"]
        raw = sched.get("section_slugs", "")
        slugs = [s.strip() for s in raw.split(",") if s.strip()] if raw else []
        plan[day] = slugs

    if not plan:
        return plan

    # Map slugs to categories for quick lookup
    section_map = get_section_map(repo)
    slug_to_cat: dict[str, str] = {}
    for slug, sec in section_map.items():
        slug_to_cat[slug] = sec.get("category") or "uncategorized"

    # Find which categories are already covered
    covered_categories: set[str] = set()
    for slugs in plan.values():
        for slug in slugs:
            cat = slug_to_cat.get(slug)
            if cat:
                covered_categories.add(cat)

    # Use rotation log to pick least-recently-used sections for uncovered categories
    recent_log = repo.get_recent_rotation_log(n=8)
    recently_used_slugs = {r["section_slug"] for r in recent_log}

    uncovered = all_categories - covered_categories
    days = list(plan.keys())

    for cat in sorted(uncovered):
        cat_sections = sections_by_cat.get(cat, [])
        if not cat_sections:
            continue

        # Pick the section from this category that was least recently used
        unused = [s for s in cat_sections if s["slug"] not in recently_used_slugs]
        pick = unused[0] if unused else cat_sections[0]

        # Add to the day with fewest sections
        target_day = min(days, key=lambda d: len(plan[d]))
        if pick["slug"] not in plan[target_day]:
            plan[target_day].append(pick["slug"])

    # Always ensure ps_from_ps is on every day
    for day in plan:
        if "ps_from_ps" not in plan[day]:
            plan[day].append("ps_from_ps")

    return plan
