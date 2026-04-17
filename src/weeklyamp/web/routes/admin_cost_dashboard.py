"""Admin cost dashboard — per-edition LLM + infra + delivery cost.

Thin wrapper around :mod:`weeklyamp.core.cost_model` so the dashboard
and the Revenue Dashboard's P&L view share a single source of truth
for pricing and computation.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from weeklyamp.core.cost_model import issues_per_month, per_edition_costs, pricing
from weeklyamp.web.deps import get_config, get_repo, render
from weeklyamp.web.security import is_authenticated

router = APIRouter()


def _require_admin(request: Request) -> Response | None:
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)
    return None


@router.get("/cost-dashboard", response_class=HTMLResponse)
async def cost_dashboard(request: Request) -> Response:
    redirect = _require_admin(request)
    if redirect is not None:
        return redirect

    config = get_config()
    rows = per_edition_costs(get_repo(), config)
    return HTMLResponse(render(
        "admin_cost_dashboard.html",
        rows=rows,
        pricing=pricing(),
        issues_per_month=issues_per_month(config),
        window_days=30,
    ))
