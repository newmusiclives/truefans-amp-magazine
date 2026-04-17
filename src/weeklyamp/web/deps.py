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

# Add markdown filter with XSS sanitization
import markdown as _md
from markupsafe import Markup

from weeklyamp.web.sanitize import sanitize_html


def _md_filter(text: str) -> str:
    raw = _md.markdown(text or "", extensions=["extra"])
    return Markup(sanitize_html(raw))

_env.filters["markdown"] = _md_filter
_env.filters["truncate_words"] = lambda s, n=20: " ".join((s or "").split()[:n]) + ("..." if len((s or "").split()) > n else "")

# Expose feature flag resolver to all templates as `ff(name)` so the
# sidebar can hide links for off-flag features instead of letting users
# click into a 404. Uses the shared cache in core.feature_flags.
def _ff(name: str) -> bool:
    from weeklyamp.core.feature_flags import enabled
    try:
        return enabled(name)
    except Exception:
        return False

_env.globals["ff"] = _ff


import re as _re

def _plain_preview(text: str, max_len: int = 140) -> str:
    """Strip markdown formatting and return a short plain-text preview."""
    if not text:
        return ""
    # Skip title/author header lines
    lines = text.split("\n")
    body_lines = [l for l in lines if l.strip() and not l.startswith("**") and not l.startswith("*By ") and not l.startswith("[Read")]
    plain = " ".join(body_lines)
    plain = _re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', plain)  # [text](url) -> text
    plain = plain.replace("**", "").replace("*", "")
    plain = " ".join(plain.split())  # collapse whitespace
    if len(plain) > max_len:
        plain = plain[:max_len].rsplit(" ", 1)[0] + "..."
    return plain

_env.filters["plain_preview"] = _plain_preview


def _initials(name: str) -> str:
    """Extract 2-char initials from a name."""
    if not name:
        return "?"
    parts = name.replace('"', "").split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return parts[0][:2].upper()


def _avatar_color(name: str) -> str:
    """Deterministic hex color from a name string."""
    h = hash(name or "agent") & 0xFFFFFF
    # Ensure decent saturation/lightness by mixing with a base
    r = 80 + (h >> 16 & 0xFF) % 140
    g = 80 + (h >> 8 & 0xFF) % 140
    b = 80 + (h & 0xFF) % 140
    return f"#{r:02x}{g:02x}{b:02x}"


_env.filters["initials"] = _initials
_env.filters["avatar_color"] = _avatar_color


def get_config() -> AppConfig:
    return load_config()


def get_repo() -> Repository:
    import os
    cfg = get_config()
    db_path = cfg.db_path
    backend = cfg.db_backend
    database_url = cfg.database_url
    if backend == "sqlite" and not os.path.isabs(db_path):
        if os.path.exists("/app"):
            db_path = os.path.join("/app", db_path)
        else:
            db_path = os.path.abspath(db_path)
    return Repository(db_path, database_url, backend)


def render(template_name: str, **ctx) -> str:
    tpl = _env.get_template(template_name)
    return tpl.render(**ctx)
