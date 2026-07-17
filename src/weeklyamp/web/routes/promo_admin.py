"""Admin UI for the ecosystem cross-sell promo block (AMP / RISE / EDGE).

Lets an admin edit the promo copy, routing, and destination URLs at
runtime. Edits are stored as a JSON overlay in ``admin_settings`` (see
:func:`weeklyamp.content.promo.effective_promo_config`) so they take effect
on the next assembled edition with no deploy. Also surfaces first-party
click performance from ``promo_events``.
"""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from weeklyamp.content.promo import PROMO_SETTINGS_KEY, effective_promo_config
from weeklyamp.web.deps import get_config, get_repo, render
from weeklyamp.web.routes.admin_account import _ensure_csrf, _require_admin

router = APIRouter()

TARGET_KEYS = ["amp", "rise", "edge"]
ROUTE_EDITIONS = ["fan", "artist", "industry"]


def _env_forced() -> bool:
    return os.getenv("WEEKLYAMP_PROMO_ENABLED", "").lower() in ("1", "true", "yes")


@router.get("/", response_class=HTMLResponse)
async def promo_admin_page(request: Request) -> Response:
    redirect = _require_admin(request)
    if redirect is not None:
        return redirect
    repo = get_repo()
    cfg = effective_promo_config(repo, get_config().promo, env_forced=_env_forced())
    response = HTMLResponse("")
    csrf_token = _ensure_csrf(request, response)
    response.body = render(
        "promo_admin.html",
        cfg=cfg,
        targets=[(k, cfg.targets[k]) for k in TARGET_KEYS if k in cfg.targets],
        route_editions=ROUTE_EDITIONS,
        target_keys=TARGET_KEYS,
        env_forced=_env_forced(),
        performance=repo.get_promo_performance(),
        csrf_token=csrf_token,
        saved=request.query_params.get("saved") == "1",
    ).encode()
    response.headers["content-length"] = str(len(response.body))
    return response


@router.post("/save")
async def promo_admin_save(request: Request) -> Response:
    redirect = _require_admin(request)
    if redirect is not None:
        return redirect
    form = await request.form()
    repo = get_repo()

    # Start from the base config's structure so we never drop keys the form
    # doesn't render (utm_source/medium, etc.).
    data = get_config().promo.model_dump()
    data["enabled"] = form.get("enabled") == "on"
    data["track_clicks"] = form.get("track_clicks") == "on"
    pos = form.get("position", "bottom")
    data["position"] = pos if pos in ("top", "mid", "bottom") else "bottom"
    default_target = (form.get("default_target") or "edge").strip()
    data["default_target"] = default_target if default_target in TARGET_KEYS else "edge"

    routing = {}
    for ed in ROUTE_EDITIONS:
        val = (form.get(f"route_{ed}") or "").strip()
        if val in TARGET_KEYS:
            routing[ed] = val
    data["routing"] = routing

    targets = {}
    for k in TARGET_KEYS:
        targets[k] = {
            "label": (form.get(f"{k}_label") or "").strip(),
            "headline": (form.get(f"{k}_headline") or "").strip(),
            "body_html": (form.get(f"{k}_body") or "").strip(),
            "cta_text": (form.get(f"{k}_cta") or "").strip() or "Learn more",
            "url": (form.get(f"{k}_url") or "").strip(),
        }
    data["targets"] = targets

    override = {
        key: data[key]
        for key in ("enabled", "position", "track_clicks", "utm_source",
                    "utm_medium", "routing", "default_target", "targets")
    }
    repo.set_admin_setting(PROMO_SETTINGS_KEY, json.dumps(override))
    return RedirectResponse("/admin/promo/?saved=1", status_code=303)
