"""Consistent copies of data/app.db (SQLite online backup API)."""

import sqlite3
from datetime import date, datetime
from pathlib import Path

from .config import BACKUP_DIR, DB_PATH

KEEP_DAILY = 14
KEEP_DAYS = 30            # before-something backups (pre-…)
KEEP_CONFLICT_DAYS = 90   # the other side's work after a two-computer conflict (cakisma-…)
KEEP_LATEST = 5           # of each kind, always kept whatever their age
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
    """At most one backup per day; keeps the newest KEEP_DAILY of them (and tidies the others: prune())."""
    prune()
    if not DB_PATH.exists():
        return None
    target = BACKUP_DIR / f"daily-{date.today():%Y%m%d}.db"
    if target.exists():
        return None
    backup_to(target)
    for old in sorted(BACKUP_DIR.glob("daily-*.db"))[:-KEEP_DAILY]:
        old.unlink(missing_ok=True)
    return target


def prune(now: datetime | None = None) -> list[str]:
    """Old backups go, so they do not fill the disk: before-something backups (pre-…) after KEEP_DAYS days (the
    newest KEEP_LATEST always stay), copies kept from a two-computer conflict (cakisma-…, the other side's work)
    after KEEP_CONFLICT_DAYS days (the newest KEEP_LATEST stay), and -wal/-shm files left next to backups (SQLite
    creates them when a backup is opened). Daily backups: daily_backup(). Returns the deleted names."""
    if not BACKUP_DIR.exists():
        return []
    now = now or datetime.now()
    deleted = []

    def age_days(p: Path) -> float:
        return (now - datetime.fromtimestamp(p.stat().st_mtime)).total_seconds() / 86400

    for pattern, days in (("pre-*.db", KEEP_DAYS), ("cakisma-*.db", KEEP_CONFLICT_DAYS)):
        files = sorted(BACKUP_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files[KEEP_LATEST:]:
            if age_days(p) > days:
                p.unlink(missing_ok=True)
                deleted.append(p.name)
    for side in [*BACKUP_DIR.glob("*.db-wal"), *BACKUP_DIR.glob("*.db-shm")]:
        db = side.with_name(side.name.rsplit("-", 1)[0])
        if not db.exists() or age_days(side) > 1:
            try:
                side.unlink()
                deleted.append(side.name)
            except OSError:  # open right now (e.g. a backup being read): next time
                pass
    return deleted


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
