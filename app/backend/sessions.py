"""Session and message persistence helpers."""

import json

from .db import get_conn, now_iso, rows_to_dicts


TEACHER = "teacher"  # Turkish teacher sessions: listed on their own page, not in practice statistics


def create_session(mode: str, scenario: dict | None = None, context: dict | None = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO sessions (mode, scenario, scenario_json, context_json, started_at) VALUES (?, ?, ?, ?, ?)",
            (mode, scenario["id"] if scenario else None,
             json.dumps(scenario, ensure_ascii=False) if scenario else None,
             json.dumps(context, ensure_ascii=False) if context else None, now_iso()),
        )
        return cur.lastrowid


def context_of(session_id: int) -> dict | None:
    """What a teacher session was opened from (None: a plain question)."""
    with get_conn() as conn:
        row = conn.execute("SELECT context_json FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return json.loads(row["context_json"]) if row and row["context_json"] else None


def mode_of(session_id: int) -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT mode FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return row["mode"] if row else None


def session_exists(session_id: int) -> bool:
    with get_conn() as conn:
        return conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone() is not None


def scenario_of(session_id: int) -> dict | None:
    """The full scenario definition of a role-play session (None for free conversation)."""
    with get_conn() as conn:
        row = conn.execute("SELECT scenario_json FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return json.loads(row["scenario_json"]) if row and row["scenario_json"] else None


def add_message(session_id: int, role: str, text: str, meta: dict | None = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO messages (session_id, role, text, meta_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, role, text, json.dumps(meta) if meta else None, now_iso()),
        )
        return cur.lastrowid


def delete_message(message_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))


def recent_messages(session_id: int, limit: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, text FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [{"role": r["role"], "content": r["text"]} for r in reversed(rows)]


def all_messages(session_id: int) -> list[dict]:
    """Messages for the UI. Spoken messages carry Whisper's per-word confidence
    ("words": [{word, probability}]) for the pronunciation hints."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, role, text, meta_json, created_at FROM messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
    messages = []
    for m in rows_to_dicts(rows):
        meta = json.loads(m.pop("meta_json") or "{}")
        if meta.get("words"):
            m["words"] = [{"word": w["word"], "probability": w["probability"]} for w in meta["words"]]
        messages.append(m)
    return messages


def end_session(session_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET ended_at = ? WHERE id = ? AND ended_at IS NULL",
            (now_iso(), session_id),
        )


def save_summary(session_id: int, summary: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET summary_json = ?, ended_at = COALESCE(ended_at, ?) WHERE id = ?",
            (json.dumps(summary, ensure_ascii=False), now_iso(), session_id),
        )


def _with_scenario_title(session: dict) -> dict:
    scenario = json.loads(session.pop("scenario_json") or "null")
    session["scenario_title"] = scenario["title_tr"] if scenario else None
    return session


def list_sessions(limit: int = 200, teacher: bool = False) -> list[dict]:
    """Practice sessions (conversation, scenario), or with teacher=True only the teacher's."""
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT s.id, s.mode, s.scenario, s.scenario_json, s.context_json, s.started_at, s.ended_at,
                   s.summary_json IS NOT NULL AS has_summary,
                   COUNT(m.id) AS message_count, MAX(m.created_at) AS last_message_at,
                   (SELECT text FROM messages WHERE session_id = s.id AND role = 'user' ORDER BY id LIMIT 1)
                       AS first_question
            FROM sessions s LEFT JOIN messages m ON m.session_id = s.id
            WHERE s.mode {"=" if teacher else "!="} ?
            GROUP BY s.id
            HAVING message_count > 0
            ORDER BY s.id DESC LIMIT ?
            """,
            (TEACHER, limit),
        ).fetchall()
    out = []
    for r in rows:
        session = _with_scenario_title(dict(r))
        session["context"] = json.loads(session.pop("context_json") or "null")
        if not teacher:
            session.pop("first_question")
        out.append(session)
    return out


def get_session(session_id: int) -> dict | None:
    with get_conn() as conn:
        session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if session is None:
        return None
    session = dict(session)
    scenario = json.loads(session.pop("scenario_json") or "null")
    session["scenario"] = scenario
    session["context"] = json.loads(session.pop("context_json") or "null")
    session["summary"] = json.loads(session.pop("summary_json") or "null")
    session["messages"] = all_messages(session_id)
    return session


def delete_session(session_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
