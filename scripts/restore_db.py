#!/usr/bin/env python3
"""Database restore using pg_restore.

Usage:
    python scripts/restore_db.py backups/durc_triage_20260409_060000.dump
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import structlog

log = structlog.get_logger()


def _parse_database_url(url: str) -> dict[str, str]:
    """Extract host, port, dbname, user, password from a DATABASE_URL."""
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "dbname": parsed.path.lstrip("/"),
        "user": parsed.username or "",
        "password": parsed.password or "",
    }


def restore(database_url: str, backup_file: Path) -> None:
    """Run pg_restore from a backup file."""
    if not backup_file.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_file}")

    db = _parse_database_url(database_url)
    env = {**os.environ}
    if db["password"]:
        env["PGPASSWORD"] = db["password"]

    cmd = [
        "pg_restore",
        "-h", db["host"],
        "-p", db["port"],
        "-U", db["user"],
        "-d", db["dbname"],
        "--clean",
        "--if-exists",
        "--no-owner",
        str(backup_file),
    ]

    log.info("restore_starting", file=str(backup_file), host=db["host"], dbname=db["dbname"])

    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    # pg_restore returns non-zero on warnings too; only fail on actual errors
    if result.returncode != 0 and "ERROR" in result.stderr:
        log.error("restore_failed", stderr=result.stderr)
        raise RuntimeError(f"pg_restore failed: {result.stderr}")

    log.info("restore_complete", file=str(backup_file))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Restore DURC triage database from backup"
    )
    parser.add_argument("file", type=Path, help="Path to backup file (.dump)")
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        log.error("DATABASE_URL not set")
        sys.exit(1)

    restore(database_url, args.file)


if __name__ == "__main__":
    main()
