"""AI-generated weekly admin report with KPIs."""

from __future__ import annotations

import logging
from datetime import datetime

from weeklyamp.core.models import AppConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


def generate_weekly_report(repo: Repository, config: AppConfig) -> str:
    """Generate an AI-powered weekly report summarizing platform performance.

    Returns HTML content of the report.
    """
    # Gather metrics
    subscriber_count = repo.get_subscriber_count()
    revenue = repo.get_revenue_summary()

    # Get recent issues
    recent_issues = repo.get_published_issues(limit=5)

    # Get growth trend
    growth = repo.get_growth_trend(days=7)

    # Build report sections
    report_date = datetime.now().strftime("%B %d, %Y")

    sections = []
    sections.append(f"<h2>Weekly Report &mdash; {report_date}</h2>")

    # Subscriber KPIs
    sections.append("<h3>Subscribers</h3>")
    sections.append(f"<p><strong>Total active subscribers:</strong> {subscriber_count:,}</p>")
    if growth:
        latest = growth[-1] if growth else {}
        sections.append(f"<p><strong>New this week:</strong> {latest.get('new_subscribers', 0):,}</p>")
        sections.append(f"<p><strong>Churned this week:</strong> {latest.get('churned_subscribers', 0):,}</p>")
        sections.append(f"<p><strong>Open rate:</strong> {latest.get('open_rate_avg', 0):.1f}%</p>")
        sections.append(f"<p><strong>Click rate:</strong> {latest.get('click_rate_avg', 0):.1f}%</p>")

    # Revenue KPIs
    sections.append("<h3>Revenue</h3>")
    sponsor = revenue.get("sponsor", {})
    tier = revenue.get("tier", {})
    sections.append(f"<p><strong>Sponsor revenue (paid):</strong> ${sponsor.get('paid_cents', 0) / 100:,.2f}</p>")
    sections.append(f"<p><strong>Sponsor pipeline:</strong> ${sponsor.get('pipeline_cents', 0) / 100:,.2f}</p>")
    sections.append(f"<p><strong>Tier MRR:</strong> ${tier.get('mrr_cents', 0) / 100:,.2f}</p>")

    # Recent issues
    sections.append("<h3>Recent Issues</h3>")
    if recent_issues:
        sections.append("<ul>")
        for issue in recent_issues:
            sections.append(
                f"<li>Issue #{issue.get('issue_number', '?')} &mdash; "
                f"{issue.get('edition_slug', 'unknown')} ({issue.get('status', '')})</li>"
            )
        sections.append("</ul>")
    else:
        sections.append("<p>No issues published yet.</p>")

    # AI Staff summary
    agents = repo.get_agents()
    tasks = repo.get_agent_tasks(state="complete")
    sections.append("<h3>AI Staff</h3>")
    sections.append(f"<p><strong>Active agents:</strong> {len(agents)}</p>")
    sections.append(f"<p><strong>Tasks completed:</strong> {len(tasks)}</p>")

    # Recommendations
    sections.append("<h3>Recommendations</h3>")
    sections.append("<ul>")
    if subscriber_count == 0:
        sections.append("<li>Import your first subscribers via CSV or the subscribe page</li>")
    if not recent_issues:
        sections.append("<li>Publish your first newsletter issue</li>")
    if sponsor.get("total_bookings", 0) == 0:
        sections.append("<li>Set up your first sponsor booking</li>")
    sections.append("<li>Check the Research page and fetch latest RSS content</li>")
    sections.append("<li>Review the AI Staff task queue for pending work</li>")
    sections.append("</ul>")

    return "\n".join(sections)
