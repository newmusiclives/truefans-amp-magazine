"""AI Staff routes — agent management and task control."""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from weeklyamp.agents.orchestrator import AgentOrchestrator
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def agents_page():
    repo = get_repo()
    config = get_config()
    orchestrator = AgentOrchestrator(repo, config)
    staff = orchestrator.get_staff_status()
    pending_reviews = orchestrator.check_pending_reviews()
    return render("agents.html",
        staff=staff,
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
    return render("agents.html",
        staff=staff, pending_reviews=pending_reviews,
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
    return render("agents.html",
        staff=staff, pending_reviews=pending_reviews,
        message=message, level=level,
    )
