"""Embed widget routes — embeddable subscribe form, badge, and admin code page."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from jinja2 import Environment, FileSystemLoader

from weeklyamp.content.embed_widget import (
    generate_badge_html,
    generate_embed_code,
    generate_milestone_html,
)
from weeklyamp.web.deps import get_config, get_repo, render

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent.parent / "templates" / "web"
_pub_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)

router = APIRouter()


@router.get("/embed/subscribe", response_class=HTMLResponse)
async def embed_subscribe(
    edition: str = Query("", description="Pre-select edition slug"),
    style: str = Query("dark", description="Widget style: dark or light"),
):
    """Return embeddable subscribe form HTML (standalone, no base.html)."""
    cfg = get_config()
    html_code = generate_embed_code(
        site_domain=cfg.site_domain,
        edition_slug=edition,
        style=style,
    )
    return HTMLResponse(html_code)


@router.get("/embed/badge", response_class=HTMLResponse)
async def embed_badge(
    text: str = Query("Featured in TrueFans NEWSLETTERS", description="Badge text"),
):
    """Return badge HTML."""
    cfg = get_config()
    html_code = generate_badge_html(
        site_domain=cfg.site_domain,
        text=text,
    )
    return HTMLResponse(html_code)


@router.get("/embed/code", response_class=HTMLResponse)
async def embed_codes_page():
    """Admin page showing embed code snippets with previews."""
    cfg = get_config()
    repo = get_repo()

    subscribe_dark = generate_embed_code(cfg.site_domain, style="dark")
    subscribe_light = generate_embed_code(cfg.site_domain, style="light")
    badge = generate_badge_html(cfg.site_domain)
    milestone = generate_milestone_html(repo, cfg)

    return render("embed_codes.html",
        subscribe_dark=subscribe_dark,
        subscribe_light=subscribe_light,
        badge=badge,
        milestone=milestone,
        site_domain=cfg.site_domain,
    )
