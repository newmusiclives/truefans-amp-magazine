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
from weeklyamp.delivery.smtp_sender import SMTPSender

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
    console.print("Run [cyan]weeklyamp publish preview[/cyan] to view, or [cyan]weeklyamp publish push[/cyan] to send.")


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
    send: bool = typer.Option(False, "--send", help="Send immediately via SMTP"),
) -> None:
    """Send the assembled newsletter via GoHighLevel SMTP."""
    cfg = load_config()
    repo = Repository(cfg.db_path)

    if not cfg.email.enabled or not cfg.email.smtp_host:
        console.print("[red]Email not configured.[/red] Set WEEKLYAMP_EMAIL_ENABLED=true and SMTP settings in .env")
        raise typer.Exit(1)

    issue = repo.get_current_issue()
    if not issue:
        console.print("[red]No current issue.[/red]")
        raise typer.Exit(1)

    assembled = repo.get_assembled(issue["id"])
    if not assembled:
        console.print("[red]No assembled HTML.[/red] Run [cyan]weeklyamp publish assemble[/cyan] first.")
        raise typer.Exit(1)

    # Build subject
    title = f"{cfg.newsletter.name} #{issue['issue_number']}"
    if issue.get("title"):
        title += f" — {issue['title']}"

    if send:
        console.print("[bold]Sending newsletter via SMTP...[/bold]")
        recipients = repo.get_subscribers("active")
        sender = SMTPSender(cfg.email)
        result = sender.send_bulk(
            recipients=recipients,
            subject=title,
            html_body=assembled["html_content"],
            plain_text=assembled.get("plain_text", ""),
            site_domain=cfg.site_domain,
        )
        repo.update_assembled_ghl(assembled["id"], f"smtp-{issue['id']}")
        repo.update_issue_status(issue["id"], "published")
        console.print(f"[bold green]Published![/bold green] Sent to {result['sent']} subscribers")
        if result["failed"]:
            console.print(f"[yellow]{result['failed']} failed[/yellow]")
    else:
        console.print("[bold]Sending test email to from_address...[/bold]")
        sender = SMTPSender(cfg.email)
        success = sender.send_single(
            to_email=cfg.email.from_address,
            subject=f"[TEST] {title}",
            html_body=assembled["html_content"],
            plain_text=assembled.get("plain_text", ""),
        )
        if success:
            console.print(f"[green]Test email sent to {cfg.email.from_address}[/green]")
            console.print("Add [cyan]--send[/cyan] flag to send to all subscribers.")
        else:
            console.print("[red]Test send failed — check SMTP settings.[/red]")
            raise typer.Exit(1)
