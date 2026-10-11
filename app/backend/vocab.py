"""Vocabulary notebook with spaced repetition (SM-2)."""

import re
import unicodedata
from datetime import date, timedelta

from .db import get_conn, log_practice, now_iso, rows_to_dicts

# Buttons → SM-2 quality (0-5).
GRADES = {"again": 1, "hard": 3, "good": 5}
MIN_EASE = 1.3


def word_key(word: str) -> str:
    """The same word however it is written: case, accents (café = cafe), apostrophes (’ = ') and spaces do not
    make a second notebook entry. Used when adding (no duplicates) and when matching list words to the notebook."""
    s = unicodedata.normalize("NFKD", word.lower().replace("’", "'").replace("‘", "'"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip()


def find(conn, word: str):
    """The notebook entry for this word (see word_key), or None."""
    row = conn.execute("SELECT * FROM vocab WHERE word = ? COLLATE NOCASE", (word,)).fetchone()
    if row:
        return row
    key = word_key(word)
    for r in conn.execute("SELECT * FROM vocab").fetchall():
        if word_key(r["word"]) == key:
            return r
    return None


def today() -> str:
    return date.today().isoformat()  # local date: "due today" means the learner's day


def add(word: str, meaning_tr: str = "", definition: str = "", example: str = "", context: str = "",
        ipa: str = "", source: str = "manual", session_id: int | None = None,
        level: str | None = None, pos: str | None = None) -> tuple[dict, bool]:
    """Add a word (or phrase). Returns (entry, created); an existing entry is returned as is
    (a word from a level list fills in its level / part of speech if they were missing)."""
    word = " ".join(word.split())
    with get_conn() as conn:
        row = find(conn, word)
        if row:
            if level and not row["level"]:
                conn.execute("UPDATE vocab SET level = ?, pos = COALESCE(pos, ?), meaning_tr = COALESCE(NULLIF(meaning_tr, ''), ?)"
                             " WHERE id = ?", (level, pos, meaning_tr.strip(), row["id"]))
                row = conn.execute("SELECT * FROM vocab WHERE id = ?", (row["id"],)).fetchone()
            return dict(row), False
        cur = conn.execute(
            "INSERT INTO vocab (word, meaning_tr, definition, example, context, ipa, source, source_session_id,"
            " due_date, created_at, level, pos) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (word, meaning_tr.strip(), definition.strip(), example.strip(), context.strip(), ipa or None, source,
             session_id, today(), now_iso(), level, pos),
        )
        row = conn.execute("SELECT * FROM vocab WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row), True


def update(vocab_id: int, fields: dict) -> dict | None:
    allowed = {k: v for k, v in fields.items() if k in ("meaning_tr", "definition", "example")}
    with get_conn() as conn:
        for key, value in allowed.items():
            conn.execute(f"UPDATE vocab SET {key} = ? WHERE id = ?", (str(value).strip(), vocab_id))
        row = conn.execute("SELECT * FROM vocab WHERE id = ?", (vocab_id,)).fetchone()
    return dict(row) if row else None


def delete(vocab_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM vocab WHERE id = ?", (vocab_id,))


def list_all(query: str = "") -> list[dict]:
    with get_conn() as conn:
        if query:
            like = f"%{query.strip()}%"
            rows = conn.execute(
                "SELECT * FROM vocab WHERE word LIKE ? OR meaning_tr LIKE ? ORDER BY id DESC", (like, like)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM vocab ORDER BY id DESC").fetchall()
    return rows_to_dicts(rows)


def contains(words: list[str]) -> list[str]:
    """Which of these words are already in the notebook (case-insensitive)."""
    if not words:
        return []
    with get_conn() as conn:
        marks = ",".join("?" * len(words))
        rows = conn.execute(f"SELECT word FROM vocab WHERE lower(word) IN ({marks})",
                            [w.lower() for w in words]).fetchall()
    return [r["word"] for r in rows]


def due(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM vocab WHERE due_date <= ? ORDER BY due_date, id LIMIT ?", (today(), limit)
        ).fetchall()
    return rows_to_dicts(rows)


def stats() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM vocab").fetchone()[0]
        due_now = conn.execute("SELECT COUNT(*) FROM vocab WHERE due_date <= ?", (today(),)).fetchone()[0]
        learned = conn.execute("SELECT COUNT(*) FROM vocab WHERE interval >= 21").fetchone()[0]
    return {"total": total, "due": due_now, "learned": learned}


def schedule(card: dict, grade: str) -> dict:
    """SM-2: the next ease / interval / repetitions for a review result."""
    q = GRADES[grade]
    ease, interval, reps = float(card["ease"]), int(card["interval"]), int(card["repetitions"])
    if q < 3:
        # Forgotten: start again; it stays due today so the session shows it once more.
        return {"ease": max(MIN_EASE, ease - 0.2), "interval": 0, "repetitions": 0, "lapse": 1}
    reps += 1
    interval = 1 if reps == 1 else 6 if reps == 2 else round(interval * ease)
    if q == 3:
        interval = max(1, round(interval * 0.8))  # "hard": a bit sooner than normal
    ease = max(MIN_EASE, ease + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    return {"ease": round(ease, 2), "interval": interval, "repetitions": reps, "lapse": 0}


def review(vocab_id: int, grade: str) -> dict | None:
    with get_conn() as conn:
        card = conn.execute("SELECT * FROM vocab WHERE id = ?", (vocab_id,)).fetchone()
        if card is None:
            return None
        nxt = schedule(dict(card), grade)
        due_date = (date.today() + timedelta(days=nxt["interval"])).isoformat()
        conn.execute(
            "UPDATE vocab SET ease = ?, interval = ?, repetitions = ?, due_date = ?, last_reviewed_at = ?,"
            " review_count = review_count + 1, lapses = lapses + ? WHERE id = ?",
            (nxt["ease"], nxt["interval"], nxt["repetitions"], due_date, now_iso(), nxt["lapse"], vocab_id),
        )
        row = conn.execute("SELECT * FROM vocab WHERE id = ?", (vocab_id,)).fetchone()
    log_practice("vocab", 0.5)
    return dict(row)
