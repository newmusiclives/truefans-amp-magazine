"""Round-trip test for encrypted backup → restore.

Guards the encryption/compression pipeline against regressions. The
happy-path assertion is not "it encrypts" (any library call will do
that) — it's "the bytes that come out of restore exactly match the
bytes that went into backup". If we silently truncate, drop a file,
or swap compression algorithms, this test fails.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture()
def backup_key() -> str:
    from weeklyamp.export.backup import ExportManager
    return ExportManager.generate_backup_key()


def test_encrypted_backup_round_trip(tmp_db, tmp_path, backup_key):
    from weeklyamp.core.config import load_config
    from weeklyamp.db.repository import Repository
    from weeklyamp.export.backup import ExportManager

    repo = Repository(tmp_db)
    # Insert a subscriber so exported CSV has a row to round-trip
    repo.upsert_subscriber(email="test@example.com", status="active")

    config = load_config()
    exporter = ExportManager(repo, config)

    encrypted_path = exporter.encrypted_full_backup(str(tmp_path), key=backup_key)
    assert os.path.exists(encrypted_path)
    assert encrypted_path.endswith(".enc")

    # Encrypted file should not contain plaintext identifiers
    with open(encrypted_path, "rb") as f:
        ciphertext = f.read()
    assert b"test@example.com" not in ciphertext
    assert b"subscribers.csv" not in ciphertext  # archive filenames also encrypted

    # Restore to a separate directory — simulates disaster recovery.
    restore_dir = tmp_path / "restored"
    ExportManager.restore_encrypted_backup(
        encrypted_path, str(restore_dir), key=backup_key
    )

    assert (restore_dir / "subscribers.csv").exists()
    assert (restore_dir / "content.json").exists()
    assert (restore_dir / "config.yaml").exists()

    csv_content = (restore_dir / "subscribers.csv").read_text()
    assert "test@example.com" in csv_content


def test_encrypted_backup_rejects_wrong_key(tmp_db, tmp_path, backup_key):
    from weeklyamp.core.config import load_config
    from weeklyamp.db.repository import Repository
    from weeklyamp.export.backup import ExportManager
    from cryptography.fernet import InvalidToken

    config = load_config()
    exporter = ExportManager(Repository(tmp_db), config)
    encrypted_path = exporter.encrypted_full_backup(str(tmp_path), key=backup_key)

    # Attempting restore with a different key must fail loudly.
    wrong_key = ExportManager.generate_backup_key()
    with pytest.raises(InvalidToken):
        ExportManager.restore_encrypted_backup(
            encrypted_path, str(tmp_path / "wrong"), key=wrong_key
        )


def test_encrypted_backup_requires_key(tmp_db, tmp_path, monkeypatch):
    """No env var + no explicit key → refuse to write plaintext fallback."""
    from weeklyamp.core.config import load_config
    from weeklyamp.db.repository import Repository
    from weeklyamp.export.backup import ExportManager

    monkeypatch.delenv("WEEKLYAMP_BACKUP_KEY", raising=False)
    config = load_config()
    exporter = ExportManager(Repository(tmp_db), config)
    with pytest.raises(ValueError, match="WEEKLYAMP_BACKUP_KEY"):
        exporter.encrypted_full_backup(str(tmp_path))
