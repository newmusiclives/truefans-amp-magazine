"""Tier access middleware — gates premium content by subscriber tier."""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, Request

from weeklyamp.billing.stripe_client import check_tier_access
from weeklyamp.web.deps import get_config, get_repo


def require_tier(required_tier: str = "free"):
    """FastAPI dependency that checks subscriber tier access.

    Usage in routes:
        @router.get("/premium-content", dependencies=[Depends(require_tier("pro"))])
        async def premium_content(request: Request): ...
    """

    async def _check(request: Request):
        config = get_config()
        if not config.paid_tiers.enabled:
            return  # tiers not active — allow all access

        subscriber_id = _get_subscriber_id(request)
        if not subscriber_id:
            if required_tier == "free":
                return
            raise HTTPException(status_code=401, detail="Login required for premium content")

        repo = get_repo()
        billing = repo.get_billing_for_subscriber(subscriber_id)
        if not check_tier_access(billing, required_tier):
            tier_name = required_tier.capitalize()
            raise HTTPException(
                status_code=403,
                detail=f"{tier_name} subscription required to access this content",
            )

    return _check


def _get_subscriber_id(request: Request) -> Optional[int]:
    """Extract subscriber ID from session or auth token."""
    session = getattr(request.state, "session", None) or {}
    sub_id = session.get("subscriber_id")
    if sub_id:
        return int(sub_id)
    # Check bearer token for API access
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        repo = get_repo()
        sub = repo.get_subscriber_by_token(token)
        if sub:
            return sub["id"]
    return None
