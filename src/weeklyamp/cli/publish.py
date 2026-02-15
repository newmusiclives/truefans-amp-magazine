"""Publish CLI commands: assemble, preview, push."""

from __future__ import annotations

import tempfile
import webbrowser
from pathlib import Path

import typer
from rich.console import Console

from weeklyamp.content.assembly import assemble_newsletter
from weeklyamp.core.config import load_config
from weeklyamp.db.repository import Repository
from weeklyamp.delivery.beehiiv import BeehiivClient

console = Console()
publish_app = typer.Typer(name="publish", help="Assemble and publish newsletter.")


@publish_app.command("assemble")
def assemble() -> None:
    """Build the final HTML from approved drafts."""
    cfg = load_config()
    repo = Repository(cfg.db_path)

    issue = repo.get_current_issue()
    if not issue:
        console.print("[red]No current issue.[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Assembling Issue #{issue['issue_number']}...[/bold]")

    try:
        html, plain_text = assemble_newsletter(repo, issue["id"], cfg)
    except Exception as exc:
        console.print(f"[red]Assembly failed:[/red] {exc}")
        raise typer.Exit(1)

    # Save to DB
    repo.save_assembled(issue["id"], html, plain_text)
    repo.update_issue_status(issue["id"], "assembled")

    console.print(f"[green]Assembled![/green] HTML: {len(html)} chars, Plain: {len(plain_text)} chars")
    console.print("Run [cyan]weeklyamp publish preview[/cyan] to view, or [cyan]weeklyamp publish push[/cyan] to send to Beehiiv.")


@publish_app.command("preview")
def preview() -> None:
    """Open the assembled newsletter in a web browser."""
    cfg = load_config()
    repo = Repository(cfg.db_path)

    issue = repo.get_current_issue()
    if not issue:
        console.print("[red]No current issue.[/red]")
        raise typer.Exit(1)

    assembled = repo.get_assembled(issue["id"])
    if not assembled:
        console.print("[red]No assembled HTML found.[/red] Run [cyan]weeklyamp publish assemble[/cyan] first.")
        raise typer.Exit(1)

    # Write to temp file and open
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
        f.write(assembled["html_content"])
        tmp_path = f.name

    console.print(f"Opening preview in browser: [cyan]{tmp_path}[/cyan]")
    webbrowser.open(f"file://{tmp_path}")


@publish_app.command("push")
def push(
    send: bool = typer.Option(False, "--send", help="Send immediately (otherwise saves as Beehiiv draft)"),
) -> None:
    """Push the assembled newsletter to Beehiiv."""
    cfg = load_config()
    repo = Repository(cfg.db_path)

    if not cfg.beehiiv.api_key or not cfg.beehiiv.publication_id:
        console.print("[red]Beehiiv not configured.[/red] Set BEEHIIV_API_KEY and BEEHIIV_PUBLICATION_ID in .env")
        raise typer.Exit(1)

    issue = repo.get_current_issue()
    if not issue:
        console.print("[red]No current issue.[/red]")
        raise typer.Exit(1)

    assembled = repo.get_assembled(issue["id"])
    if not assembled:
        console.print("[red]No assembled HTML.[/red] Run [cyan]weeklyamp publish assemble[/cyan] first.")
        raise typer.Exit(1)

    client = BeehiivClient(cfg.beehiiv)
    title = f"{cfg.newsletter.name} #{issue['issue_number']}"
    if issue.get("title"):
        title += f" — {issue['title']}"

    action = "Sending" if send else "Creating draft in"
    console.print(f"[bold]{action} Beehiiv...[/bold]")

    try:
        result = client.create_post(
            title=title,
            html_content=assembled["html_content"],
            send=send,
        )
        post_id = result.get("id", "")
        repo.update_assembled_beehiiv(assembled["id"], post_id)

        if send:
            repo.update_issue_status(issue["id"], "published")
            console.print(f"[bold green]Published![/bold green] Post ID: {post_id}")
        else:
            console.print(f"[green]Draft created in Beehiiv![/green] Post ID: {post_id}")
            console.print("Review in Beehiiv dashboard, then send when ready.")
    except Exception as exc:
        console.print(f"[red]Beehiiv push failed:[/red] {exc}")
        raise typer.Exit(1)
    finally:
        client.close()
