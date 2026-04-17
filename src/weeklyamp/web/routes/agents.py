"""AI Staff routes — agent management and task control."""

from __future__ import annotations

import json

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from weeklyamp.agents.orchestrator import AgentOrchestrator
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


EDITION_LABELS = {
    "fan": "Fan Edition",
    "artist": "Artist Edition",
    "industry": "Industry Edition",
}

EDITION_COLORS = {
    "fan": "#e8645a",
    "artist": "#7c5cfc",
    "industry": "#f59e0b",
}

EDITION_ICONS = {
    "fan": "&#127911;",
    "artist": "&#127928;",
    "industry": "&#128200;",
}


# Leadership display ordering: EIC → cross-portfolio heads → edition
# growth → edition marketing → edition sales → expansion leads.
_LEADERSHIP_RANK = {
    "editor_in_chief": 0,
    "head_of_growth": 1,
    "cmo": 2,
    "vp_sales": 3,
    "growth_lead": 4,
    "marketing_lead": 5,
    "sales_lead": 6,
    "expansion_lead": 7,
}
_EDITION_RANK = {"fan": 0, "artist": 1, "industry": 2, "": 3}


def _leadership_role(atype: str, cfg: dict, editions_count: int) -> str:
    """Derive a display role key for leadership sorting/labeling.

    The role collapses the (agent_type + config_json) combination into a
    single label the template can render as a badge ("Growth Lead",
    "Cities Expansion", etc.). A config-level `role` wins; otherwise we
    infer from agent_type and whether the agent is edition-scoped.
    """
    explicit = cfg.get("role")
    if explicit:
        return explicit
    if cfg.get("expansion"):
        return "expansion_lead"
    if atype == "editor_in_chief":
        return "editor_in_chief"
    if atype == "growth":
        return "growth_lead" if cfg.get("edition") else "head_of_growth"
    if atype == "marketing":
        return "marketing_lead" if cfg.get("edition") else "cmo"
    if atype == "sales":
        return "vp_sales" if editions_count > 1 else "sales_lead"
    return atype


def _enrich_staff(staff: list[dict]) -> dict:
    """Organize staff into structured groups by role and edition.

    Leadership captures every management-level role: Editor-in-Chief,
    cross-portfolio heads (Growth, Marketing, Sales VP), per-edition
    Growth/Marketing/Sales leads, and Expansion leads (Cities, Genre).
    Edition teams still surface their Sales lead so readers see a
    complete roster per newsletter — sales intentionally appears in
    both places.
    """
    leadership = []
    edition_teams = {
        "fan": {"editor": None, "researchers": [], "writers": [], "sales": None, "promotion": None},
        "artist": {"editor": None, "researchers": [], "writers": [], "sales": None, "promotion": None},
        "industry": {"editor": None, "researchers": [], "writers": [], "sales": None, "promotion": None},
    }
    cross_newsletter = []

    for agent in staff:
        enriched = dict(agent)
        try:
            cfg = json.loads(agent.get("config_json") or "{}")
        except (ValueError, TypeError):
            cfg = {}
        enriched["categories"] = cfg.get("categories", [])
        enriched["sections"] = cfg.get("sections", [])
        enriched["edition"] = cfg.get("edition", "")
        enriched["editions"] = cfg.get("editions", [])
        enriched["expansion"] = cfg.get("expansion", "")

        atype = agent.get("agent_type", "")
        role = _leadership_role(atype, cfg, len(enriched["editions"]))
        enriched["leadership_role"] = role

        is_leader = atype in ("editor_in_chief", "growth", "marketing", "sales")
        if is_leader:
            leadership.append(enriched)

        # Edition-team placement (sales lands here AND in leadership).
        if atype in ("editor", "researcher", "writer", "sales", "promotion") and enriched["edition"] in edition_teams:
            if atype == "writer":
                edition_teams[enriched["edition"]]["writers"].append(enriched)
            elif atype == "researcher":
                edition_teams[enriched["edition"]]["researchers"].append(enriched)
            else:
                edition_teams[enriched["edition"]][atype] = enriched
        elif not is_leader:
            # Publisher sign-off (Paul) and any other cross-edition role
            # that isn't a leadership function.
            cross_newsletter.append(enriched)

    leadership.sort(key=lambda a: (
        _LEADERSHIP_RANK.get(a.get("leadership_role", ""), 99),
        _EDITION_RANK.get(a.get("edition") or "", 3),
        a.get("expansion") or "",
        a.get("name") or "",
    ))

    editions = []
    for slug in ("fan", "artist", "industry"):
        team = edition_teams[slug]
        members = []
        if team["editor"]:
            members.append(team["editor"])
        members.extend(team["researchers"])
        members.extend(team["writers"])
        if team["sales"]:
            members.append(team["sales"])
        if team["promotion"]:
            members.append(team["promotion"])

        # Build role summary for header
        roles = []
        if team["editor"]:
            roles.append("Editor")
        researcher_count = len(team["researchers"])
        if researcher_count == 1:
            roles.append("Researcher")
        elif researcher_count > 1:
            roles.append(f"{researcher_count} Researchers")
        writer_count = len(team["writers"])
        if writer_count == 1:
            roles.append("Writer")
        elif writer_count > 1:
            roles.append(f"{writer_count} Writers")
        if team["sales"]:
            roles.append("Sales")
        if team["promotion"]:
            roles.append("Promotion")

        editions.append({
            "slug": slug,
            "label": EDITION_LABELS[slug],
            "color": EDITION_COLORS[slug],
            "icon": EDITION_ICONS[slug],
            "team": members,
            "roles_summary": " · ".join(roles),
        })

    return {
        "leadership": leadership,
        "editions": editions,
        "cross_newsletter": cross_newsletter,
    }


@router.get("/", response_class=HTMLResponse)
async def agents_page():
    repo = get_repo()
    config = get_config()
    orchestrator = AgentOrchestrator(repo, config)
    staff = orchestrator.get_staff_status()
    pending_reviews = orchestrator.check_pending_reviews()
    groups = _enrich_staff(staff)
    return render("agents.html",
        staff=staff,
        leadership=groups["leadership"],
        editions=groups["editions"],
        cross_newsletter=groups["cross_newsletter"],
        pending_reviews=pending_reviews,
    )


@router.get("/workflow", response_class=HTMLResponse)
async def workflow_page():
    config = get_config()
    return render("agents_workflow.html", config=config)


@router.get("/tasks", response_class=HTMLResponse)
async def tasks_list(state: str = ""):
    repo = get_repo()
    tasks = repo.get_agent_tasks(state=state if state else None)
    return render("partials/task_list.html", tasks=tasks, filter_state=state)


@router.get("/{agent_id}", response_class=HTMLResponse)
async def agent_detail(agent_id: int):
    repo = get_repo()
    agent = repo.get_agent(agent_id)
    if not agent:
        return render("partials/alert.html", message="Agent not found.", level="error")
    agent = dict(agent)
    try:
        cfg = json.loads(agent.get("config_json") or "{}")
    except (ValueError, TypeError):
        cfg = {}
    agent["categories"] = cfg.get("categories", [])
    agent["sections"] = cfg.get("sections", [])
    tasks = repo.get_agent_tasks(agent_id=agent_id)
    return render("agent_detail.html", agent=agent, tasks=tasks)


@router.post("/{agent_id}/trigger", response_class=HTMLResponse)
async def trigger_agent(
    agent_id: int,
    task_type: str = Form(...),
    issue_id: int = Form(0),
    section_slug: str = Form(""),
):
    repo = get_repo()
    config = get_config()
    agent = repo.get_agent(agent_id)
    if not agent:
        return render("partials/alert.html", message="Agent not found.", level="error")

    orchestrator = AgentOrchestrator(repo, config)
    try:
        result = orchestrator.trigger_agent(
            agent["agent_type"], task_type,
            issue_id=issue_id if issue_id else None,
            section_slug=section_slug,
        )
        message = f"Task '{task_type}' completed successfully."
        level = "success"
    except Exception as e:
        message = f"Task failed: {e}"
        level = "error"

    staff = orchestrator.get_staff_status()
    pending_reviews = orchestrator.check_pending_reviews()
    groups = _enrich_staff(staff)
    return render("agents.html",
        staff=staff, pending_reviews=pending_reviews,
        leadership=groups["leadership"], editions=groups["editions"],
        cross_newsletter=groups["cross_newsletter"],
        message=message, level=level,
    )


@router.post("/tasks/{task_id}/approve", response_class=HTMLResponse)
async def approve_task(task_id: int):
    repo = get_repo()
    repo.update_task_state(task_id, "complete")
    tasks = repo.get_tasks_for_review()
    return render("partials/task_list.html", tasks=tasks, filter_state="review",
        message="Task approved.", level="success")


@router.post("/tasks/{task_id}/reject", response_class=HTMLResponse)
async def reject_task(task_id: int, notes: str = Form("")):
    repo = get_repo()
    repo.update_task_state(task_id, "failed")
    tasks = repo.get_tasks_for_review()
    return render("partials/task_list.html", tasks=tasks, filter_state="review",
        message="Task rejected.", level="warning")


@router.post("/tasks/{task_id}/override", response_class=HTMLResponse)
async def override_task(task_id: int, human_notes: str = Form("")):
    repo = get_repo()
    repo.override_task(task_id, human_notes)
    tasks = repo.get_tasks_for_review()
    return render("partials/task_list.html", tasks=tasks, filter_state="review",
        message="Task overridden.", level="info")


@router.post("/run-cycle", response_class=HTMLResponse)
async def run_cycle(issue_id: int = Form(0)):
    repo = get_repo()
    config = get_config()
    orchestrator = AgentOrchestrator(repo, config)
    try:
        result = orchestrator.run_autonomous_cycle(
            issue_id=issue_id if issue_id else None,
        )
        message = f"Cycle complete. {result.get('pending_reviews', 0)} tasks awaiting review."
        level = "success"
    except Exception as e:
        message = f"Cycle failed: {e}"
        level = "error"

    staff = orchestrator.get_staff_status()
    pending_reviews = orchestrator.check_pending_reviews()
    groups = _enrich_staff(staff)
    return render("agents.html",
        staff=staff, pending_reviews=pending_reviews,
        leadership=groups["leadership"], editions=groups["editions"],
        cross_newsletter=groups["cross_newsletter"],
        message=message, level=level,
    )
