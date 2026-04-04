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


def _enrich_staff(staff: list[dict]) -> dict:
    """Organize staff into structured groups by role and edition."""
    leadership = []  # editor_in_chief + growth + VP sales
    edition_teams = {
        "fan": {"editor": None, "researchers": [], "writers": [], "sales": None, "promotion": None},
        "artist": {"editor": None, "researchers": [], "writers": [], "sales": None, "promotion": None},
        "industry": {"editor": None, "researchers": [], "writers": [], "sales": None, "promotion": None},
    }
    cross_newsletter = []  # PS and other cross-edition staff

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

        atype = agent.get("agent_type", "")

        if atype == "editor_in_chief":
            leadership.append(enriched)
        elif atype == "growth":
            leadership.append(enriched)
        elif atype == "marketing":
            leadership.append(enriched)
        elif atype == "sales" and len(enriched.get("editions", [])) > 1:
            leadership.append(enriched)
        elif atype in ("editor", "researcher", "writer", "sales", "promotion") and enriched["edition"] in edition_teams:
            if atype == "writer":
                edition_teams[enriched["edition"]]["writers"].append(enriched)
            elif atype == "researcher":
                edition_teams[enriched["edition"]]["researchers"].append(enriched)
            else:
                edition_teams[enriched["edition"]][atype] = enriched
        elif enriched.get("editions"):
            cross_newsletter.append(enriched)
        else:
            cross_newsletter.append(enriched)

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
