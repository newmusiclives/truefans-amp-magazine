"""CLI commands for artist submissions management."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from weeklyamp.core.config import load_config
from weeklyamp.db.repository import Repository

console = Console()
submissions_app = typer.Typer(name="submissions", help="Artist submission management.")


@submissions_app.command("list")
def list_submissions(
    state: str = typer.Option("", help="Filter by review state"),
    limit: int = typer.Option(20, help="Max results"),
) -> None:
    """List artist submissions."""
    cfg = load_config()
    repo = Repository(cfg.db_path)
    subs = repo.get_submissions(review_state=state if state else None, limit=limit)

    if not subs:
        console.print("[dim]No submissions found.[/dim]")
        return

    table = Table(title="Artist Submissions")
    table.add_column("ID", style="white")
    table.add_column("Artist", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Type", style="white")
    table.add_column("Method", style="dim")
    table.add_column("State", style="yellow")

    for sub in subs:
        state_style = {
            "submitted": "yellow",
            "reviewed": "blue",
            "approved": "green",
            "rejected": "red",
            "scheduled": "purple",
            "published": "green",
        }.get(sub["review_state"], "white")

        table.add_row(
            str(sub["id"]),
            sub["artist_name"],
            sub.get("title", "")[:40],
            sub.get("submission_type", ""),
            sub.get("intake_method", ""),
            f"[{state_style}]{sub['review_state']}[/{state_style}]",
        )

    console.print(table)
