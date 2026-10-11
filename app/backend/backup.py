"""Consistent copies of data/app.db (SQLite online backup API)."""

import sqlite3
from datetime import date, datetime
from pathlib import Path

from .config import BACKUP_DIR, DB_PATH

KEEP_DAILY = 14
TABLES = ("sessions", "messages", "corrections", "error_log", "writings", "vocab", "settings")


def backup_to(path: Path, db_path: Path = DB_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return path


def backup_now(label: str) -> Path | None:
    """Backup before a risky operation, e.g. backup_now('pre-migration')."""
    if not DB_PATH.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return backup_to(BACKUP_DIR / f"{label}-{stamp}.db")


def daily_backup() -> Path | None:
    """At most one backup per day; keeps the newest KEEP_DAILY of them."""
    if not DB_PATH.exists():
        return None
    target = BACKUP_DIR / f"daily-{date.today():%Y%m%d}.db"
    if target.exists():
        return None
    backup_to(target)
    for old in sorted(BACKUP_DIR.glob("daily-*.db"))[:-KEEP_DAILY]:
        old.unlink(missing_ok=True)
    return target


def row_counts(db_path: Path = DB_PATH) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    try:
        counts = {}
        for table in TABLES:
            try:
                counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.OperationalError:
                counts[table] = 0
        return counts
    finally:
        conn.close()
