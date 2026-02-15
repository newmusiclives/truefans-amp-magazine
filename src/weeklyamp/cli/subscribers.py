"""Subscriber CLI commands: sync, stats."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from weeklyamp.core.config import load_config
from weeklyamp.db.repository import Repository
from weeklyamp.delivery.subscribers import sync_subscribers

console = Console()
subs_app = typer.Typer(name="subs", help="Subscriber management.")


@subs_app.command("sync")
def sync() -> None:
    """Pull subscribers from Beehiiv into local database."""
    cfg = load_config()

    if not cfg.beehiiv.api_key or not cfg.beehiiv.publication_id:
        console.print("[red]Beehiiv not configured.[/red] Set BEEHIIV_API_KEY and BEEHIIV_PUBLICATION_ID in .env")
        raise typer.Exit(1)

    repo = Repository(cfg.db_path)
    console.print("[bold]Syncing subscribers from Beehiiv...[/bold]")

    try:
        result = sync_subscribers(repo, cfg.beehiiv)
        console.print(f"[green]Synced![/green] {result['synced']} processed, {result['new']} new, {result['total']} total active")
    except Exception as exc:
        console.print(f"[red]Sync failed:[/red] {exc}")
        raise typer.Exit(1)


@subs_app.command("stats")
def stats() -> None:
    """Show subscriber and engagement statistics."""
    cfg = load_config()
    repo = Repository(cfg.db_path)

    # Subscriber counts
    active = repo.get_subscriber_count()
    console.print(f"\n[bold]Subscriber Stats[/bold]")
    console.print(f"  Active subscribers: [cyan]{active}[/cyan]")

    # Recent engagement
    issue = repo.get_current_issue()
    if issue:
        engagement = repo.get_engagement(issue["id"])
        if engagement:
            table = Table(title=f"Engagement — Issue #{issue['issue_number']}")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", justify="right")

            table.add_row("Sends", str(engagement["sends"]))
            table.add_row("Opens", str(engagement["opens"]))
            table.add_row("Clicks", str(engagement["clicks"]))
            table.add_row("Open Rate", f"{engagement['open_rate']:.1%}")
            table.add_row("Click Rate", f"{engagement['click_rate']:.1%}")
            console.print(table)
        else:
            console.print("  [dim]No engagement data yet.[/dim]")


@subs_app.command("count")
def count() -> None:
    """Show active subscriber count."""
    cfg = load_config()
    repo = Repository(cfg.db_path)
    n = repo.get_subscriber_count()
    console.print(f"Active subscribers: [bold cyan]{n}[/bold cyan]")
