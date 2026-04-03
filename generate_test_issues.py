"""Generate 3 test newsletter issues (Fan, Artist, Industry) with AI content.

Creates issues, generates drafts for 5 sections per edition (Monday send day),
assembles into full HTML, and saves as preview files.

Usage: python3 generate_test_issues.py
"""
from __future__ import annotations

import os
import sys
import time

# Ensure project is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from weeklyamp.core.config import load_config
from weeklyamp.core.database import init_database, seed_sections, seed_editions, seed_agents
from weeklyamp.db.repository import Repository
from weeklyamp.content.assembly import assemble_newsletter

TARGET_EMAIL = "paul@lightworkdigital.com"
SECTIONS_PER_EDITION = 5  # Generate 5 sections per edition to keep it fast


def main():
    cfg = load_config()
    db_path = os.path.abspath(cfg.db_path)

    # Init DB
    init_database(db_path, "", "sqlite")
    seed_sections(db_path, "", "sqlite")
    seed_editions(db_path, "", "sqlite")
    seed_agents(db_path, "", "sqlite")

    repo = Repository(db_path)
    editions = repo.get_editions()
    next_num = repo.get_next_issue_number()

    results = []

    for edition in editions:
        slug = edition["slug"]
        name = edition["name"]
        print(f"\n{'='*60}")
        print(f"Generating: {name} (Monday edition)")
        print(f"{'='*60}")

        # Create issue
        issue_num = next_num
        next_num += 1
        issue_id = repo.create_issue_with_schedule(
            issue_number=issue_num,
            title=f"{name} — Test Issue #{issue_num}",
            week_id="2026-W12",
            send_day="monday",
            edition_slug=slug,
        )
        print(f"  Created issue #{issue_num} (id={issue_id})")

        # Get edition sections (first N for Monday)
        edition_sections = repo.get_edition_sections(slug)
        sections_to_generate = edition_sections[:SECTIONS_PER_EDITION]

        print(f"  Generating {len(sections_to_generate)} sections: {', '.join(s['slug'] for s in sections_to_generate)}")

        # Generate AI drafts for each section
        from weeklyamp.content.generator import generate_draft
        from weeklyamp.content.prompts import build_prompt

        for sec in sections_to_generate:
            sec_slug = sec["slug"]
            display = sec["display_name"]
            word_count = sec.get("target_word_count", 300)
            label = sec.get("word_count_label", "medium")

            print(f"    Drafting: {display} ({sec_slug})...", end=" ", flush=True)
            start = time.time()

            prompt = build_prompt(
                section_slug=sec_slug,
                topic="",
                notes=f"This is a test issue for the {name}. Write engaging content appropriate for this section.",
                reference_content="",
                newsletter_name=cfg.newsletter.name,
                target_word_count=word_count,
                word_count_label=label,
            )

            try:
                content, model_used = generate_draft(prompt, cfg)
                draft_id = repo.create_draft(
                    issue_id=issue_id,
                    section_slug=sec_slug,
                    content=content,
                    ai_model=model_used,
                    prompt_used=prompt[:500],
                )
                # Auto-approve
                repo.update_draft_status(draft_id, "approved")
                elapsed = time.time() - start
                words = len(content.split())
                print(f"OK ({words} words, {elapsed:.1f}s)")
            except Exception as e:
                print(f"FAILED: {e}")
                # Create a placeholder draft
                placeholder = f"# {display}\n\nThis section is coming soon in the {name}. Stay tuned for insights and stories curated just for you."
                draft_id = repo.create_draft(
                    issue_id=issue_id,
                    section_slug=sec_slug,
                    content=placeholder,
                    ai_model="placeholder",
                )
                repo.update_draft_status(draft_id, "approved")

        # Assemble newsletter
        print(f"  Assembling newsletter...")
        try:
            html, plain = assemble_newsletter(repo, issue_id, cfg)
            repo.save_assembled(issue_id, html, plain)
            repo.update_issue_status(issue_id, "assembled")

            # Save preview HTML
            preview_file = f"test_{slug}_monday.html"
            with open(preview_file, "w") as f:
                f.write(html)
            print(f"  Saved preview: {preview_file} ({len(html):,} bytes)")

            results.append({
                "edition": name,
                "slug": slug,
                "issue_id": issue_id,
                "issue_number": issue_num,
                "html": html,
                "plain": plain,
                "preview_file": preview_file,
            })
        except Exception as e:
            print(f"  Assembly FAILED: {e}")
            import traceback
            traceback.print_exc()

    # Summary
    print(f"\n{'='*60}")
    print(f"GENERATION COMPLETE")
    print(f"{'='*60}")
    for r in results:
        print(f"  {r['edition']}: Issue #{r['issue_number']} -> {r['preview_file']}")

    # Try to send via SMTP if configured
    if cfg.email.enabled and cfg.email.smtp_host and cfg.email.smtp_password:
        print(f"\nSending test emails to {TARGET_EMAIL}...")
        from weeklyamp.delivery.smtp_sender import SMTPSender
        sender = SMTPSender(cfg.email)

        for r in results:
            subject = f"[TEST] {cfg.newsletter.name} — {r['edition']} #{r['issue_number']}"
            success = sender.send_single(
                to_email=TARGET_EMAIL,
                subject=subject,
                html_body=r["html"],
                plain_text=r["plain"],
            )
            status = "SENT" if success else "FAILED"
            print(f"  {r['edition']}: {status}")
    else:
        print(f"\nSMTP not configured — previews saved as HTML files.")
        print(f"To send, set these in your .env file:")
        print(f"  WEEKLYAMP_EMAIL_ENABLED=true")
        print(f"  WEEKLYAMP_SMTP_HOST=your-smtp-host")
        print(f"  WEEKLYAMP_SMTP_PORT=587")
        print(f"  WEEKLYAMP_SMTP_USER=your-user")
        print(f"  WEEKLYAMP_SMTP_PASSWORD=your-password")
        print(f"  WEEKLYAMP_EMAIL_FROM=your@email.com")
        print(f"  WEEKLYAMP_EMAIL_FROM_NAME=TrueFans NEWSLETTERS")
        print(f"\nThen run: python3 generate_test_issues.py")

    # Open previews in browser
    print(f"\nOpening previews in browser...")
    import subprocess
    for r in results:
        subprocess.run(["open", r["preview_file"]], check=False)


if __name__ == "__main__":
    main()
