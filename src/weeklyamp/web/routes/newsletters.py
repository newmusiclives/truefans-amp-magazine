"""Public newsletters page — edition details with section breakdowns."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from jinja2 import Environment, FileSystemLoader

from weeklyamp.core.config import load_config
from weeklyamp.db.repository import Repository

_TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent.parent / "templates" / "web"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)

router = APIRouter()


def _get_repo() -> Repository:
    cfg = load_config()
    db_path = cfg.db_path
    if not os.path.isabs(db_path):
        if os.path.exists("/app"):
            db_path = os.path.join("/app", db_path)
        else:
            db_path = os.path.abspath(db_path)
    return Repository(db_path)


@router.get("/newsletters", response_class=HTMLResponse)
async def newsletters_page():
    repo = _get_repo()
    editions = repo.get_editions(active_only=True)

    # Resolve section_slugs to full section details
    all_sections = repo.get_all_sections()
    sections_map = {s["slug"]: s for s in all_sections}

    editions_with_sections = []
    for ed in editions:
        slugs = [s.strip() for s in ed.get("section_slugs", "").split(",") if s.strip()]
        resolved = [sections_map[s] for s in slugs if s in sections_map]
        editions_with_sections.append({**ed, "sections": resolved})

    tpl = _env.get_template("newsletters.html")
    return tpl.render(editions=editions_with_sections)
