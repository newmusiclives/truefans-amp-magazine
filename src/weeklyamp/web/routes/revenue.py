"""Revenue dashboard — unified view of all revenue streams."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from weeklyamp.core.cost_model import monthly_cost_estimate
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def revenue_dashboard(request: Request):
    repo = get_repo()
    config = get_config()
    summary = repo.get_revenue_summary()
    by_edition = repo.get_revenue_by_edition()
    tier_breakdown = repo.get_tier_breakdown()
    subscriber_count = repo.get_subscriber_count()

    # P&L view — pull costs from the shared cost model so Revenue and
    # Cost dashboards are always reconciled. All values in dollars.
    costs = monthly_cost_estimate(repo, config)
    # Monthly revenue estimate: tier MRR is already monthly; sponsor
    # paid_cents is cumulative, so we approximate monthly sponsor
    # contribution by taking the last 30 days of paid bookings (the
    # summary already tracks pipeline vs paid — we use paid as the
    # floor). Affiliate revenue is likewise shown as cumulative.
    monthly_revenue_dollars = (summary["tier"]["mrr_cents"] or 0) / 100.0
    total_revenue_dollars = (
        summary["sponsor"]["paid_cents"]
        + summary["affiliate"]["total_revenue"]
        + summary["tier"]["mrr_cents"]
    ) / 100.0
    net_monthly_dollars = round(monthly_revenue_dollars - costs["total_monthly"], 2)

    return HTMLResponse(render("revenue_dashboard.html",
        summary=summary, by_edition=by_edition,
        tier_breakdown=tier_breakdown, subscriber_count=subscriber_count,
        costs=costs,
        monthly_revenue_dollars=round(monthly_revenue_dollars, 2),
        total_revenue_dollars=round(total_revenue_dollars, 2),
        net_monthly_dollars=net_monthly_dollars,
    ))


@router.get("/licensees")
async def licensees_dashboard(request: Request):
    """Licensee MRR / churn / past-due dashboard.

    JSON response with: total active licensees, MRR (sum of monthly fees
    in cents and dollars), past-due count, recently activated, and the
    full per-licensee table sorted by status then revenue.
    """
    repo = get_repo()
    licensees = repo.get_licensees()

    by_status: dict[str, int] = {}
    mrr_cents = 0
    past_due: list[dict] = []
    recently_activated: list[dict] = []

    cutoff_30d = datetime.utcnow() - timedelta(days=30)

    for lic in licensees:
        status = (lic.get("status") or "").lower()
        by_status[status] = by_status.get(status, 0) + 1

        if status == "active":
            fee = int(lic.get("license_fee_cents") or 0)
            interval = (lic.get("license_type") or "monthly").lower()
            # Normalise yearly licenses to monthly contribution to MRR
            if interval == "yearly":
                fee = fee // 12
            mrr_cents += fee

        if status == "past_due":
            past_due.append({
                "id": lic.get("id"),
                "company": lic.get("company_name"),
                "email": lic.get("email"),
                "city": lic.get("city_market_slug"),
            })

        activated = lic.get("activated_at")
        if activated:
            try:
                ts = (
                    datetime.fromisoformat(activated[:19])
                    if isinstance(activated, str)
                    else activated
                )
                if ts >= cutoff_30d:
                    recently_activated.append({
                        "id": lic.get("id"),
                        "company": lic.get("company_name"),
                        "city": lic.get("city_market_slug"),
                        "activated_at": str(activated),
                    })
            except Exception:
                pass

    # Sort the per-licensee table: active first, then highest fee
    licensees_sorted = sorted(
        licensees,
        key=lambda l: (
            0 if (l.get("status") or "").lower() == "active" else 1,
            -int(l.get("license_fee_cents") or 0),
        ),
    )

    return JSONResponse({
        "total_licensees": len(licensees),
        "by_status": by_status,
        "mrr": {
            "cents": mrr_cents,
            "dollars": round(mrr_cents / 100, 2),
        },
        "annualised_run_rate_dollars": round(mrr_cents * 12 / 100, 2),
        "past_due_count": len(past_due),
        "past_due": past_due,
        "recently_activated_30d": recently_activated,
        "licensees": [
            {
                "id": l.get("id"),
                "company": l.get("company_name"),
                "city": l.get("city_market_slug"),
                "editions": l.get("edition_slugs"),
                "status": l.get("status"),
                "type": l.get("license_type"),
                "fee_cents": l.get("license_fee_cents"),
                "revenue_share_pct": l.get("revenue_share_pct"),
            }
            for l in licensees_sorted
        ],
    })
