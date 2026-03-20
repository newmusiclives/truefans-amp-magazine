"""Export/backup routes (admin)."""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def backup_page():
    cfg = get_config()
    repo = get_repo()

    # Fetch recent exports
    try:
        conn = repo._conn()
        exports = conn.execute(
            "SELECT * FROM export_logs ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
        exports = [dict(r) for r in exports]
        conn.close()
    except Exception:
        exports = []

    return render("backup.html", exports=exports, config=cfg)


@router.post("/subscribers")
async def export_subscribers():
    """Export all subscribers as a CSV download."""
    repo = get_repo()

    try:
        conn = repo._conn()
        rows = conn.execute(
            "SELECT email, status, subscribed_at, synced_at FROM subscribers ORDER BY email"
        ).fetchall()
        rows = [dict(r) for r in rows]
        conn.close()

        # Build CSV
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["email", "status", "subscribed_at", "synced_at"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

        csv_content = output.getvalue()

        # Log the export
        _log_export(repo, "subscribers", len(rows), len(csv_content.encode("utf-8")))

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=subscribers_{timestamp}.csv",
            },
        )
    except Exception as exc:
        return render("partials/alert.html",
            message=f"Export failed: {exc}", level="error")


@router.post("/full", response_class=HTMLResponse)
async def full_backup():
    """Run a full backup of key tables and return a summary."""
    repo = get_repo()

    try:
        conn = repo._conn()
        tables = [
            "subscribers", "issues", "drafts", "section_definitions",
            "assembled_issues", "engagement_metrics", "content_sources",
        ]

        backup_data = {}
        total_records = 0

        for table in tables:
            try:
                rows = conn.execute(f"SELECT * FROM {table}").fetchall()
                table_rows = [dict(r) for r in rows]
                backup_data[table] = table_rows
                total_records += len(table_rows)
            except Exception:
                backup_data[table] = []

        conn.close()

        backup_json = json.dumps(backup_data, indent=2, default=str)
        backup_size = len(backup_json.encode("utf-8"))

        # Log the export
        _log_export(repo, "full_backup", total_records, backup_size)

        size_label = _format_size(backup_size)
        return render("partials/alert.html",
            message=f"Full backup complete: {total_records} records across {len(tables)} tables ({size_label}).",
            level="success")
    except Exception as exc:
        return render("partials/alert.html",
            message=f"Backup failed: {exc}", level="error")


def _log_export(repo, export_type: str, record_count: int, size_bytes: int):
    """Log an export to the export_logs table."""
    try:
        conn = repo._conn()
        conn.execute(
            """INSERT INTO export_logs (export_type, record_count, size_bytes, created_at)
               VALUES (?, ?, ?, ?)""",
            (export_type, record_count, size_bytes, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()
    except Exception:
        logger.exception("Failed to log export")


def _format_size(size_bytes: int) -> str:
    """Format bytes into a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
