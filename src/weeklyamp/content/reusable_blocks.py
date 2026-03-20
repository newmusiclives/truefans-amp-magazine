"""Reusable content blocks (sponsors, CTAs, headers, footers, etc.).

Provides CRUD operations for the ``reusable_blocks`` table so that
common HTML snippets can be managed centrally and injected into
newsletter templates by slug.
"""

from __future__ import annotations

import logging
from typing import Optional

from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


class BlockManager:
    """Create, retrieve, update, delete, and render reusable content blocks."""

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    # Column whitelist for safe updates
    _ALLOWED_FIELDS = {
        "name", "slug", "block_type", "html_content", "plain_text", "is_active",
    }

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_block(
        self,
        name: str,
        slug: str,
        block_type: str,
        html_content: str,
        plain_text: str = "",
    ) -> int:
        """Insert a new reusable block and return its id."""
        conn = self.repo._conn()
        try:
            cur = conn.execute(
                """INSERT INTO reusable_blocks
                   (name, slug, block_type, html_content, plain_text)
                   VALUES (?, ?, ?, ?, ?)""",
                (name, slug, block_type, html_content, plain_text),
            )
            conn.commit()
            block_id: int = cur.lastrowid
            conn.close()
            logger.info("Created reusable block '%s' (id=%d)", slug, block_id)
            return block_id
        except Exception:
            logger.exception("Failed to create reusable block '%s'", slug)
            conn.close()
            raise

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_block(self, slug: str) -> Optional[dict]:
        """Fetch a single block by slug."""
        conn = self.repo._conn()
        try:
            row = conn.execute(
                "SELECT * FROM reusable_blocks WHERE slug = ?", (slug,)
            ).fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception:
            logger.exception("Failed to fetch block '%s'", slug)
            conn.close()
            return None

    def get_blocks(self, block_type: Optional[str] = None) -> list[dict]:
        """List all blocks, optionally filtered by type."""
        conn = self.repo._conn()
        try:
            if block_type:
                rows = conn.execute(
                    "SELECT * FROM reusable_blocks WHERE block_type = ? ORDER BY name",
                    (block_type,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM reusable_blocks ORDER BY name"
                ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            logger.exception("Failed to list reusable blocks")
            conn.close()
            return []

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_block(self, block_id: int, **fields: object) -> None:
        """Update a block with a field whitelist."""
        filtered = {k: v for k, v in fields.items() if k in self._ALLOWED_FIELDS}
        if not filtered:
            return

        sets = ", ".join(f"{k} = ?" for k in filtered)
        vals = list(filtered.values()) + [block_id]

        conn = self.repo._conn()
        try:
            conn.execute(
                f"UPDATE reusable_blocks SET {sets} WHERE id = ?", vals
            )
            conn.commit()
            conn.close()
            logger.info("Updated reusable block id=%d fields=%s", block_id, list(filtered.keys()))
        except Exception:
            logger.exception("Failed to update block id=%d", block_id)
            conn.close()
            raise

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_block(self, block_id: int) -> None:
        """Delete a block by id."""
        conn = self.repo._conn()
        try:
            conn.execute(
                "DELETE FROM reusable_blocks WHERE id = ?", (block_id,)
            )
            conn.commit()
            conn.close()
            logger.info("Deleted reusable block id=%d", block_id)
        except Exception:
            logger.exception("Failed to delete block id=%d", block_id)
            conn.close()
            raise

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def render_block(self, slug: str) -> str:
        """Return the ``html_content`` for a block, or empty string if not found."""
        block = self.get_block(slug)
        if block:
            return block.get("html_content", "")
        return ""
