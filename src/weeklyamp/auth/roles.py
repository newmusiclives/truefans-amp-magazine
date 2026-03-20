"""Role-based access control.

Provides user management with bcrypt password hashing and a simple
four-tier role hierarchy: admin > editor > reviewer > viewer.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import bcrypt

from weeklyamp.core.models import RolesConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)

# Higher numeric level = more privilege.
ROLE_HIERARCHY: dict[str, int] = {
    "viewer": 0,
    "reviewer": 1,
    "editor": 2,
    "admin": 3,
}


class RoleManager:
    """Manage users, passwords, and role-based permissions."""

    def __init__(self, repo: Repository, config: RolesConfig) -> None:
        self.repo = repo
        self.config = config

    # ------------------------------------------------------------------
    # User CRUD
    # ------------------------------------------------------------------

    def create_user(
        self,
        username: str,
        password: str,
        role: str = "viewer",
        display_name: str = "",
        email: str = "",
    ) -> int:
        """Create a new user with a bcrypt-hashed password.

        Returns the new row id.
        """
        if role not in ROLE_HIERARCHY:
            raise ValueError(f"Invalid role '{role}'. Must be one of {list(ROLE_HIERARCHY)}")

        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        conn = self.repo._conn()
        cur = conn.execute(
            """INSERT INTO user_roles
                   (username, password_hash, role, display_name, email)
               VALUES (?, ?, ?, ?, ?)""",
            (username, hashed, role, display_name, email),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        logger.info("Created user '%s' with role '%s' (id=%s)", username, role, row_id)
        return row_id

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        """Verify credentials and update ``last_login_at``.

        Returns the user dict on success, or ``None`` on failure.
        """
        conn = self.repo._conn()
        row = conn.execute(
            "SELECT * FROM user_roles WHERE username = ? AND is_active = 1",
            (username,),
        ).fetchone()

        if not row:
            conn.close()
            logger.warning("Authentication failed: user '%s' not found or inactive", username)
            return None

        user = dict(row)
        stored_hash = user.get("password_hash", "")

        if not bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8")):
            conn.close()
            logger.warning("Authentication failed: bad password for '%s'", username)
            return None

        # Update last login
        conn.execute(
            "UPDATE user_roles SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?",
            (user["id"],),
        )
        conn.commit()
        conn.close()

        # Strip password hash from returned dict
        user.pop("password_hash", None)
        logger.info("User '%s' authenticated successfully", username)
        return user

    def get_user(self, username: str) -> Optional[dict]:
        """Fetch a user by username (excludes password hash)."""
        conn = self.repo._conn()
        row = conn.execute(
            "SELECT * FROM user_roles WHERE username = ?", (username,)
        ).fetchone()
        conn.close()
        if not row:
            return None
        user = dict(row)
        user.pop("password_hash", None)
        return user

    def get_users(self) -> list[dict]:
        """List all active users (password hashes excluded)."""
        conn = self.repo._conn()
        rows = conn.execute(
            "SELECT * FROM user_roles WHERE is_active = 1 ORDER BY username"
        ).fetchall()
        conn.close()
        users = []
        for r in rows:
            u = dict(r)
            u.pop("password_hash", None)
            users.append(u)
        return users

    # ------------------------------------------------------------------
    # Role management
    # ------------------------------------------------------------------

    def update_role(self, username: str, role: str) -> None:
        """Change a user's role."""
        if role not in ROLE_HIERARCHY:
            raise ValueError(f"Invalid role '{role}'. Must be one of {list(ROLE_HIERARCHY)}")

        conn = self.repo._conn()
        conn.execute(
            "UPDATE user_roles SET role = ? WHERE username = ?",
            (role, username),
        )
        conn.commit()
        conn.close()
        logger.info("Updated role for '%s' to '%s'", username, role)

    def deactivate_user(self, username: str) -> None:
        """Soft-delete a user by setting ``is_active = 0``."""
        conn = self.repo._conn()
        conn.execute(
            "UPDATE user_roles SET is_active = 0 WHERE username = ?",
            (username,),
        )
        conn.commit()
        conn.close()
        logger.info("Deactivated user '%s'", username)

    # ------------------------------------------------------------------
    # Permission checks
    # ------------------------------------------------------------------

    def has_permission(self, username: str, required_role: str) -> bool:
        """Return ``True`` if *username*'s role >= *required_role* in the hierarchy."""
        if required_role not in ROLE_HIERARCHY:
            logger.warning("Unknown required role '%s'", required_role)
            return False

        user = self.get_user(username)
        if not user:
            return False

        user_role = user.get("role", "viewer")
        user_level = ROLE_HIERARCHY.get(user_role, 0)
        required_level = ROLE_HIERARCHY.get(required_role, 0)
        return user_level >= required_level
