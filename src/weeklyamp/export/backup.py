"""Backup and export utilities.

Provides CSV subscriber exports, JSON content exports, sanitised
config YAML dumps, and full timestamped backups.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from weeklyamp.core.models import AppConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


class ExportManager:
    """Create data exports and backups of the WeeklyAmp system."""

    def __init__(self, repo: Repository, config: AppConfig) -> None:
        self.repo = repo
        self.config = config

    # ------------------------------------------------------------------
    # Subscriber export
    # ------------------------------------------------------------------

    def export_subscribers(self, format: str = "csv") -> tuple[str, str, int]:
        """Export all subscribers to a CSV string.

        Returns ``(csv_content, filename, record_count)``.
        """
        subscribers = self.repo.get_subscribers(status="active")
        subscribers += self.repo.get_subscribers(status="inactive")

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"subscribers_{timestamp}.csv"

        buf = io.StringIO()
        if subscribers:
            fieldnames = list(subscribers[0].keys())
            writer = csv.DictWriter(buf, fieldnames=fieldnames)
            writer.writeheader()
            for sub in subscribers:
                writer.writerow(sub)
        else:
            buf.write("email,status\n")

        content = buf.getvalue()
        logger.info("Exported %d subscribers to %s", len(subscribers), filename)
        return content, filename, len(subscribers)

    # ------------------------------------------------------------------
    # Content export
    # ------------------------------------------------------------------

    def export_content(self, issue_id: Optional[int] = None) -> str:
        """Export drafts and assembled issues to a JSON string.

        When *issue_id* is provided, only that issue's data is included.
        """
        data: dict = {"exported_at": datetime.utcnow().isoformat(), "issues": []}

        if issue_id:
            issue = self.repo.get_issue(issue_id)
            if issue:
                drafts = self.repo.get_drafts_for_issue(issue_id)
                assembled = self.repo.get_assembled(issue_id)
                data["issues"].append({
                    "issue": issue,
                    "drafts": drafts,
                    "assembled": assembled,
                })
        else:
            # Export all recent issues
            issues = self.repo.get_upcoming_issues(limit=50)
            issues += self.repo.get_published_issues(limit=50)
            seen_ids: set[int] = set()
            for iss in issues:
                iid = iss["id"]
                if iid in seen_ids:
                    continue
                seen_ids.add(iid)
                drafts = self.repo.get_drafts_for_issue(iid)
                assembled = self.repo.get_assembled(iid)
                data["issues"].append({
                    "issue": iss,
                    "drafts": drafts,
                    "assembled": assembled,
                })

        content = json.dumps(data, indent=2, default=str)
        logger.info("Exported content for %d issues", len(data["issues"]))
        return content

    # ------------------------------------------------------------------
    # Config export (sanitised)
    # ------------------------------------------------------------------

    def export_config(self) -> str:
        """Export current config as YAML, stripping passwords and API keys."""
        cfg_dict = self.config.model_dump()

        # Sanitise sensitive fields
        sensitive_keys = {
            "api_key", "smtp_password", "inbound_secret", "password",
            "secret", "token", "database_url",
        }

        def _sanitise(d: dict) -> dict:
            result = {}
            for k, v in d.items():
                if isinstance(v, dict):
                    result[k] = _sanitise(v)
                elif any(sk in k.lower() for sk in sensitive_keys):
                    result[k] = "***REDACTED***" if v else ""
                else:
                    result[k] = v
            return result

        sanitised = _sanitise(cfg_dict)
        content = yaml.dump(sanitised, default_flow_style=False, sort_keys=False)
        logger.info("Exported sanitised config")
        return content

    # ------------------------------------------------------------------
    # Full backup
    # ------------------------------------------------------------------

    def full_backup(self, output_dir: str) -> str:
        """Export everything to a timestamped sub-directory.

        Creates:
            - subscribers.csv
            - content.json
            - config.yaml

        Logs the export to the ``export_log`` table and returns the
        backup directory path.
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(output_dir, f"backup_{timestamp}")
        os.makedirs(backup_dir, exist_ok=True)

        # Subscribers
        csv_content, csv_filename, sub_count = self.export_subscribers()
        with open(os.path.join(backup_dir, "subscribers.csv"), "w") as f:
            f.write(csv_content)

        # Content
        content_json = self.export_content()
        with open(os.path.join(backup_dir, "content.json"), "w") as f:
            f.write(content_json)

        # Config
        config_yaml = self.export_config()
        with open(os.path.join(backup_dir, "config.yaml"), "w") as f:
            f.write(config_yaml)

        # Log to export_log table
        conn = self.repo._conn()
        conn.execute(
            """INSERT INTO export_log
                   (export_type, file_path, record_count)
               VALUES (?, ?, ?)""",
            ("full_backup", backup_dir, sub_count),
        )
        conn.commit()
        conn.close()

        logger.info("Full backup written to %s", backup_dir)
        return backup_dir

    # ------------------------------------------------------------------
    # Export history
    # ------------------------------------------------------------------

    def get_export_history(self, limit: int = 20) -> list[dict]:
        """Return recent exports from the ``export_log`` table."""
        conn = self.repo._conn()
        rows = conn.execute(
            "SELECT * FROM export_log ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
