"""CLI commands for AI Staff management."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from weeklyamp.agents.orchestrator import AgentOrchestrator
from weeklyamp.core.config import load_config
from weeklyamp.db.repository import Repository

console = Console()
agent_app = typer.Typer(name="agent", help="AI Staff management.")


@agent_app.command("status")
def agent_status() -> None:
    """Show all agents and their current state."""
    cfg = load_config()
    repo = Repository(cfg.db_path)
    orchestrator = AgentOrchestrator(repo, cfg)
    staff = orchestrator.get_staff_status()

    if not staff:
        console.print("[dim]No agents registered yet. Run a task to auto-create agents.[/dim]")
        return

    table = Table(title="AI Staff")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="white")
    table.add_column("Autonomy", style="white")
    table.add_column("Active", style="yellow")
    table.add_column("Review", style="purple")
    table.add_column("Complete", style="green")
    table.add_column("Failed", style="red")

    for agent in staff:
        table.add_row(
            agent["name"],
            agent["agent_type"],
            agent.get("autonomy_level", "manual"),
            str(agent["active_tasks"]),
            str(agent["review_tasks"]),
            str(agent["completed_tasks"]),
            str(agent["failed_tasks"]),
        )

    console.print(table)


@agent_app.command("run")
def agent_run(
    agent_type: str = typer.Argument(help="Agent type: editor_in_chief, writer, researcher, sales, growth"),
    task_type: str = typer.Argument(help="Task type to execute"),
    issue_id: int = typer.Option(0, help="Issue ID to target"),
    section_slug: str = typer.Option("", help="Section slug to target"),
) -> None:
    """Trigger a specific agent to run a task."""
    cfg = load_config()
    repo = Repository(cfg.db_path)
    orchestrator = AgentOrchestrator(repo, cfg)

    console.print(f"[bold]Running {agent_type} -> {task_type}...[/bold]")

    try:
        result = orchestrator.trigger_agent(
            agent_type, task_type,
            issue_id=issue_id if issue_id else None,
            section_slug=section_slug,
        )
        console.print(f"[green]Task completed:[/green]")
        for k, v in result.items():
            val_str = str(v)[:200]
            console.print(f"  {k}: {val_str}")
    except Exception as e:
        console.print(f"[red]Failed:[/red] {e}")
        raise typer.Exit(1)


@agent_app.command("review")
def agent_review() -> None:
    """List pending human reviews."""
    cfg = load_config()
    repo = Repository(cfg.db_path)
    orchestrator = AgentOrchestrator(repo, cfg)
    reviews = orchestrator.check_pending_reviews()

    if not reviews:
        console.print("[dim]No tasks pending review.[/dim]")
        return

    table = Table(title="Pending Reviews")
    table.add_column("ID", style="white")
    table.add_column("Agent", style="cyan")
    table.add_column("Task Type", style="white")
    table.add_column("Section", style="white")
    table.add_column("Created", style="dim")

    for task in reviews:
        table.add_row(
            str(task["id"]),
            task.get("agent_name", ""),
            task["task_type"],
            task.get("section_slug", ""),
            str(task.get("created_at", "")),
        )

    console.print(table)
