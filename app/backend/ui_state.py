"""Work in progress the learner keeps until they delete it, stored as JSON per key:
"lesson:<id>" (answered exercises, own sentences with their checks, unsent drafts) and "exam:<level>"
(a running exam: its questions, the answers so far, the part). The page saves it as the learner works,
so leaving the page, reloading or restarting the app loses nothing."""

import json
import re

from .db import get_conn, now_iso

KEY = re.compile(r"^(lesson|exam):[A-Za-z0-9_-]{1,80}$")
MAX_BYTES = 512 * 1024


def valid_key(key: str) -> bool:
    return bool(KEY.match(key))


def get(key: str):
    with get_conn() as conn:
        row = conn.execute("SELECT value_json FROM ui_state WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value_json"]) if row else None


def put(key: str, value) -> None:
    data = json.dumps(value, ensure_ascii=False)
    if len(data.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Kaydedilecek veri çok büyük.")
    with get_conn() as conn:
        conn.execute("INSERT INTO ui_state (key, value_json, updated_at) VALUES (?, ?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at",
                     (key, data, now_iso()))


def delete(key: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM ui_state WHERE key = ?", (key,))
