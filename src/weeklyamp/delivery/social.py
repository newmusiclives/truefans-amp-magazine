"""Social media posting via platform APIs.

Supports Twitter/X and LinkedIn. Each platform requires API credentials
set in environment variables. Posts are queued in social_posts table
and published via this module.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def post_to_twitter(content: str) -> Optional[str]:
    """Post to Twitter/X. Returns tweet URL or None on failure.

    Requires env vars: TWITTER_API_KEY, TWITTER_API_SECRET,
    TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
    """
    api_key = os.environ.get("TWITTER_API_KEY", "")
    if not api_key:
        logger.info("Twitter API not configured — skipping")
        return None
    try:
        import httpx
        # Twitter API v2 tweet endpoint
        response = httpx.post(
            "https://api.twitter.com/2/tweets",
            headers={"Authorization": f"Bearer {os.environ.get('TWITTER_BEARER_TOKEN', '')}"},
            json={"text": content[:280]},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        tweet_id = data.get("data", {}).get("id", "")
        return f"https://twitter.com/i/status/{tweet_id}" if tweet_id else None
    except Exception:
        logger.exception("Twitter post failed")
        return None


def post_to_linkedin(content: str) -> Optional[str]:
    """Post to LinkedIn. Returns post URL or None on failure.

    Requires env vars: LINKEDIN_ACCESS_TOKEN, LINKEDIN_PERSON_URN
    """
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
    person_urn = os.environ.get("LINKEDIN_PERSON_URN", "")
    if not token or not person_urn:
        logger.info("LinkedIn API not configured — skipping")
        return None
    try:
        import httpx
        response = httpx.post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Restli-Protocol-Version": "2.0.0",
            },
            json={
                "author": person_urn,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": content},
                        "shareMediaCategory": "NONE",
                    }
                },
                "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
            },
            timeout=30,
        )
        response.raise_for_status()
        return "https://linkedin.com"  # LinkedIn doesn't return direct URL easily
    except Exception:
        logger.exception("LinkedIn post failed")
        return None


def publish_social_post(repo, post_id: int) -> dict:
    """Publish a single social post from the queue.

    Updates post status to 'posted' or 'failed'.
    Returns result dict with status and url.
    """
    conn = repo._conn()
    row = conn.execute("SELECT * FROM social_posts WHERE id = ?", (post_id,)).fetchone()
    conn.close()

    if not row:
        return {"status": "error", "message": "Post not found"}

    post = dict(row)
    platform = post.get("platform", "")
    content = post.get("content", "")

    url = None
    if platform in ("twitter", "x"):
        url = post_to_twitter(content)
    elif platform == "linkedin":
        url = post_to_linkedin(content)
    else:
        logger.info("Platform %s not supported for auto-posting", platform)
        return {"status": "skipped", "message": f"Platform {platform} not supported"}

    if url:
        repo.update_social_post(post_id, status="posted", posted_at="CURRENT_TIMESTAMP")
        return {"status": "posted", "url": url}
    else:
        repo.update_social_post(post_id, status="failed")
        return {"status": "failed", "message": "API call failed"}


def publish_all_pending(repo) -> dict:
    """Publish all scheduled social posts that are due."""
    posts = repo.get_social_posts(status="scheduled")
    results = {"posted": 0, "failed": 0, "skipped": 0}
    for post in posts:
        result = publish_social_post(repo, post["id"])
        results[result.get("status", "failed")] = results.get(result.get("status", "failed"), 0) + 1
    return results
