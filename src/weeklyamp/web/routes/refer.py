"""Public referral routes — landing page, dashboard, and leaderboard."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from weeklyamp.core.models import ReferralConfig
from weeklyamp.content.referrals import ReferralManager
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_referral_manager() -> ReferralManager:
    repo = get_repo()
    cfg = get_config()
    return ReferralManager(repo, cfg.referrals)


def _anonymize_email(email: str) -> str:
    """Anonymize an email: j***@gmail.com."""
    if not email or "@" not in email:
        return "***"
    local, domain = email.rsplit("@", 1)
    if len(local) <= 1:
        return f"*@{domain}"
    return f"{local[0]}***@{domain}"


def _get_reward_tiers(config: ReferralConfig) -> list[dict]:
    """Return reward tier definitions."""
    return [
        {"count": 3, "label": "3 Referrals", "reward": "Exclusive behind-the-scenes content"},
        {"count": 5, "label": "5 Referrals", "reward": "Early access to new features"},
        {"count": 10, "label": "10 Referrals", "reward": "TrueFans VIP badge + shout-out"},
        {"count": 25, "label": "25 Referrals", "reward": "TrueFans merch pack"},
        {"count": 50, "label": "50 Referrals", "reward": "Lifetime VIP membership"},
    ]


def _get_subscriber_count() -> int:
    """Get total active subscriber count for social proof."""
    repo = get_repo()
    conn = repo._conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM subscribers WHERE status = 'active'"
        ).fetchone()
        conn.close()
        return row["cnt"] if row else 0
    except Exception:
        conn.close()
        return 0


def _get_referrer_info(code: str) -> dict | None:
    """Look up referrer name/email by code."""
    repo = get_repo()
    conn = repo._conn()
    try:
        row = conn.execute(
            """SELECT s.first_name, s.email
               FROM referral_codes rc
               JOIN subscribers s ON rc.subscriber_id = s.id
               WHERE rc.code = ?""",
            (code,),
        ).fetchone()
        conn.close()
        if row:
            return dict(row)
        return None
    except Exception:
        conn.close()
        return None


def _get_subscriber_by_token(token: str) -> dict | None:
    """Look up subscriber by preference token (same pattern as preferences.py)."""
    repo = get_repo()
    conn = repo._conn()
    try:
        row = conn.execute(
            "SELECT * FROM subscribers WHERE preference_token = ? AND status = 'active'",
            (token,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        conn.close()
        return None


def _get_referral_log(referral_code_id: int) -> list[dict]:
    """Get list of referred emails for a referral code."""
    repo = get_repo()
    conn = repo._conn()
    try:
        rows = conn.execute(
            """SELECT referred_email, created_at
               FROM referral_log
               WHERE referral_code_id = ?
               ORDER BY created_at DESC""",
            (referral_code_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        conn.close()
        return []


def _get_referral_code_record(subscriber_id: int) -> dict | None:
    """Get the referral_codes row for a subscriber."""
    repo = get_repo()
    conn = repo._conn()
    try:
        row = conn.execute(
            "SELECT * FROM referral_codes WHERE subscriber_id = ? LIMIT 1",
            (subscriber_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        conn.close()
        return None


def _get_leaderboard_position(subscriber_id: int) -> int:
    """Get a subscriber's position on the referral leaderboard (1-based)."""
    repo = get_repo()
    conn = repo._conn()
    try:
        rows = conn.execute(
            "SELECT subscriber_id FROM referral_codes ORDER BY referral_count DESC"
        ).fetchall()
        conn.close()
        for i, row in enumerate(rows, 1):
            if row["subscriber_id"] == subscriber_id:
                return i
        return 0
    except Exception:
        conn.close()
        return 0


@router.get("/refer", response_class=HTMLResponse)
async def refer_landing(request: Request):
    """Referral landing page — shows who referred them + subscribe CTA."""
    code = request.query_params.get("code", "")
    cfg = get_config()

    referrer_info = None
    referrer_name = "A friend"
    if code:
        referrer_info = _get_referrer_info(code)
        if referrer_info and referrer_info.get("first_name"):
            referrer_name = referrer_info["first_name"]

    repo = get_repo()
    editions = repo.get_editions(active_only=True)
    subscriber_count = _get_subscriber_count()

    return render(
        "refer_landing.html",
        code=code,
        referrer_name=referrer_name,
        editions=editions,
        subscriber_count=subscriber_count,
        newsletter_name=cfg.newsletter.name,
        site_domain=cfg.site_domain,
    )


@router.get("/refer/dashboard/{token}", response_class=HTMLResponse)
async def refer_dashboard(token: str):
    """Subscriber's referral dashboard (token-based auth)."""
    subscriber = _get_subscriber_by_token(token)
    if not subscriber:
        return HTMLResponse(
            "<html><body style='font-family:Inter,sans-serif;max-width:600px;margin:60px auto;text-align:center'>"
            "<h2>Invalid or expired link</h2>"
            "<p>This referral dashboard link is no longer valid. Please use the link from your most recent email.</p>"
            "</body></html>",
            status_code=404,
        )

    cfg = get_config()
    mgr = _get_referral_manager()

    # Get or create referral code
    code = mgr.get_or_create_code(subscriber["id"])
    stats = mgr.get_referral_stats(subscriber["id"])
    referral_url = f"{cfg.site_domain.rstrip('/')}/refer?code={code}" if code else ""

    # Get referral code record for log lookup
    code_record = _get_referral_code_record(subscriber["id"])
    referral_log = []
    if code_record:
        referral_log = _get_referral_log(code_record["id"])

    # Anonymize emails in log
    for entry in referral_log:
        entry["anonymized_email"] = _anonymize_email(entry.get("referred_email", ""))

    leaderboard_position = _get_leaderboard_position(subscriber["id"])
    reward_tiers = _get_reward_tiers(cfg.referrals)

    return render(
        "refer_dashboard.html",
        subscriber=subscriber,
        code=code,
        referral_url=referral_url,
        stats=stats,
        referral_log=referral_log,
        leaderboard_position=leaderboard_position,
        reward_tiers=reward_tiers,
        newsletter_name=cfg.newsletter.name,
        site_domain=cfg.site_domain,
    )


@router.get("/refer/stats", response_class=HTMLResponse)
async def refer_leaderboard():
    """Public top referrers leaderboard (anonymized)."""
    cfg = get_config()
    mgr = _get_referral_manager()
    top_referrers = mgr.get_top_referrers(limit=20)

    # Anonymize emails
    for referrer in top_referrers:
        referrer["anonymized_email"] = _anonymize_email(referrer.get("email", ""))

    subscriber_count = _get_subscriber_count()

    return render(
        "refer_leaderboard.html",
        top_referrers=top_referrers,
        subscriber_count=subscriber_count,
        newsletter_name=cfg.newsletter.name,
        site_domain=cfg.site_domain,
    )
