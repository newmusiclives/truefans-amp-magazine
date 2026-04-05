"""Advanced analytics routes — NPS, reports, forecasting, media kit."""
from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def analytics_hub(request: Request):
    repo = get_repo()
    config = get_config()
    from weeklyamp.content.analytics_tools import calculate_nps, generate_content_report, forecast_revenue
    nps = calculate_nps(repo)
    content_report = generate_content_report(repo)
    forecasts = forecast_revenue(repo, months=12)
    return HTMLResponse(render("analytics_hub.html",
        nps=nps, content_report=content_report, forecasts=forecasts, config=config))

@router.get("/media-kit", response_class=HTMLResponse)
async def media_kit_download(request: Request):
    repo = get_repo()
    config = get_config()
    from weeklyamp.content.analytics_tools import generate_media_kit_text
    kit_text = generate_media_kit_text(repo, config)
    subscriber_count = repo.get_subscriber_count()
    summary = repo.get_revenue_summary()

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>TrueFans NEWSLETTERS — Media Kit</title>
<style>
body {{ font-family: 'Inter', -apple-system, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 24px; color: #1a1a2e; line-height: 1.7; }}
h1 {{ color: #e8645a; font-size: 28px; border-bottom: 3px solid #e8645a; padding-bottom: 12px; }}
h2 {{ color: #1a1a2e; font-size: 20px; margin-top: 32px; }}
.stat-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 24px 0; }}
.stat-box {{ background: #f8f9fa; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px; text-align: center; }}
.stat-box .number {{ font-size: 32px; font-weight: 900; color: #e8645a; }}
.stat-box .label {{ font-size: 13px; color: #6b7280; margin-top: 4px; }}
table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #e5e7eb; font-size: 14px; }}
th {{ background: #f8f9fa; font-weight: 600; }}
.footer {{ margin-top: 40px; padding-top: 20px; border-top: 2px solid #e5e7eb; font-size: 13px; color: #6b7280; }}
</style></head><body>
<h1>TrueFans NEWSLETTERS — Media Kit</h1>
<p><strong>{config.newsletter.name}</strong> — {config.newsletter.tagline}</p>

<div class="stat-grid">
<div class="stat-box"><div class="number">{subscriber_count:,}</div><div class="label">Total Subscribers</div></div>
<div class="stat-box"><div class="number">3</div><div class="label">Newsletter Editions</div></div>
<div class="stat-box"><div class="number">9</div><div class="label">Issues per Week</div></div>
</div>

<h2>Our Editions</h2>
<table>
<tr><th>Edition</th><th>Audience</th><th>Content Focus</th></tr>
<tr><td><strong>Fan Edition</strong></td><td>Music fans, concert-goers</td><td>Artist spotlights, new releases, playlists, trivia, live music</td></tr>
<tr><td><strong>Artist Edition</strong></td><td>Independent musicians, songwriters</td><td>Career strategy, marketing, production, industry intelligence</td></tr>
<tr><td><strong>Industry Edition</strong></td><td>Labels, managers, publishers, distributors</td><td>Market analysis, deal flow, streaming data, business strategy</td></tr>
</table>

<h2>Sponsor Rates</h2>
<table>
<tr><th>Position</th><th>CPM</th><th>Per Issue (1K subs)</th><th>Notes</th></tr>
<tr><td>Top Banner</td><td>$45</td><td>$45</td><td>Premium placement, highest visibility</td></tr>
<tr><td>Mid-Content</td><td>$30</td><td>$30</td><td>Embedded between sections</td></tr>
<tr><td>Bottom</td><td>$21</td><td>$21</td><td>End-of-newsletter placement</td></tr>
</table>
<p><em>Volume discounts: 10% off weekly bookings, 20% off monthly commitments.</em></p>

<h2>Audience Demographics</h2>
<table>
<tr><th>Metric</th><th>Value</th></tr>
<tr><td>Primary Age Range</td><td>25-45</td></tr>
<tr><td>Music Industry Professionals</td><td>~35%</td></tr>
<tr><td>Independent Artists</td><td>~40%</td></tr>
<tr><td>Music Fans / Enthusiasts</td><td>~25%</td></tr>
<tr><td>Geographic Focus</td><td>US (65%), UK (12%), Canada (8%), Other (15%)</td></tr>
</table>

<h2>Why Advertise With Us</h2>
<ul>
<li>Highly engaged, niche audience — music professionals and passionate fans</li>
<li>3x weekly touchpoints across 3 targeted editions</li>
<li>AI-powered content ensures consistent quality and engagement</li>
<li>Full open/click tracking and reporting</li>
<li>Sponsor creative support available</li>
</ul>

<h2>Contact</h2>
<p>Email: <strong>sponsors@truefansnewsletters.com</strong><br>
Website: <strong>{config.site_domain}</strong></p>

<div class="footer">
<p>Generated on {__import__('datetime').datetime.utcnow().strftime('%B %d, %Y')} | {config.newsletter.name}</p>
</div>
</body></html>"""

    return HTMLResponse(html)
