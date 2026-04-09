#!/usr/bin/env python3
"""Database backup using pg_dump.

Usage:
    python scripts/backup_db.py                    # Backup to ./backups/
    python scripts/backup_db.py --dir /mnt/backups # Custom directory
    python scripts/backup_db.py --keep 30          # Retain last 30 days (default: 14)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
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


def backup(database_url: str, backup_dir: Path, keep_days: int = 14) -> Path:
    """Run pg_dump and return the path to the backup file."""
    backup_dir.mkdir(parents=True, exist_ok=True)

    db = _parse_database_url(database_url)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"durc_triage_{timestamp}.dump"
    filepath = backup_dir / filename

    env = {**os.environ}
    if db["password"]:
        env["PGPASSWORD"] = db["password"]

    cmd = [
        "pg_dump",
        "-h", db["host"],
        "-p", db["port"],
        "-U", db["user"],
        "-d", db["dbname"],
        "--format=custom",
        f"--file={filepath}",
    ]

    log.info("backup_starting", file=str(filepath), host=db["host"], dbname=db["dbname"])

    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("backup_failed", stderr=result.stderr)
        raise RuntimeError(f"pg_dump failed: {result.stderr}")

    size_mb = filepath.stat().st_size / (1024 * 1024)
    log.info("backup_complete", file=str(filepath), size_mb=round(size_mb, 2))

    # Prune old backups
    _prune(backup_dir, keep_days)

    return filepath


def _prune(backup_dir: Path, keep_days: int) -> None:
    """Delete backup files older than keep_days."""
    cutoff = datetime.now(UTC) - timedelta(days=keep_days)
    pruned = 0
    for f in sorted(backup_dir.glob("durc_triage_*.dump")):
        if datetime.fromtimestamp(f.stat().st_mtime, tz=UTC) < cutoff:
            f.unlink()
            pruned += 1
    if pruned:
        log.info("backup_pruned", count=pruned, keep_days=keep_days)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup DURC triage database")
    parser.add_argument(
        "--dir", default="backups", help="Backup directory (default: ./backups/)"
    )
    parser.add_argument(
        "--keep", type=int, default=14, help="Days to retain backups (default: 14)"
    )
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        log.error("DATABASE_URL not set")
        sys.exit(1)

    backup(database_url, Path(args.dir), args.keep)


if __name__ == "__main__":
    main()
