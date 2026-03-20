"""Embeddable subscribe widget and badge generator.

Generates self-contained HTML snippets that partners can paste on their
websites to drive newsletter signups.
INACTIVE by default — used by admin embed code page.
"""

from __future__ import annotations

import html
import logging
import math
from typing import Optional

from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


def generate_embed_code(
    site_domain: str,
    edition_slug: str = "",
    style: str = "dark",
) -> str:
    """Generate an embeddable HTML/JS subscribe form snippet.

    Partners paste this on their website to drive signups.  The form
    posts directly to the newsletter's /subscribe endpoint.
    """
    domain = html.escape(site_domain.rstrip("/"))
    edition_val = html.escape(edition_slug)
    subscribe_url = f"{domain}/subscribe"

    if style == "light":
        bg = "#ffffff"
        text_color = "#111827"
        input_bg = "#f3f4f6"
        input_border = "#d1d5db"
        btn_bg = "#e8645a"
        btn_text = "#ffffff"
    else:
        bg = "#13131f"
        text_color = "#f0f0f5"
        input_bg = "#1e1e2e"
        input_border = "#2d2d3f"
        btn_bg = "#e8645a"
        btn_text = "#ffffff"

    edition_field = ""
    if edition_slug:
        edition_field = f'<input type="hidden" name="editions" value="{edition_val}">'

    return f"""<!-- TrueFans NEWSLETTERS Subscribe Widget -->
<div id="truefans-subscribe" style="max-width:400px;margin:0 auto;padding:24px;
     background:{bg};border-radius:12px;font-family:Arial,sans-serif;
     border:1px solid {input_border};">
  <div style="text-align:center;margin-bottom:16px;">
    <div style="font-size:18px;font-weight:700;color:{text_color};">
      Subscribe to TrueFans NEWSLETTERS
    </div>
    <div style="font-size:13px;color:#9ca3af;margin-top:4px;">
      Free music industry intelligence, 3x weekly
    </div>
  </div>
  <form action="{subscribe_url}" method="POST" target="_blank">
    {edition_field}
    <input type="email" name="email" placeholder="your@email.com" required
           style="width:100%;padding:10px 14px;margin-bottom:10px;
                  background:{input_bg};border:1px solid {input_border};
                  border-radius:6px;font-size:15px;color:{text_color};
                  box-sizing:border-box;">
    <button type="submit"
            style="width:100%;padding:10px 14px;background:{btn_bg};
                   color:{btn_text};border:none;border-radius:6px;
                   font-size:15px;font-weight:600;cursor:pointer;">
      Subscribe Free
    </button>
  </form>
  <div style="text-align:center;margin-top:10px;">
    <a href="{domain}" target="_blank"
       style="font-size:11px;color:#9ca3af;text-decoration:none;">
      Powered by TrueFans NEWSLETTERS
    </a>
  </div>
</div>
<!-- End TrueFans Widget -->"""


def generate_badge_html(
    site_domain: str,
    text: str = "Featured in TrueFans NEWSLETTERS",
) -> str:
    """Generate an "As Featured In" badge HTML snippet.

    Artists can embed this on their website to show they were featured
    in the newsletter.  Links to the newsletter landing page.
    """
    domain = html.escape(site_domain.rstrip("/"))
    safe_text = html.escape(text)

    return f"""<!-- TrueFans Featured Badge -->
<a href="{domain}" target="_blank" rel="noopener"
   style="display:inline-flex;align-items:center;gap:8px;padding:8px 16px;
          background:#13131f;color:#f0f0f5;text-decoration:none;
          border-radius:8px;font-family:Arial,sans-serif;font-size:13px;
          font-weight:600;border:1px solid rgba(255,255,255,0.1);">
  <span style="display:inline-block;width:8px;height:8px;
               background:#e8645a;border-radius:50%;"></span>
  {safe_text}
</a>
<!-- End TrueFans Badge -->"""


def generate_milestone_html(
    repo: Repository,
    config,  # AppConfig
) -> str:
    """Generate a public milestone progress bar HTML snippet.

    Shows current subscriber count (rounded to nearest 50), next milestone
    target, a progress bar, and a CTA.
    """
    # Get current subscriber count
    conn = repo._conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM subscribers WHERE status = 'active'"
        ).fetchone()
        total_subs = row["cnt"] if row else 0
    finally:
        conn.close()

    # Round to nearest 50 for public display
    display_count = int(math.ceil(total_subs / 50.0) * 50) if total_subs > 0 else 0

    # Get next milestone
    conn = repo._conn()
    try:
        row = conn.execute(
            """SELECT * FROM newsletter_milestones
               WHERE is_reached = 0
               ORDER BY target_subscribers ASC
               LIMIT 1"""
        ).fetchone()
        milestone = dict(row) if row else None
    finally:
        conn.close()

    if not milestone:
        # No milestones configured — use a sensible default
        target = max(display_count + 100, 500)
        milestone_title = f"{target} Subscribers"
        milestone_desc = ""
    else:
        target = milestone["target_subscribers"]
        milestone_title = milestone.get("title", f"{target} Subscribers")
        milestone_desc = milestone.get("description", "")

    # Calculate percentage
    pct = min(round(display_count / target * 100, 1), 100) if target > 0 else 0
    bar_width = max(pct, 2)  # minimum visible bar

    domain = html.escape(config.site_domain.rstrip("/"))

    return f"""<!-- TrueFans Milestone Progress -->
<div style="max-width:400px;margin:0 auto;padding:20px 24px;
            background:#13131f;border-radius:12px;font-family:Arial,sans-serif;
            border:1px solid rgba(255,255,255,0.08);">
  <div style="text-align:center;margin-bottom:12px;">
    <div style="font-size:11px;font-weight:700;text-transform:uppercase;
                letter-spacing:1px;color:#e8645a;">
      Community Goal
    </div>
    <div style="font-size:20px;font-weight:800;color:#f0f0f5;margin-top:4px;">
      {milestone_title}
    </div>
    {"<div style='font-size:13px;color:#9ca3af;margin-top:2px;'>" + html.escape(milestone_desc) + "</div>" if milestone_desc else ""}
  </div>
  <div style="background:#1e1e2e;border-radius:6px;height:12px;width:100%;
              overflow:hidden;margin-bottom:8px;">
    <div style="background:linear-gradient(90deg,#e8645a,#7c5cfc);
                border-radius:6px;height:12px;width:{bar_width}%;
                transition:width 0.5s;"></div>
  </div>
  <div style="display:flex;justify-content:space-between;font-size:13px;
              color:#9ca3af;margin-bottom:12px;">
    <span>{display_count}+ subscribers</span>
    <span>{pct}%</span>
  </div>
  <div style="text-align:center;">
    <a href="{domain}/subscribe" target="_blank"
       style="display:inline-block;padding:8px 20px;background:#e8645a;
              color:#ffffff;text-decoration:none;border-radius:6px;
              font-size:14px;font-weight:600;">
      Help us reach {target}!
    </a>
  </div>
</div>
<!-- End TrueFans Milestone -->"""
