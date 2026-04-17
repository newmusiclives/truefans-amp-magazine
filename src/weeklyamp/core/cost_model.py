"""Shared cost model — used by both /admin/cost-dashboard and the
Revenue Dashboard so the P&L view and the per-edition view always
agree on the numbers.

Unit costs are env-overridable; defaults match the cost-tracking memory
as of 2026-04-17 (Claude Sonnet 4.5 list prices, GHL/Mailgun $0.80/1k
delivery, Railway+Postgres $25/mo combined).
"""

from __future__ import annotations

import os


# Baseline modeled LLM cost per edition when we have no telemetry yet.
# Structurally ~$0.42 per 15-section edition at list prices.
MODELED_LLM_PER_ISSUE = 0.42

CANONICAL_EDITIONS: tuple[str, ...] = ("fan", "artist", "industry")


def pricing() -> dict[str, float]:
    """Return current pricing assumptions.

    Re-read every call so env-var changes take effect without a
    restart — keeps this safe to call from multiple request handlers.
    """
    return {
        # Claude Sonnet 4.5 list prices ($/million → $/1k).
        # Blended assumes a 30/70 input/output split for generation.
        "input_per_1k": float(os.environ.get("WEEKLYAMP_COST_INPUT_PER_1K", "0.003")),
        "output_per_1k": float(os.environ.get("WEEKLYAMP_COST_OUTPUT_PER_1K", "0.015")),
        "blended_per_1k": float(os.environ.get("WEEKLYAMP_COST_BLENDED_PER_1K", "0.0114")),
        "email_per_1k": float(os.environ.get("WEEKLYAMP_COST_EMAIL_PER_1K", "0.80")),
        "hosting_monthly": float(os.environ.get("WEEKLYAMP_COST_HOSTING_MONTHLY", "20.00")),
        "db_monthly": float(os.environ.get("WEEKLYAMP_COST_DB_MONTHLY", "5.00")),
    }


def issues_per_month(config) -> int:
    """Estimate issues-per-month from schedule × canonical edition count."""
    editions = len(CANONICAL_EDITIONS)
    sends_per_week = max(1, len(getattr(config.schedule, "send_days", []) or []))
    return max(1, editions * sends_per_week * 4)


def per_edition_costs(repo, config) -> list[dict]:
    """Per-edition cost rows used by /admin/cost-dashboard.

    Fails defensively — if the repo query raises (e.g. schema drift),
    returns all-modeled rows rather than 500ing the caller.
    """
    p = pricing()
    try:
        stats = repo.get_cost_stats_by_edition(since_days=30)
        sub_counts = repo.get_subscriber_counts_by_edition()
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "per_edition_costs: telemetry query failed; falling back to modeled"
        )
        stats = []
        sub_counts = {}

    measured = {s["edition_slug"]: s for s in stats}
    infra_per_issue = (p["hosting_monthly"] + p["db_monthly"]) / issues_per_month(config)

    rows: list[dict] = []
    for slug in CANONICAL_EDITIONS:
        m = measured.get(slug)
        if m and m.get("avg_tokens_per_issue", 0) > 0:
            llm_cost = m["avg_tokens_per_issue"] / 1000.0 * p["blended_per_1k"]
            source = "measured"
            issue_count = m["issue_count"]
            avg_tokens = m["avg_tokens_per_issue"]
        else:
            llm_cost = MODELED_LLM_PER_ISSUE
            source = "modeled"
            issue_count = m["issue_count"] if m else 0
            avg_tokens = 0
        subs = int(sub_counts.get(slug, 0) or 0)
        email_cost = subs / 1000.0 * p["email_per_1k"]
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
            "total": llm_cost + infra_per_issue + email_cost,
        })
    return rows


def monthly_cost_estimate(repo, config) -> dict[str, float]:
    """Project the monthly cost of production + delivery.

    Composed as:
      llm_monthly     = issues_per_month × avg_llm_cost_per_edition
                        (measured when we have data, modeled otherwise)
      infra_monthly   = hosting_monthly + db_monthly (flat, not amortized)
      email_monthly   = issues_per_month × total_active_subs × $0.80/1k
      total_monthly   = llm + infra + email

    All values returned in DOLLARS (float), keyed so the Revenue
    Dashboard can subtract them from revenue to compute net.
    """
    p = pricing()
    per_edition = per_edition_costs(repo, config)
    ipm = issues_per_month(config)

    # Average per-edition LLM cost — weight each edition equally since
    # our current schedule has the same frequency for all three.
    avg_llm_per_edition = (
        sum(r["llm_cost"] for r in per_edition) / len(per_edition)
        if per_edition else MODELED_LLM_PER_ISSUE
    )

    # Sum active subscribers across editions (a subscriber to two
    # editions is counted twice because they receive two sends).
    total_subscribers_reach = sum(r["subscribers"] for r in per_edition)

    llm_monthly = ipm * avg_llm_per_edition
    infra_monthly = p["hosting_monthly"] + p["db_monthly"]
    # Email: issues_per_month already = 3 editions × sends_per_week × 4
    # weeks, so multiplying by per-edition subscribers is wrong —
    # total_subscribers_reach is per-send, and issues_per_month is the
    # total sends across all editions. So: sends × avg_subs_per_send.
    avg_subs_per_send = (
        total_subscribers_reach / len(per_edition) if per_edition else 0
    )
    email_monthly = ipm * avg_subs_per_send / 1000.0 * p["email_per_1k"]

    total_monthly = llm_monthly + infra_monthly + email_monthly
    return {
        "llm_monthly": round(llm_monthly, 2),
        "infra_monthly": round(infra_monthly, 2),
        "email_monthly": round(email_monthly, 2),
        "total_monthly": round(total_monthly, 2),
        "issues_per_month": ipm,
        "total_subscribers_reach": total_subscribers_reach,
    }
