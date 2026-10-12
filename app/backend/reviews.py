"""Reviewing finished lessons: summary cards, spaced review and routing by the learner's mistakes.

Spacing effect + retrieval practice: a finished lesson comes back after growing intervals (REVIEW_DAYS); a review
is a glance at the lesson's summary card, then a short quiz of the lesson's own exercises (the ones answered
wrongly before first). A good result moves the lesson one step further, a middling one repeats the interval, a
poor one starts over (and suggests going through the lesson again). Frequent mistakes in a topic (errors.py
categories: conversation/writing corrections, review quizzes) bring that topic's finished lessons forward.

The summary cards (app/content/review/<LEVEL>.json, README there) are hand-written and checked like the lessons:
only rules_tr / remember_tr are new text; the table and the mistakes are picked from the lesson by index.
"""

import json
import random
import re
from datetime import date, datetime, timedelta, timezone

from . import errors
from .config import APP_DIR
from .db import get_conn, log_practice, now_iso
from .lessons import BY_ID

CONTENT_DIR = APP_DIR / "content" / "review"
TERM_MARK = re.compile(r"\[(en|tr|key):([^\[\]]+)\]")
TURKISH_LETTERS = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
RULES = (3, 5)
RULE_LEN = (40, 260)
REMEMBER_LEN = (20, 160)
MISTAKES = (2, 3)
TABLE_ROWS = 9


# ------------------------------------------------------------------ content

def load_content(levels=None) -> dict[str, dict]:
    """lesson id → summary card, from every level file (or the given ones)."""
    from .lessons import LEVELS

    out = {}
    for level in levels or LEVELS:
        path = CONTENT_DIR / f"{level}.json"
        if path.exists():
            out.update(json.loads(path.read_text(encoding="utf-8"))["reviews"])
    return out


def _text_problems(where: str, text) -> list[str]:
    if not isinstance(text, str) or not text.strip():
        return [f"{where}: boş ya da metin değil"]
    problems = []
    if re.search(r"\[[a-z]+:", TERM_MARK.sub("", text)):
        problems.append(f"{where}: bozuk işaretleme: {text[:80]}")
    if re.search(r"[\"“”]", text):
        problems.append(f"{where}: tırnak yerine [en:…] / [tr:…] kullan: {text[:80]}")
    for kind, inner in TERM_MARK.findall(text):
        if kind == "en" and TURKISH_LETTERS.search(inner):
            problems.append(f"{where}: [en:…] içinde Türkçe harf: {inner}")
    # A quoted Turkish example ([tr:sen / siz]) is not the card speaking.
    if re.search(r"\bsiz(?:in|e|i)?\b|\b\w+(?:iniz|ınız|unuz|ünüz)\b", TERM_MARK.sub("", text), re.I):
        problems.append(f"{where}: 'siz' dili olabilir (dersler 'sen' diliyle): {text[:80]}")
    return problems


def validate_content(cards: dict[str, dict], lessons: list[dict]) -> list[str]:
    """Problems in summary cards against these lessons (every lesson must have a card)."""
    problems = []
    by_id = {l["id"]: l for l in lessons}
    for lid in by_id:
        if lid not in cards:
            problems.append(f"{lid}: özet yok")
    for lid, card in cards.items():
        lesson = by_id.get(lid)
        if lesson is None:
            problems.append(f"{lid}: böyle bir ders yok")
            continue
        extra = set(card) - {"rules_tr", "remember_tr", "table", "mistakes"}
        if extra:
            problems.append(f"{lid}: bilinmeyen alan(lar): {sorted(extra)}")
        rules = card.get("rules_tr")
        if not isinstance(rules, list) or not RULES[0] <= len(rules) <= RULES[1]:
            problems.append(f"{lid}: rules_tr {RULES[0]}–{RULES[1]} madde olmalı")
            rules = rules if isinstance(rules, list) else []
        for i, rule in enumerate(rules):
            problems += _text_problems(f"{lid} rules_tr[{i}]", rule)
            if isinstance(rule, str) and not RULE_LEN[0] <= len(TERM_MARK.sub(r"\2", rule)) <= RULE_LEN[1]:
                problems.append(f"{lid} rules_tr[{i}]: {RULE_LEN[0]}–{RULE_LEN[1]} karakter olmalı ({len(rule)})")
        if len(set(map(str, rules))) != len(rules):
            problems.append(f"{lid}: aynı madde iki kez")
        remember = card.get("remember_tr")
        problems += _text_problems(f"{lid} remember_tr", remember)
        if isinstance(remember, str) and not REMEMBER_LEN[0] <= len(TERM_MARK.sub(r"\2", remember)) <= REMEMBER_LEN[1]:
            problems.append(f"{lid} remember_tr: {REMEMBER_LEN[0]}–{REMEMBER_LEN[1]} karakter olmalı")
        table = card.get("table", "missing")
        if table == "missing":
            problems.append(f"{lid}: table alanı yok (tablo yoksa null)")
        elif table is not None:
            sections = lesson.get("sections", [])
            if not (isinstance(table, int) and 0 <= table < len(sections) and sections[table].get("table")):
                problems.append(f"{lid}: table={table} tablolu bir bölüm değil")
            elif len(sections[table]["table"]["rows"]) > TABLE_ROWS:
                problems.append(f"{lid}: table={table} {TABLE_ROWS} satırdan uzun")
        picked = card.get("mistakes")
        n = len(lesson.get("mistakes", []))
        if not (isinstance(picked, list) and MISTAKES[0] <= len(picked) <= min(MISTAKES[1], n)
                and all(isinstance(i, int) and 0 <= i < n for i in picked) and len(set(picked)) == len(picked)):
            problems.append(f"{lid}: mistakes {MISTAKES[0]}–{MISTAKES[1]} geçerli, tekrarsız sıra olmalı (dersin {n} hatası var)")
    return problems


def card(lesson: dict, cards: dict[str, dict] | None = None) -> dict | None:
    """The summary card of a lesson as the page shows it (None when it has none yet)."""
    c = (cards if cards is not None else CARDS).get(lesson["id"])
    if not c:
        return None
    sections = lesson.get("sections", [])
    table = sections[c["table"]]["table"] if c.get("table") is not None and c["table"] < len(sections) else None
    return {"rules_tr": c["rules_tr"], "remember_tr": c["remember_tr"], "table": table,
            "mistakes": [lesson["mistakes"][i] for i in c["mistakes"] if i < len(lesson.get("mistakes", []))]}


CARDS = load_content()


# ----------------------------------------------------------------- schedule

REVIEW_DAYS = [1, 3, 7, 14, 30, 60, 120]  # days until the next review, per step
GOOD, OK = 0.8, 0.5        # quiz score: ≥ GOOD next step; ≥ OK same interval again; below: back to the start
QUIZ_SIZE = 6
NEW_PER_DAY = 2            # finished lessons entering review late (e.g. before this feature) are spread out
WEAK_DAYS, WEAK_MIN = 14, 3  # a topic with ≥ WEAK_MIN corrected mistakes in WEAK_DAYS days is "weak"
PULL_GAP = 3               # a weak topic's lesson is brought forward when not reviewed in this many days


def _today() -> date:
    return date.today()


def ensure_scheduled() -> None:
    """Every finished lesson has a review schedule (the first review the day after it was finished; lessons
    finished long ago — or on the other computer — are spread over the coming days, NEW_PER_DAY a day)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT p.lesson_id, p.completed_at FROM lesson_progress p LEFT JOIN lesson_review r "
            "ON r.lesson_id = p.lesson_id WHERE p.completed_at IS NOT NULL AND r.lesson_id IS NULL "
            "ORDER BY p.completed_at").fetchall()
        late = 0
        for r in rows:
            if r["lesson_id"] not in BY_ID:
                continue
            finished = datetime.fromisoformat(r["completed_at"]).astimezone().date()
            due = finished + timedelta(days=REVIEW_DAYS[0])
            if due < _today():
                due = _today() + timedelta(days=late // NEW_PER_DAY)
                late += 1
            conn.execute("INSERT INTO lesson_review (lesson_id, step, due_date, created_at) VALUES (?, 0, ?, ?)",
                         (r["lesson_id"], due.isoformat(), now_iso()))


def weak_topics() -> dict[str, int]:
    """Error categories (errors.py) with frequent recent mistakes: category → count."""
    since = (datetime.now(timezone.utc) - timedelta(days=WEAK_DAYS)).isoformat(timespec="seconds")
    with get_conn() as conn:
        rows = conn.execute("SELECT category, COUNT(*) AS n FROM error_log WHERE created_at >= ? "
                            "GROUP BY category HAVING n >= ? ORDER BY n DESC", (since, WEAK_MIN)).fetchall()
    return {r["category"]: r["n"] for r in rows if r["category"] != "other"}


def _rows() -> dict[str, dict]:
    with get_conn() as conn:
        return {r["lesson_id"]: dict(r) for r in conn.execute("SELECT * FROM lesson_review")}


def _item(lesson: dict, row: dict, reason: str = "") -> dict:
    return {"lesson_id": lesson["id"], "title_tr": lesson["title_tr"], "title_en": lesson["title_en"],
            "level": lesson["level"], "step": row["step"], "steps": len(REVIEW_DAYS), "due_date": row["due_date"],
            "review_count": row["review_count"], "last_reviewed_at": row["last_reviewed_at"],
            "last_score": row["last_score"], "reason": reason}


def overview() -> dict:
    """Reviews due today (and those brought forward by weak topics), the next ones, the weak topics."""
    ensure_scheduled()
    today = _today()
    rows = _rows()
    weak = weak_topics()
    due, soon = [], []
    for lid, row in rows.items():
        lesson = BY_ID.get(lid)
        if lesson is None:
            continue
        due_day = date.fromisoformat(row["due_date"])
        if due_day <= today:
            late = (today - due_day).days
            due.append(_item(lesson, row, f"{late} gün gecikti" if late > 1 else ""))
            continue
        hits = [c for c in lesson["categories"] if c in weak]
        reviewed = row["last_reviewed_at"] or row["created_at"]
        rested = (today - datetime.fromisoformat(reviewed).astimezone().date()).days >= PULL_GAP
        if hits and rested:
            c = max(hits, key=weak.get)
            due.append(_item(lesson, row, f"öne alındı: {errors.BY_ID[c]['tr']} hataların arttı ({weak[c]})")
                       | {"pulled": True})
        else:
            soon.append(_item(lesson, row))
    due.sort(key=lambda x: (x.get("pulled", False), x["due_date"]))
    soon.sort(key=lambda x: x["due_date"])
    return {"due": due, "soon": soon[:5], "count": len(due),
            "weak": [{"category": c, "label": errors.BY_ID[c]["tr"], "count": n} for c, n in weak.items()
                     if c in errors.BY_ID]}


def due_count() -> int:
    return overview()["count"]


def _json_list(value) -> list[int]:
    try:
        return [int(i) for i in json.loads(value or "[]")]
    except (ValueError, TypeError):
        return []


def pick_quiz(lesson: dict, row: dict | None, rng: random.Random | None = None) -> list[int]:
    """QUIZ_SIZE exercise indices: first the ones answered wrongly before (in reviews, then on the lesson page),
    then ones the last review did not ask, then any; in lesson order."""
    rng = rng or random.Random()
    n = len(lesson["exercises"])
    with get_conn() as conn:
        saved = conn.execute("SELECT value_json FROM ui_state WHERE key = ?", (f"lesson:{lesson['id']}",)).fetchone()
    try:
        page = json.loads(saved["value_json"]).get("exercises", {}) if saved else {}
    except (ValueError, AttributeError):
        page = {}
    wrong_page = [int(i) for i, a in page.items() if str(i).isdigit() and not a.get("ok")
                  and int(i) < n and a.get("type") == lesson["exercises"][int(i)]["type"]]
    wrong_review = _json_list(row and row.get("wrong_items"))
    last = set(_json_list(row and row.get("last_items")))
    picked: list[int] = []
    for group in (wrong_review, wrong_page):
        for i in group:
            if 0 <= i < n and i not in picked and len(picked) < QUIZ_SIZE // 2:  # at most half: also new ones
                picked.append(i)
    fresh = [i for i in range(n) if i not in picked and i not in last]
    rest = [i for i in range(n) if i not in picked and i in last]
    rng.shuffle(fresh)
    rng.shuffle(rest)
    picked += (fresh + rest)[:QUIZ_SIZE - len(picked)]
    return sorted(picked)


def start(lesson_id: str) -> dict | None:
    """A review: the lesson's summary card and a short quiz of its own exercises."""
    lesson = BY_ID.get(lesson_id)
    if lesson is None:
        return None
    ensure_scheduled()
    row = _rows().get(lesson_id)
    items = pick_quiz(lesson, row)
    return {"lesson_id": lesson_id, "title_tr": lesson["title_tr"], "title_en": lesson["title_en"],
            "level": lesson["level"], "card": card(lesson),
            "state": _item(lesson, row) if row else None, "steps": len(REVIEW_DAYS),
            "items": items, "exercises": [lesson["exercises"][i] for i in items]}


def record(lesson_id: str, items: list[int], wrong: list[int]) -> dict:
    """The result of a review quiz: the next date on the ladder, and advice."""
    lesson = BY_ID.get(lesson_id)
    if lesson is None:
        raise ValueError("Ders bulunamadı.")
    n = len(lesson["exercises"])
    items = sorted({i for i in items if 0 <= i < n})
    wrong = sorted({i for i in wrong if i in items})
    if not items:
        raise ValueError("Cevaplanan soru yok.")
    score = (len(items) - len(wrong)) / len(items)
    ensure_scheduled()
    row = _rows().get(lesson_id) or {"step": 0, "lapses": 0, "wrong_items": None}
    step = row["step"]
    if score >= GOOD:
        step = min(step + 1, len(REVIEW_DAYS) - 1)
        advice = "good"
    elif score >= OK:
        advice = "again"   # the same interval once more
    else:
        step = 0
        advice = "relearn"  # go through the lesson again
    days = REVIEW_DAYS[step]
    due = (_today() + timedelta(days=days)).isoformat()
    # Wrong answers are asked again next time; right ones leave that list.
    earlier = [i for i in _json_list(row.get("wrong_items")) if i not in items]
    wrong_items = (wrong + earlier)[:QUIZ_SIZE]
    now = now_iso()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO lesson_review (lesson_id, step, due_date, created_at, last_reviewed_at, last_score, "
            "review_count, lapses, last_items, wrong_items) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?) "
            "ON CONFLICT(lesson_id) DO UPDATE SET step = excluded.step, due_date = excluded.due_date, "
            "last_reviewed_at = excluded.last_reviewed_at, last_score = excluded.last_score, "
            "review_count = review_count + 1, lapses = lapses + ?, last_items = excluded.last_items, "
            "wrong_items = excluded.wrong_items",
            (lesson_id, step, due, now, now, score, int(advice == "relearn"), json.dumps(items),
             json.dumps(wrong_items), int(advice == "relearn")))
    log_practice("review", 0.5 * len(items))
    return {"score": score, "correct": len(items) - len(wrong), "total": len(items), "step": step,
            "steps": len(REVIEW_DAYS), "days": days, "due_date": due, "advice": advice}
