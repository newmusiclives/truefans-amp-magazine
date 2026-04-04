"""Marketing & Promotion hub — subscriber growth and sponsor sales tools."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()

CAMPAIGN_TYPES = [
    ("subscriber_growth", "Subscriber Growth"),
    ("sponsor_outreach", "Sponsor Outreach"),
    ("retention", "Retention / Win-back"),
    ("reactivation", "Reactivation"),
    ("upsell", "Upsell to Paid Tier"),
    ("event", "Event / Launch"),
]

CHANNELS = [
    ("email", "Email"),
    ("sms", "SMS / Text"),
    ("voice", "Voice Call"),
    ("ai_agent", "AI Agent"),
    ("social", "Social Media"),
    ("multi", "Multi-Channel"),
]

PROSPECT_STATUSES = [
    "identified", "researching", "contacted", "meeting",
    "proposal", "negotiating", "closed_won", "closed_lost",
]


@router.get("/", response_class=HTMLResponse)
async def marketing_hub(request: Request):
    repo = get_repo()
    config = get_config()
    stats = repo.get_outreach_stats()
    campaigns = repo.get_marketing_campaigns(limit=10)
    prospects = repo.get_sponsor_prospects(limit=10)
    templates = repo.get_marketing_templates()
    subscriber_count = repo.get_subscriber_count()
    return HTMLResponse(render("marketing.html",
        stats=stats, campaigns=campaigns, prospects=prospects,
        templates=templates, subscriber_count=subscriber_count,
        campaign_types=CAMPAIGN_TYPES, channels=CHANNELS,
        prospect_statuses=PROSPECT_STATUSES, config=config))


@router.get("/campaigns", response_class=HTMLResponse)
async def campaigns_page(request: Request):
    repo = get_repo()
    campaigns = repo.get_marketing_campaigns(limit=50)
    return HTMLResponse(render("marketing_campaigns.html",
        campaigns=campaigns, campaign_types=CAMPAIGN_TYPES, channels=CHANNELS))


@router.post("/campaigns/create", response_class=HTMLResponse)
async def create_campaign(
    request: Request,
    name: str = Form(...),
    campaign_type: str = Form(...),
    channel: str = Form("email"),
    target_audience: str = Form(""),
    goal_description: str = Form(""),
    goal_target: int = Form(0),
    template_content: str = Form(""),
    notes: str = Form(""),
):
    repo = get_repo()
    campaign_id = repo.create_marketing_campaign(
        name, campaign_type, channel, target_audience,
        goal_description, goal_target, template_content, notes,
    )
    return HTMLResponse(f'<div class="alert alert-success">Campaign "{name}" created (ID: {campaign_id}).</div>')


@router.post("/campaigns/{campaign_id}/status", response_class=HTMLResponse)
async def update_campaign_status(campaign_id: int, request: Request, status: str = Form(...)):
    repo = get_repo()
    repo.update_campaign_status(campaign_id, status)
    return HTMLResponse(f'<span class="badge badge-info">{status}</span>')


@router.get("/prospects", response_class=HTMLResponse)
async def prospects_page(request: Request):
    repo = get_repo()
    prospects = repo.get_sponsor_prospects(limit=100)
    return HTMLResponse(render("marketing_prospects.html",
        prospects=prospects, prospect_statuses=PROSPECT_STATUSES))


@router.post("/prospects/create", response_class=HTMLResponse)
async def create_prospect(
    request: Request,
    company_name: str = Form(...),
    contact_name: str = Form(""),
    contact_email: str = Form(""),
    contact_phone: str = Form(""),
    website: str = Form(""),
    category: str = Form("general"),
    target_editions: str = Form(""),
    estimated_budget: str = Form(""),
    notes: str = Form(""),
):
    repo = get_repo()
    repo.create_sponsor_prospect(
        company_name, contact_name, contact_email, contact_phone,
        website, category, target_editions, estimated_budget, notes=notes,
    )
    return HTMLResponse(f'<div class="alert alert-success">Prospect "{company_name}" added to pipeline.</div>')


@router.post("/prospects/{prospect_id}/status", response_class=HTMLResponse)
async def update_prospect_status(prospect_id: int, request: Request, status: str = Form(...)):
    repo = get_repo()
    repo.update_prospect_status(prospect_id, status)
    return HTMLResponse(f'<span class="badge badge-info">{status}</span>')


@router.get("/templates", response_class=HTMLResponse)
async def templates_page(request: Request):
    repo = get_repo()
    templates = repo.get_marketing_templates()
    by_category = {}
    for t in templates:
        by_category.setdefault(t.get("category", "general"), []).append(t)
    return HTMLResponse(render("marketing_templates.html", by_category=by_category))


@router.get("/templates/{template_id}", response_class=HTMLResponse)
async def template_detail(template_id: int, request: Request):
    repo = get_repo()
    template = repo.get_marketing_template(template_id)
    if not template:
        return HTMLResponse("Template not found", status_code=404)
    return HTMLResponse(render("marketing_template_detail.html", template=template))


@router.get("/ghl", response_class=HTMLResponse)
async def ghl_integration(request: Request):
    repo = get_repo()
    config = get_config()
    return HTMLResponse(render("marketing_ghl.html", config=config))


# ── Automation ──

@router.get("/automation", response_class=HTMLResponse)
async def automation_page(request: Request):
    repo = get_repo()
    config = get_config()
    autonomous = config.agents.default_autonomy == "autonomous"
    agent_row = repo.get_agent_by_type("marketing")
    tasks = []
    if agent_row:
        tasks = repo.get_agent_tasks(agent_id=agent_row["id"], limit=20)
    return HTMLResponse(render("marketing_automation.html",
        autonomous=autonomous, tasks=tasks, config=config))


def _run_marketing_task(task_type: str):
    """Helper to run a marketing agent task and return HTML result."""
    import json as _json
    repo = get_repo()
    config = get_config()
    from weeklyamp.agents.marketing import MarketingAgent
    agent_row = repo.get_agent_by_type("marketing")
    if not agent_row:
        return '<div class="alert alert-warning">Marketing agent not found. Restart server to seed agents.</div>', {}
    agent = MarketingAgent(repo, config, agent_row)
    task_id = repo.create_agent_task(agent_row["id"], task_type)
    agent.execute(task_id)
    task = repo.get_task(task_id)
    output = _json.loads(task.get("output_json", "{}")) if task else {}
    return None, output


@router.post("/automation/prospect-scan", response_class=HTMLResponse)
async def trigger_prospect_scan(request: Request):
    err, output = _run_marketing_task("identify_prospects")
    if err:
        return HTMLResponse(err)
    return HTMLResponse(f'<div class="alert alert-success">Prospect scan complete. {output.get("count", 0)} prospects identified.</div>')


@router.post("/automation/outreach", response_class=HTMLResponse)
async def trigger_outreach(request: Request):
    err, output = _run_marketing_task("draft_outreach_batch")
    if err:
        return HTMLResponse(err)
    return HTMLResponse(f'<div class="alert alert-success">Outreach drafted for {output.get("drafted", 0)} prospects.</div>')


@router.post("/automation/growth-tactics", response_class=HTMLResponse)
async def trigger_growth_tactics(request: Request):
    err, output = _run_marketing_task("generate_growth_tactics")
    if err:
        return HTMLResponse(err)
    tactics = output.get("tactics", "No tactics generated")
    return HTMLResponse(f'<div class="card" style="margin-top:12px"><h4>Growth Tactics</h4><div style="white-space:pre-wrap;font-size:14px;line-height:1.7">{tactics}</div></div>')


@router.post("/automation/social-batch", response_class=HTMLResponse)
async def trigger_social_batch(request: Request):
    err, output = _run_marketing_task("draft_social_batch")
    if err:
        return HTMLResponse(err)
    return HTMLResponse(f'<div class="alert alert-success">{output.get("drafted", 0)} social posts drafted.</div>')


@router.post("/automation/retention-check", response_class=HTMLResponse)
async def trigger_retention(request: Request):
    err, output = _run_marketing_task("identify_at_risk")
    if err:
        return HTMLResponse(err)
    err2, output2 = _run_marketing_task("draft_winback_batch")
    recipients = output2.get("recipients", 0) if not err2 else 0
    return HTMLResponse(f'<div class="alert alert-success">Retention check complete. {output.get("at_risk_count", 0)} at-risk found, {recipients} win-back emails queued.</div>')


@router.post("/automation/weekly-report", response_class=HTMLResponse)
async def trigger_weekly_report(request: Request):
    err, output = _run_marketing_task("weekly_marketing_report")
    if err:
        return HTMLResponse(err)
    report = output.get("report", "No report generated")
    return HTMLResponse(f'<div class="card" style="margin-top:12px"><h4>Marketing Report</h4><div style="white-space:pre-wrap;font-size:14px;line-height:1.7">{report}</div></div>')
