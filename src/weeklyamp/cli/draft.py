"""Draft CLI commands: generate, regenerate, list, show."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from weeklyamp.content.generator import generate_draft
from weeklyamp.content.prompts import build_prompt
from weeklyamp.content.sections import get_section_slugs, validate_section
from weeklyamp.core.config import load_config
from weeklyamp.db.repository import Repository

console = Console()
draft_app = typer.Typer(name="draft", help="AI draft generation and management.")


@draft_app.command("generate")
def generate(
    section: Optional[str] = typer.Option(None, "-s", "--section", help="Generate for a specific section only"),
) -> None:
    """AI-generate drafts for all (or one) sections of the current issue."""
    cfg = load_config()
    repo = Repository(cfg.db_path)

    # Get or create current issue
    issue = repo.get_current_issue()
    if not issue:
        num = repo.get_next_issue_number()
        issue_id = repo.create_issue(num, title=f"Issue #{num}")
        issue = repo.get_issue(issue_id)
        console.print(f"[green]Created issue #{num}[/green]")
    else:
        issue_id = issue["id"]

    # Update issue status
    repo.update_issue_status(issue_id, "drafting")

    # Determine which sections to generate
    if section:
        if not validate_section(repo, section):
            console.print(f"[red]Unknown section:[/red] {section}")
            raise typer.Exit(1)
        slugs = [section]
    else:
        slugs = get_section_slugs(repo)

    console.print(f"[bold]Generating drafts for issue #{issue['issue_number']}...[/bold]\n")

    for slug in slugs:
        console.print(f"  [cyan]{slug}[/cyan]... ", end="")

        # Gather editorial inputs + reference content
        inputs = repo.get_editorial_inputs(issue_id, slug)
        topic = ""
        notes = ""
        if inputs:
            topic = inputs[0].get("topic", "")
            notes = inputs[0].get("notes", "")

        # Gather relevant raw content
        raw_items = repo.get_unused_content(section_slug=slug, limit=3)
        reference = ""
        if raw_items:
            reference = "\n\n".join(
                f"- {item['title']}: {item['summary']}" for item in raw_items[:3]
            )

        # Build prompt
        prompt = build_prompt(
            section_slug=slug,
            topic=topic,
            notes=notes,
            reference_content=reference,
            newsletter_name=cfg.newsletter.name,
        )

        try:
            content, model = generate_draft(prompt, cfg)
            repo.create_draft(
                issue_id=issue_id,
                section_slug=slug,
                content=content,
                ai_model=model,
                prompt_used=prompt[:2000],
            )
            console.print(f"[green]done[/green] ({len(content)} chars)")
        except Exception as exc:
            console.print(f"[red]failed:[/red] {exc}")

    console.print(f"\n[bold green]Draft generation complete.[/bold green]")
    console.print("Run [cyan]weeklyamp review[/cyan] to review drafts.")


@draft_app.command("regenerate")
def regenerate(
    section: str = typer.Option(..., "-s", "--section", help="Section to regenerate"),
) -> None:
    """Regenerate the draft for a specific section (creates new version)."""
    cfg = load_config()
    repo = Repository(cfg.db_path)

    issue = repo.get_current_issue()
    if not issue:
        console.print("[red]No current issue.[/red] Run [cyan]weeklyamp draft generate[/cyan] first.")
        raise typer.Exit(1)

    if not validate_section(repo, section):
        console.print(f"[red]Unknown section:[/red] {section}")
        raise typer.Exit(1)

    console.print(f"[bold]Regenerating draft for [cyan]{section}[/cyan]...[/bold]")

    inputs = repo.get_editorial_inputs(issue["id"], section)
    topic = inputs[0].get("topic", "") if inputs else ""
    notes = inputs[0].get("notes", "") if inputs else ""

    raw_items = repo.get_unused_content(section_slug=section, limit=3)
    reference = "\n\n".join(f"- {item['title']}: {item['summary']}" for item in raw_items[:3]) if raw_items else ""

    prompt = build_prompt(section_slug=section, topic=topic, notes=notes, reference_content=reference, newsletter_name=cfg.newsletter.name)

    try:
        content, model = generate_draft(prompt, cfg)
        repo.create_draft(issue_id=issue["id"], section_slug=section, content=content, ai_model=model, prompt_used=prompt[:2000])
        console.print(f"[green]New version created[/green] ({len(content)} chars)")
    except Exception as exc:
        console.print(f"[red]Failed:[/red] {exc}")


@draft_app.command("list")
def list_drafts() -> None:
    """List all drafts for the current issue."""
    cfg = load_config()
    repo = Repository(cfg.db_path)

    issue = repo.get_current_issue()
    if not issue:
        console.print("[dim]No current issue.[/dim]")
        return

    drafts = repo.get_drafts_for_issue(issue["id"])
    if not drafts:
        console.print("[dim]No drafts yet.[/dim]")
        return

    table = Table(title=f"Drafts for Issue #{issue['issue_number']}")
    table.add_column("Section", style="cyan")
    table.add_column("Version", justify="right")
    table.add_column("Status")
    table.add_column("Length", justify="right")
    table.add_column("Model", style="dim")

    for d in drafts:
        status_style = {"pending": "yellow", "approved": "green", "rejected": "red", "revised": "blue"}.get(d["status"], "white")
        table.add_row(
            d["section_slug"],
            f"v{d['version']}",
            f"[{status_style}]{d['status']}[/{status_style}]",
            str(len(d["content"])),
            d["ai_model"],
        )
    console.print(table)


@draft_app.command("show")
def show_draft(
    section: str = typer.Option(..., "-s", "--section", help="Section slug to display"),
) -> None:
    """Display the latest draft for a section."""
    cfg = load_config()
    repo = Repository(cfg.db_path)

    issue = repo.get_current_issue()
    if not issue:
        console.print("[red]No current issue.[/red]")
        raise typer.Exit(1)

    draft = repo.get_latest_draft(issue["id"], section)
    if not draft:
        console.print(f"[dim]No draft for {section}.[/dim]")
        return

    console.print(f"\n[bold]Draft: {section}[/bold] (v{draft['version']}, {draft['status']})\n")
    console.print(Markdown(draft["content"]))
    console.print(f"\n[dim]Model: {draft['ai_model']} | Created: {draft['created_at']}[/dim]")
