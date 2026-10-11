"""Progress statistics: totals, daily streak, error categories, weak points.

Timestamps are stored in UTC; days (streak, activity, "last 7 days") are the
learner's local days.
"""

import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from . import errors
from .db import get_conn
from .sessions import TEACHER

ACTIVE_SESSION_GAP_MIN = 10  # a pause longer than this does not count as practice time
WEAK_POINT_LIMIT = 5


def _local_day(iso: str) -> date:
    return datetime.fromisoformat(iso).astimezone().date()


def _words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9'’-]+", text or ""))


def _practice_minutes(timestamps: list[str]) -> float:
    """Practice time of a session: sum of gaps between messages, ignoring long pauses."""
    times = sorted(datetime.fromisoformat(t) for t in timestamps)
    total = 0.0
    for a, b in zip(times, times[1:]):
        gap = (b - a).total_seconds() / 60
        if gap <= ACTIVE_SESSION_GAP_MIN:
            total += gap
    return total + (1 if times else 0)  # count the first exchange as ~1 minute


def overview(days: int = 30) -> dict:
    today = date.today()
    since = today - timedelta(days=days - 1)
    with get_conn() as conn:
        messages = conn.execute(
            "SELECT m.session_id, m.role, m.text, m.meta_json, m.created_at, s.mode"
            " FROM messages m JOIN sessions s ON s.id = m.session_id").fetchall()
        writings = conn.execute("SELECT text, created_at FROM writings WHERE review_json IS NOT NULL").fetchall()
        vocab_rows = conn.execute("SELECT interval FROM vocab").fetchall()
        practice_days = conn.execute("SELECT day, minutes FROM practice_days").fetchall()  # flashcards, lessons
        exams_done = conn.execute("SELECT finished_at FROM exam_attempts WHERE finished_at IS NOT NULL").fetchall()
        err_rows = conn.execute("SELECT category, source, created_at FROM error_log").fetchall()
        sessions = conn.execute("SELECT COUNT(*) FROM sessions WHERE mode != ? AND id IN (SELECT session_id FROM messages)",
                                (TEACHER,)).fetchone()[0]
        checked = conn.execute("SELECT created_at FROM corrections").fetchall()

    # --- totals
    speaking_seconds = 0.0
    user_messages = chat_words = 0
    per_session: dict[int, list[str]] = defaultdict(list)
    activity: dict[date, float] = defaultdict(float)  # local day → minutes
    for m in messages:
        per_session[m["session_id"]].append(m["created_at"])
        if m["role"] != "user" or m["mode"] == TEACHER:  # questions to the teacher are mostly Turkish
            continue
        user_messages += 1
        chat_words += _words(m["text"])
        meta = json.loads(m["meta_json"]) if m["meta_json"] else {}
        speaking_seconds += float(meta.get("audio_seconds") or 0)
        activity[_local_day(m["created_at"])] += 0  # mark the day active
    practice_minutes = 0.0
    for stamps in per_session.values():
        minutes = _practice_minutes(stamps)
        practice_minutes += minutes
        activity[_local_day(min(stamps))] += minutes

    writing_words = sum(_words(w["text"]) for w in writings)
    for w in writings:
        activity[_local_day(w["created_at"])] += max(1, _words(w["text"]) / 15)  # ~15 words/min
    for p in practice_days:
        activity[date.fromisoformat(p["day"])] += p["minutes"]
    for e in exams_done:
        activity[_local_day(e["finished_at"])] += 20

    # --- streak (today counts once there is activity; until then yesterday keeps it alive)
    active_days = set(activity)
    cursor = today if today in active_days else today - timedelta(days=1)
    streak = 0
    while cursor in active_days:
        streak += 1
        cursor -= timedelta(days=1)
    longest = run = 0
    for d in sorted(active_days):
        run = run + 1 if (d - timedelta(days=1)) in active_days else 1
        longest = max(longest, run)

    # --- errors by category in the period (speech vs writing)
    by_cat: dict[str, Counter] = defaultdict(Counter)
    for e in err_rows:
        if _local_day(e["created_at"]) >= since:
            by_cat[e["category"]]["writing" if e["source"] == "writing" else "speech"] += 1
    categories = sorted(
        ({"id": cid, "speech": c["speech"], "writing": c["writing"], "total": c["speech"] + c["writing"]}
         for cid, c in by_cat.items()),
        key=lambda x: -x["total"],
    )
    checked_in_period = sum(1 for c in checked if _local_day(c["created_at"]) >= since)

    return {
        "days": days,
        "totals": {
            "sessions": sessions,
            "practice_minutes": round(practice_minutes),
            "speaking_minutes": round(speaking_seconds / 60, 1),
            "user_messages": user_messages,
            "chat_words": chat_words,
            "writing_words": writing_words,
            "writings": len(writings),
            "vocab_total": len(vocab_rows),
            "vocab_learned": sum(1 for v in vocab_rows if v["interval"] >= 21),
        },
        "streak": {
            "current": streak,
            "longest": longest,
            "today_active": today in active_days,
            "calendar": [
                {"date": (since + timedelta(days=i)).isoformat(),
                 "minutes": round(activity.get(since + timedelta(days=i), 0), 1),
                 "active": (since + timedelta(days=i)) in active_days}
                for i in range(days)
            ],
        },
        "errors": {
            "categories": categories,
            "total": sum(c["total"] for c in categories),
            "checked_sentences": checked_in_period,
        },
    }


def weak_points(days: int = 30) -> list[dict]:
    """Most frequent error categories with real examples and a this-week trend."""
    today = date.today()
    since = today - timedelta(days=days - 1)
    week = today - timedelta(days=6)
    prev_week = today - timedelta(days=13)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT category, source, wrong, right, explanation, created_at FROM error_log ORDER BY id DESC"
        ).fetchall()
    recent = [r for r in rows if _local_day(r["created_at"]) >= since] or rows  # fall back to all time
    counts = Counter(r["category"] for r in recent)
    out = []
    for cid, count in counts.most_common(WEAK_POINT_LIMIT):
        cat_rows = [r for r in recent if r["category"] == cid]
        this_week = sum(1 for r in rows if r["category"] == cid and _local_day(r["created_at"]) >= week)
        last_week = sum(1 for r in rows if r["category"] == cid and prev_week <= _local_day(r["created_at"]) < week)
        examples, seen = [], set()
        for r in cat_rows:
            key = (r["wrong"] or "").lower()
            if key in seen:
                continue
            seen.add(key)
            examples.append({"wrong": r["wrong"], "right": r["right"], "explanation": r["explanation"],
                             "source": r["source"]})
            if len(examples) == 3:
                break
        out.append({
            "category": cid,
            "count": count,
            "this_week": this_week,
            "last_week": last_week,
            "examples": examples,
            "practice": "writing" if cid in errors.WRITTEN_ONLY else "conversation",
        })
    return out
