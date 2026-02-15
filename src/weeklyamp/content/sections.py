"""Section registry — reads active sections from the database."""

from __future__ import annotations

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
