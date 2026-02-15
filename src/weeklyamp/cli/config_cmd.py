"""Config/sections management CLI commands."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from weeklyamp.core.config import load_config
from weeklyamp.db.repository import Repository

console = Console()
config_app = typer.Typer(name="config", help="Configuration and section management.")


@config_app.command("sections")
def list_sections() -> None:
    """List all newsletter sections."""
    cfg = load_config()
    repo = Repository(cfg.db_path)
    sections = repo.get_active_sections()

    table = Table(title="Newsletter Sections")
    table.add_column("#", style="dim", width=3)
    table.add_column("Slug", style="cyan")
    table.add_column("Display Name", style="white")
    table.add_column("Active", justify="center")

    for sec in sections:
        active = "[green]Yes[/green]" if sec["is_active"] else "[red]No[/red]"
        table.add_row(str(sec["sort_order"]), sec["slug"], sec["display_name"], active)

    console.print(table)


@config_app.command("add-section")
def add_section(
    slug: str = typer.Option(..., help="Section slug (lowercase, underscores)"),
    name: str = typer.Option(..., help="Display name"),
    order: int = typer.Option(..., help="Sort order"),
) -> None:
    """Add a new newsletter section."""
    cfg = load_config()
    repo = Repository(cfg.db_path)

    try:
        repo.add_section(slug, name, order)
        console.print(f"[green]Added section:[/green] {slug} — {name}")
    except Exception as exc:
        console.print(f"[red]Failed:[/red] {exc}")
        raise typer.Exit(1)


@config_app.command("toggle-section")
def toggle_section(
    slug: str = typer.Option(..., "-s", "--slug", help="Section slug to toggle"),
) -> None:
    """Enable or disable a section."""
    cfg = load_config()
    repo = Repository(cfg.db_path)

    section = repo.get_section(slug)
    if not section:
        console.print(f"[red]Section not found:[/red] {slug}")
        raise typer.Exit(1)

    new_state = not bool(section["is_active"])
    repo.update_section(slug, is_active=int(new_state))
    state_str = "[green]enabled[/green]" if new_state else "[red]disabled[/red]"
    console.print(f"Section [cyan]{slug}[/cyan] is now {state_str}")


@config_app.command("reorder")
def reorder_section(
    slug: str = typer.Option(..., "-s", "--slug", help="Section slug"),
    order: int = typer.Option(..., "-o", "--order", help="New sort order"),
) -> None:
    """Change a section's sort order."""
    cfg = load_config()
    repo = Repository(cfg.db_path)

    section = repo.get_section(slug)
    if not section:
        console.print(f"[red]Section not found:[/red] {slug}")
        raise typer.Exit(1)

    repo.update_section(slug, sort_order=order)
    console.print(f"Section [cyan]{slug}[/cyan] moved to position [cyan]{order}[/cyan]")
