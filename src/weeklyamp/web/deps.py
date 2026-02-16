"""Shared dependencies for web routes."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from weeklyamp.core.config import load_config
from weeklyamp.core.models import AppConfig
from weeklyamp.db.repository import Repository

_TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent / "templates" / "web"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=True,
)

# Add markdown filter
import markdown as _md

def _md_filter(text: str) -> str:
    return _md.markdown(text or "", extensions=["extra"])

_env.filters["markdown"] = _md_filter
_env.filters["truncate_words"] = lambda s, n=20: " ".join((s or "").split()[:n]) + ("..." if len((s or "").split()) > n else "")


def get_config() -> AppConfig:
    return load_config()


def get_repo() -> Repository:
    import os
    cfg = get_config()
    db_path = cfg.db_path
    if not os.path.isabs(db_path):
        if os.path.exists("/app"):
            db_path = os.path.join("/app", db_path)
        else:
            db_path = os.path.abspath(db_path)
    return Repository(db_path)


def render(template_name: str, **ctx) -> str:
    tpl = _env.get_template(template_name)
    return tpl.render(**ctx)
