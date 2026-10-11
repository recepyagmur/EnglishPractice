"""Saved work in progress (backend/ui_state.py), offline on a temporary database: keys, save / read / delete,
the reset of "Dersler ve sınavlar" removes it, and housekeeping keeps a half-done exam that is saved
(it deletes unsaved ones older than a day). Usage: python ui_state_test.py"""

import asyncio
import os
import sys
import tempfile
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ✓ on a Windows (cp1254) console

os.environ["EP_DATA_DIR"] = tempfile.mkdtemp()  # never the real database
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "app"))

from backend import db, reset, ui_state  # noqa: E402
from backend.db import get_conn  # noqa: E402

db.init_db()
problems = []


def check(ok, what):
    print(("✓ " if ok else "✗ ") + what)
    if not ok:
        problems.append(what)


with get_conn() as conn:
    check(conn.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS), "schema at the latest version")

check(ui_state.valid_key("lesson:a1-be") and ui_state.valid_key("exam:B2"), "lesson / exam keys accepted")
check(not ui_state.valid_key("other:x") and not ui_state.valid_key("lesson:../x"), "other keys refused")
work = {"exercises": {"0": {"type": "choice", "ok": True, "given": "are"}}, "drafts": {"3": "I goes"},
        "result": None, "sentences": [{"question": "What do you do?", "answer": "I'm a nurse.", "result": None}]}
ui_state.put("lesson:a1-be", work)
check(ui_state.get("lesson:a1-be") == work, "saved work read back unchanged (Turkish text too)")
ui_state.put("lesson:a1-be", {**work, "drafts": {}})
check(ui_state.get("lesson:a1-be")["drafts"] == {}, "saving again replaces it")
ui_state.delete("lesson:a1-be")
check(ui_state.get("lesson:a1-be") is None, "deleted")
try:
    ui_state.put("lesson:big", {"x": "a" * (ui_state.MAX_BYTES + 1)})
    check(False, "too large refused")
except ValueError:
    check(True, "too large refused")

# Housekeeping: an old unfinished exam is dropped unless it is saved (the learner left it half done).
old = "2020-01-01T00:00:00+00:00"
with get_conn() as conn:
    saved_id = conn.execute("INSERT INTO exam_attempts (level, started_at, questions_json) VALUES ('A1', ?, '[]')",
                            (old,)).lastrowid
    lost_id = conn.execute("INSERT INTO exam_attempts (level, started_at, questions_json) VALUES ('A2', ?, '[]')",
                           (old,)).lastrowid
ui_state.put("exam:A1", {"exam": {"attempt_id": saved_id, "level": "A1"}, "answers": {}, "step": 1})
db._housekeeping()
with get_conn() as conn:
    left = {r[0] for r in conn.execute("SELECT id FROM exam_attempts")}
check(saved_id in left, "saved half-done exam kept by housekeeping")
check(lost_id not in left, "unsaved old exam removed by housekeeping")

# Reset "lessons" removes the saved work; other groups leave it.
ui_state.put("lesson:a1-be", work)
check(reset.counts()["lessons"] == 1 + 2, "reset count includes saved work (1 attempt + 2 saved)")
asyncio.run(reset.reset(["history"]))
check(ui_state.get("lesson:a1-be") is not None, "history reset keeps lesson work")
asyncio.run(reset.reset(["lessons"]))
check(ui_state.get("lesson:a1-be") is None and ui_state.get("exam:A1") is None, "lessons reset removes saved work")

print("Sorun yok ✓" if not problems else f"{len(problems)} sorun")
sys.exit(1 if problems else 0)
