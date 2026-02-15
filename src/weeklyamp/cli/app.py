"""Root CLI application with init and status commands."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from weeklyamp.cli.config_cmd import config_app
from weeklyamp.cli.draft import draft_app
from weeklyamp.cli.publish import publish_app
from weeklyamp.cli.research import research_app
from weeklyamp.cli.review import review_app
from weeklyamp.cli.subscribers import subs_app
from weeklyamp.cli.agents import agent_app
from weeklyamp.cli.submissions import submissions_app
from weeklyamp.core.config import load_config
from weeklyamp.core.database import get_schema_version, init_database, seed_sections
from weeklyamp.db.repository import Repository

console = Console()
app = typer.Typer(
    name="weeklyamp",
    help="TrueFans AMP Magazine — AI-powered magazine platform for independent artists.",
    no_args_is_help=True,
)

# Register sub-command groups
app.add_typer(research_app)
app.add_typer(draft_app)
app.add_typer(review_app)
app.add_typer(publish_app)
app.add_typer(subs_app)
app.add_typer(config_app)
app.add_typer(agent_app)
app.add_typer(submissions_app)


@app.command()
def init() -> None:
    """Initialize the database and seed default sections."""
    cfg = load_config()
    db_path = cfg.db_path

    console.print(f"[bold]Initializing TrueFans AMP Magazine...[/bold]")

    # Create DB
    init_database(db_path)
    console.print(f"  Database created at [cyan]{db_path}[/cyan]")

    # Seed sections
    count = seed_sections(db_path)
    if count > 0:
        console.print(f"  Seeded [green]{count}[/green] default sections")
    else:
        console.print("  Sections already exist")

    # Show schema version
    ver = get_schema_version(db_path)
    console.print(f"  Schema version: [cyan]{ver}[/cyan]")

    console.print("\n[bold green]Ready![/bold green] Run [cyan]weeklyamp status[/cyan] to see the dashboard.")


@app.command()
def status() -> None:
    """Show the current issue dashboard."""
    cfg = load_config()
    repo = Repository(cfg.db_path)

    if not Path(cfg.db_path).exists():
        console.print("[red]Database not found.[/red] Run [cyan]weeklyamp init[/cyan] first.")
        raise typer.Exit(1)

    # Current issue
    issue = repo.get_current_issue()
    console.print("\n[bold]TrueFans AMP Magazine Dashboard[/bold]")
    console.print(f"Newsletter: [cyan]{cfg.newsletter.name}[/cyan]")
    console.print(f"AI: [cyan]{cfg.ai.provider.value}[/cyan] / [cyan]{cfg.ai.model}[/cyan]\n")

    if issue:
        console.print(f"[bold]Current Issue:[/bold] #{issue['issue_number']} — {issue['title'] or '(untitled)'}")
        console.print(f"Status: [yellow]{issue['status']}[/yellow]")

        # Drafts summary
        drafts = repo.get_drafts_for_issue(issue["id"])
        sections = repo.get_active_sections()

        table = Table(title="Sections")
        table.add_column("Section", style="cyan")
        table.add_column("Draft", style="white")
        table.add_column("Status", style="white")

        draft_map = {d["section_slug"]: d for d in drafts}
        for sec in sections:
            d = draft_map.get(sec["slug"])
            if d:
                status_style = {
                    "pending": "yellow",
                    "approved": "green",
                    "rejected": "red",
                    "revised": "blue",
                }.get(d["status"], "white")
                table.add_row(
                    sec["display_name"],
                    f"v{d['version']}",
                    f"[{status_style}]{d['status']}[/{status_style}]",
                )
            else:
                table.add_row(sec["display_name"], "—", "[dim]no draft[/dim]")

        console.print(table)
    else:
        console.print("[dim]No issues yet.[/dim] Start by creating one with [cyan]weeklyamp draft generate[/cyan].")

    # Table counts
    counts = repo.get_table_counts()
    console.print(f"\n[dim]Sources: {counts['sources']} | Content items: {counts['raw_content']} | "
                  f"Subscribers: {counts['subscribers']}[/dim]")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host to bind to"),
    port: int = typer.Option(8000, help="Port to listen on"),
    reload: bool = typer.Option(False, help="Enable auto-reload for development"),
) -> None:
    """Start the web dashboard."""
    import uvicorn

    console.print(f"\n[bold]TrueFans AMP Magazine Dashboard[/bold]")
    console.print(f"Starting at [cyan]http://{host}:{port}[/cyan]\n")
    uvicorn.run(
        "weeklyamp.web.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )
