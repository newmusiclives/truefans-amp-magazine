"""Interactive review workflow with Rich display."""

from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from weeklyamp.content.sections import get_section_map
from weeklyamp.core.config import load_config
from weeklyamp.db.repository import Repository

console = Console()
review_app = typer.Typer(name="review", help="Review and approve drafts.")


@review_app.callback(invoke_without_command=True)
def interactive_review(ctx: typer.Context) -> None:
    """Walk through all pending drafts for interactive review."""
    if ctx.invoked_subcommand is not None:
        return

    cfg = load_config()
    repo = Repository(cfg.db_path)

    issue = repo.get_current_issue()
    if not issue:
        console.print("[red]No current issue.[/red]")
        raise typer.Exit(1)

    drafts = repo.get_drafts_for_issue(issue["id"])
    section_map = get_section_map(repo)
    pending = [d for d in drafts if d["status"] in ("pending", "revised")]

    if not pending:
        console.print("[green]All drafts have been reviewed![/green]")
        return

    console.print(f"\n[bold]Reviewing Issue #{issue['issue_number']}[/bold] — {len(pending)} drafts to review\n")

    for draft in pending:
        slug = draft["section_slug"]
        display = section_map.get(slug, {}).get("display_name", slug)

        console.print(Panel(
            Markdown(draft["content"]),
            title=f"[bold]{display}[/bold] (v{draft['version']})",
            border_style="cyan",
        ))

        action = Prompt.ask(
            "\n[bold]Action[/bold]",
            choices=["approve", "reject", "edit", "skip"],
            default="skip",
        )

        if action == "approve":
            repo.update_draft_status(draft["id"], "approved")
            console.print(f"  [green]Approved![/green]\n")
        elif action == "reject":
            notes = Prompt.ask("  Rejection notes", default="")
            repo.update_draft_status(draft["id"], "rejected", notes)
            console.print(f"  [red]Rejected.[/red]\n")
        elif action == "edit":
            new_content = _open_in_editor(draft["content"])
            if new_content and new_content != draft["content"]:
                repo.update_draft_content(draft["id"], new_content)
                console.print(f"  [blue]Updated.[/blue]\n")
            else:
                console.print(f"  [dim]No changes.[/dim]\n")
        else:
            console.print(f"  [dim]Skipped.[/dim]\n")

    # Update issue status if all approved
    all_drafts = repo.get_drafts_for_issue(issue["id"])
    if all_drafts and all(d["status"] == "approved" for d in all_drafts):
        repo.update_issue_status(issue["id"], "reviewing")
        console.print("[bold green]All drafts approved![/bold green] Run [cyan]weeklyamp publish assemble[/cyan].")


@review_app.command("approve")
def approve(
    section: str = typer.Option(..., "-s", "--section", help="Section slug to approve"),
) -> None:
    """Approve a specific section's draft."""
    cfg = load_config()
    repo = Repository(cfg.db_path)

    issue = repo.get_current_issue()
    if not issue:
        console.print("[red]No current issue.[/red]")
        raise typer.Exit(1)

    draft = repo.get_latest_draft(issue["id"], section)
    if not draft:
        console.print(f"[red]No draft for {section}.[/red]")
        raise typer.Exit(1)

    repo.update_draft_status(draft["id"], "approved")
    console.print(f"[green]Approved[/green] draft for [cyan]{section}[/cyan] (v{draft['version']})")


@review_app.command("reject")
def reject(
    section: str = typer.Option(..., "-s", "--section", help="Section slug to reject"),
    notes: str = typer.Option("", "-n", "--notes", help="Rejection notes"),
) -> None:
    """Reject a specific section's draft."""
    cfg = load_config()
    repo = Repository(cfg.db_path)

    issue = repo.get_current_issue()
    if not issue:
        console.print("[red]No current issue.[/red]")
        raise typer.Exit(1)

    draft = repo.get_latest_draft(issue["id"], section)
    if not draft:
        console.print(f"[red]No draft for {section}.[/red]")
        raise typer.Exit(1)

    repo.update_draft_status(draft["id"], "rejected", notes)
    console.print(f"[red]Rejected[/red] draft for [cyan]{section}[/cyan]" + (f" — {notes}" if notes else ""))


@review_app.command("edit")
def edit(
    section: str = typer.Option(..., "-s", "--section", help="Section slug to edit"),
) -> None:
    """Open a section's draft in $EDITOR for editing."""
    cfg = load_config()
    repo = Repository(cfg.db_path)

    issue = repo.get_current_issue()
    if not issue:
        console.print("[red]No current issue.[/red]")
        raise typer.Exit(1)

    draft = repo.get_latest_draft(issue["id"], section)
    if not draft:
        console.print(f"[red]No draft for {section}.[/red]")
        raise typer.Exit(1)

    new_content = _open_in_editor(draft["content"])
    if new_content and new_content != draft["content"]:
        repo.update_draft_content(draft["id"], new_content)
        console.print(f"[green]Draft updated[/green] for [cyan]{section}[/cyan]")
    else:
        console.print("[dim]No changes made.[/dim]")


def _open_in_editor(content: str) -> Optional[str]:
    """Open content in the user's $EDITOR. Returns edited content or None."""
    editor = os.environ.get("EDITOR", "nano")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        tmp_path = f.name

    try:
        subprocess.run([editor, tmp_path], check=True)
        with open(tmp_path) as f:
            return f.read()
    except (subprocess.CalledProcessError, FileNotFoundError):
        console.print(f"[red]Could not open editor ({editor}).[/red]")
        return None
    finally:
        os.unlink(tmp_path)
