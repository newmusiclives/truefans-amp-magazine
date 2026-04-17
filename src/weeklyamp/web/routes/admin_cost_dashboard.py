"""Admin cost dashboard — per-edition LLM + infra + delivery cost.

Reads measured token usage from agent_output_log (wired via the
generate_draft_with_usage path) and active subscriber counts per
edition. Falls back to modeled defaults when no real runs exist yet
so the dashboard is useful on day 1, not just after the first issues
have been produced.

Unit costs are hardcoded with env-var overrides so they can be
retuned without a code deploy when the real GHL rate or Anthropic
pricing changes. Defaults match the cost-tracking memory as of
2026-04-17.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from weeklyamp.web.deps import get_config, get_repo, render
from weeklyamp.web.security import is_authenticated

router = APIRouter()


# Unit cost defaults. All overridable via env so an operator can pin
# rates to actual bills once they exist.
def _pricing() -> dict:
    return {
        # Claude Sonnet 4.5 list prices ($/million → $/1k).
        # Blended rate assumes a 30/70 input/output split (typical for
        # generation workloads): 0.3*$0.003 + 0.7*$0.015 ≈ $0.0114/1k.
        "input_per_1k": float(os.environ.get("WEEKLYAMP_COST_INPUT_PER_1K", "0.003")),
        "output_per_1k": float(os.environ.get("WEEKLYAMP_COST_OUTPUT_PER_1K", "0.015")),
        "blended_per_1k": float(os.environ.get("WEEKLYAMP_COST_BLENDED_PER_1K", "0.0114")),
        # GHL/Mailgun per 1,000 deliveries.
        "email_per_1k": float(os.environ.get("WEEKLYAMP_COST_EMAIL_PER_1K", "0.80")),
        # Railway + Postgres amortized monthly spend, used to compute
        # per-issue infra share given the monthly issue count.
        "hosting_monthly": float(os.environ.get("WEEKLYAMP_COST_HOSTING_MONTHLY", "20.00")),
        "db_monthly": float(os.environ.get("WEEKLYAMP_COST_DB_MONTHLY", "5.00")),
    }


# Baseline modeled LLM cost per edition when we have no telemetry yet
# (pre-launch, or for editions that haven't published an issue in the
# window). Structurally ~$0.42 per 15-section edition at list prices.
_MODELED_LLM_PER_ISSUE = 0.42


def _issues_per_month(config) -> int:
    """Estimate issues-per-month from schedule × edition count.

    Used to amortize hosting. Falls back to 39 (the memory estimate)
    if config parsing yields zero.
    """
    editions = 3  # fan / artist / industry (the three seeded editions)
    sends_per_week = max(1, len(getattr(config.schedule, "send_days", []) or []))
    return max(1, editions * sends_per_week * 4) or 39


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
    repo = get_repo()
    pricing = _pricing()

    # Window: last 30 days of runs — aligns with the agent_output_log
    # retention we expect in a live system.
    stats = repo.get_cost_stats_by_edition(since_days=30)
    sub_counts = repo.get_subscriber_counts_by_edition()
    measured_by_slug = {s["edition_slug"]: s for s in stats}

    # Monthly infra amortization: split Railway + Postgres across the
    # projected issues-per-month.
    infra_per_issue = (pricing["hosting_monthly"] + pricing["db_monthly"]) / _issues_per_month(config)

    rows = []
    # Always show the 3 canonical editions even if one has no data.
    for slug in ("fan", "artist", "industry"):
        m = measured_by_slug.get(slug)
        if m and m["avg_tokens_per_issue"] > 0:
            llm_cost = m["avg_tokens_per_issue"] / 1000.0 * pricing["blended_per_1k"]
            source = "measured"
            issue_count = m["issue_count"]
            avg_tokens = m["avg_tokens_per_issue"]
        else:
            llm_cost = _MODELED_LLM_PER_ISSUE
            source = "modeled"
            issue_count = m["issue_count"] if m else 0
            avg_tokens = 0
        subs = sub_counts.get(slug, 0)
        email_cost = subs / 1000.0 * pricing["email_per_1k"]
        total = llm_cost + infra_per_issue + email_cost
        rows.append({
            "slug": slug,
            "label": slug.capitalize(),
            "source": source,
            "issue_count": issue_count,
            "avg_tokens": avg_tokens,
            "llm_cost": llm_cost,
            "infra_cost": infra_per_issue,
            "subscribers": subs,
            "email_cost": email_cost,
            "total": total,
        })

    return HTMLResponse(render(
        "admin_cost_dashboard.html",
        rows=rows,
        pricing=pricing,
        issues_per_month=_issues_per_month(config),
        window_days=30,
    ))
