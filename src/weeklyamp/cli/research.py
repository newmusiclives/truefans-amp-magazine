"""Research CLI commands: scrape, list, add-topic."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from weeklyamp.core.config import load_config
from weeklyamp.db.repository import Repository
from weeklyamp.research.discovery import score_and_tag_content
from weeklyamp.research.sources import fetch_all_sources, sync_sources_from_config

console = Console()
research_app = typer.Typer(name="research", help="Content research and scraping.")


@research_app.command("scrape")
def scrape() -> None:
    """Scrape all RSS feeds and blog sources for new content."""
    cfg = load_config()
    repo = Repository(cfg.db_path)

    # Sync sources from config
    new_sources = sync_sources_from_config(repo)
    if new_sources:
        console.print(f"  Added [green]{new_sources}[/green] new sources from config")

    console.print("[bold]Scraping all sources...[/bold]\n")
    results = fetch_all_sources(repo)

    # Score newly fetched content
    console.print("\n[bold]Scoring content relevance...[/bold]")
    content_items = repo.get_unused_content(limit=100)
    for item in content_items:
        if not item["matched_sections"] or item["relevance_score"] == 0:
            score_and_tag_content(repo, item["id"], item["title"], item["summary"])

    # Summary
    total = sum(results.values())
    console.print(f"\n[bold green]Done![/bold green] Fetched [cyan]{total}[/cyan] new items from [cyan]{len(results)}[/cyan] sources.")

    table = Table(title="Source Results")
    table.add_column("Source", style="cyan")
    table.add_column("New Items", justify="right")
    for name, count in results.items():
        table.add_row(name, str(count))
    console.print(table)


@research_app.command("list")
def list_content(
    section: Optional[str] = typer.Option(None, "-s", "--section", help="Filter by section slug"),
    limit: int = typer.Option(20, "-n", "--limit", help="Max items to show"),
) -> None:
    """Show discovered content items."""
    cfg = load_config()
    repo = Repository(cfg.db_path)
    items = repo.get_unused_content(section_slug=section, limit=limit)

    if not items:
        console.print("[dim]No unused content found.[/dim]")
        return

    table = Table(title=f"Content Items ({len(items)})")
    table.add_column("ID", style="dim", width=5)
    table.add_column("Title", style="white", max_width=50)
    table.add_column("Sections", style="cyan", max_width=30)
    table.add_column("Score", justify="right", width=6)

    for item in items:
        table.add_row(
            str(item["id"]),
            item["title"][:50],
            item["matched_sections"],
            f"{item['relevance_score']:.2f}",
        )
    console.print(table)


@research_app.command("add-topic")
def add_topic(
    section: str = typer.Option(..., "-s", "--section", help="Section slug"),
    topic: str = typer.Option(..., "-t", "--topic", help="Topic or subject"),
    notes: str = typer.Option("", "-n", "--notes", help="Additional notes"),
) -> None:
    """Add a manual editorial topic for a section."""
    cfg = load_config()
    repo = Repository(cfg.db_path)

    # Get or create current issue
    issue = repo.get_current_issue()
    if not issue:
        num = repo.get_next_issue_number()
        issue_id = repo.create_issue(num)
        console.print(f"Created new issue #{num}")
    else:
        issue_id = issue["id"]

    repo.add_editorial_input(
        issue_id=issue_id,
        section_slug=section,
        topic=topic,
        notes=notes,
    )
    console.print(f"[green]Added topic[/green] for [cyan]{section}[/cyan]: {topic}")
