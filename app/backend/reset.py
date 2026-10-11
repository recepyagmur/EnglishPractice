"""Reset the learner's data from the settings page (each group on its own). A backup is taken first, so a
reset can be undone (README: Yedekler ve geri dönme)."""

from . import backup
from .config import DEFAULT_SETTINGS
from .corrections import worker as correction_worker
from .db import get_conn, vacuum

# Children before parents (foreign keys).
GROUPS = {
    # + the saved work on lesson pages and running exams (ui_state)
    "lessons": {"label": "Dersler, sınavlar ve testler", "tables": ["lesson_progress", "exam_attempts", "selftest_attempts"],
                "state": ["lesson:%", "exam:%"]},
    "words": {"label": "Kelimeler ve kalıplar", "tables": ["vocab", "pattern_progress"]},  # word_examples (checked model output) stays
    "history": {"label": "Konuşma geçmişi ve istatistikler",
                "tables": ["error_log", "corrections", "messages", "sessions", "writings", "practice_days"]},
    "level": {"label": "Seviye", "tables": []},
}


def counts() -> dict[str, int]:
    """Rows per group (shown next to each checkbox)."""
    with get_conn() as conn:
        out = {g: sum(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in spec["tables"])
               + sum(conn.execute("SELECT COUNT(*) FROM ui_state WHERE key LIKE ?", (p,)).fetchone()[0]
                     for p in spec.get("state", []))
               for g, spec in GROUPS.items()}
    return out


async def reset(groups: list[str]) -> dict:
    groups = [g for g in GROUPS if g in groups]
    if not groups:
        raise ValueError("Sıfırlanacak bir şey seçilmedi.")
    path = backup.backup_now("pre-reset")
    deleted = {}
    # No correction may write into history that is being deleted; its queued jobs have no message left.
    async with correction_worker.pause():
        if "history" in groups:
            correction_worker.queue.clear()
        with get_conn() as conn:
            for g in groups:
                deleted[g] = 0
                for table in GROUPS[g]["tables"]:
                    deleted[g] += conn.execute(f"DELETE FROM {table}").rowcount
                for pattern in GROUPS[g].get("state", []):
                    deleted[g] += conn.execute("DELETE FROM ui_state WHERE key LIKE ?", (pattern,)).rowcount
            if "level" in groups:  # asked again on the next page load, as on the first start
                for key in ("level", "level_confirmed"):
                    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, DEFAULT_SETTINGS[key]))
    vacuum()  # give the space back to the disk
    return {"groups": groups, "deleted": deleted, "backup": path.name if path else None}
