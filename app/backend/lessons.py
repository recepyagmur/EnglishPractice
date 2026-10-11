"""Structured lessons by level (A1–C1).

The content is hand-written (Turkish explanations, examples, typical mistakes of
Turkish learners, exercises) and lives in app/content/lessons/<LEVEL>.json — the
local LLM's Turkish is not reliable enough to write explanations. The LLM is only
used in English: questions for "build your own sentences" (answers are checked by
the correction engine) and the conversation practice.

Lesson ids are stable (progress is stored by id): never rename or reuse one.
Each lesson lists the error categories (errors.py ids) it teaches, so weak points
can point to the right lesson.
"""

import json
import logging
import re

from . import errors, llm_models, ollama_client
from .config import APP_DIR
from .corrections import worker as correction_worker
from .db import get_conn, log_practice, now_iso
from .settings_store import get_level

log = logging.getLogger("app")

LEVELS = ["A1", "A2", "B1", "B2", "C1"]
CONTENT_DIR = APP_DIR / "content" / "lessons"
COMPLETE_AT = 0.8  # share of correct exercise answers that marks a lesson as done
EXERCISE_TYPES = {"choice", "fill", "fix", "transform", "order", "match", "listen"}


def _load() -> list[dict]:
    lessons = []
    for level in LEVELS:
        path = CONTENT_DIR / f"{level}.json"
        if not path.exists():
            continue
        for order, lesson in enumerate(json.loads(path.read_text(encoding="utf-8"))["lessons"], 1):
            lessons.append({**lesson, "level": level, "order": order})
    return lessons


def validate(lessons: list[dict]) -> list[str]:
    """Content mistakes (used by the content test and logged at start-up)."""
    problems, seen = [], set()
    for l in lessons:
        where = l.get("id", "?")
        if l.get("id") in seen:
            problems.append(f"{where}: duplicate id")
        seen.add(l.get("id"))
        for key in ("id", "title_tr", "title_en", "categories", "sections", "exercises", "practice"):
            if not l.get(key):
                problems.append(f"{where}: missing {key}")
        problems += [f"{where}: unknown category {c}" for c in l.get("categories", []) if c not in errors.BY_ID]
        for s in l.get("sources", []):
            if not str(s.get("url", "")).startswith("https://") or not s.get("title"):
                problems.append(f"{where}: bad source {s}")
        for i, ex in enumerate(l.get("exercises", []), 1):
            if ex.get("type") not in EXERCISE_TYPES:
                problems.append(f"{where} #{i}: unknown type {ex.get('type')}")
            elif ex["type"] == "choice" and not (0 <= ex.get("answer", -1) < len(ex.get("options", []))):
                problems.append(f"{where} #{i}: answer index out of range")
            elif ex["type"] in ("fill", "fix", "transform", "order", "listen") and not (
                    isinstance(ex.get("answer"), list) and ex["answer"]):
                problems.append(f"{where} #{i}: answer must be a non-empty list")
            if ex.get("type") == "fill" and "___" not in ex.get("q", ""):
                problems.append(f"{where} #{i}: fill question without ___")
            if ex.get("type") == "transform" and not (ex.get("instruction_tr") and ex.get("q")):
                problems.append(f"{where} #{i}: transform needs instruction_tr and q")
            if ex.get("type") == "listen" and not ex.get("text"):
                problems.append(f"{where} #{i}: listen needs text")
            if ex.get("type") == "order":
                tiles = ex.get("words") or []
                if len(tiles) < 3:
                    problems.append(f"{where} #{i}: order needs at least 3 tiles")
                elif ex.get("answer") and _tokens(" ".join(tiles)) != _tokens(ex["answer"][0]):
                    problems.append(f"{where} #{i}: the tiles do not make the first answer")
            if ex.get("type") == "match":
                pairs = ex.get("pairs") or []
                if len(pairs) < 3 or any(len(p) != 2 or not all(p) for p in pairs):
                    problems.append(f"{where} #{i}: match needs at least 3 [english, turkish] pairs")
                elif len({p[0].lower() for p in pairs}) != len(pairs) or len({p[1].lower() for p in pairs}) != len(pairs):
                    problems.append(f"{where} #{i}: match pairs must be unique on both sides")
    return problems


TERM_MARK = re.compile(r"\[(en|tr|key):([^\[\]]+)\]")


def plain(text: str) -> str:
    """Content text for the LLM: the term markup ([en:does], shown as chips in the app) as quotes."""
    return TERM_MARK.sub(lambda m: f'"{m.group(2)}"', text)


def _tokens(text: str) -> list[str]:
    """Words of a sentence, order-free (for checking that order tiles make the answer)."""
    return sorted(re.findall(r"[a-z0-9']+", text.lower().replace("’", "'")))


LESSONS = _load()
BY_ID = {l["id"]: l for l in LESSONS}
for _problem in validate(LESSONS):
    log.warning("lesson content: %s", _problem)


# ---------------------------------------------------------------- progress

def _progress() -> dict[str, dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM lesson_progress").fetchall()
    return {r["lesson_id"]: dict(r) for r in rows}


def _status(p: dict | None) -> dict:
    if not p:
        return {"status": "new", "best_score": None}
    status = "done" if p["completed_at"] else "started"
    return {"status": status, "best_score": p["best_score"]}


def summary(lesson: dict, progress: dict | None = None) -> dict:
    return ({k: lesson[k] for k in ("id", "level", "order", "title_tr", "title_en", "categories")}
            | {"tags": lesson.get("tags", [])} | _status(progress))


def level_index(level: str) -> int:
    return LEVELS.index(level) if level in LEVELS else LEVELS.index("B1")


def for_category(category: str, progress: dict | None = None, limit: int = 2) -> list[dict]:
    """Lessons that teach this error category, up to the learner's level; unfinished first."""
    progress = _progress() if progress is None else progress
    top = level_index(get_level())
    matches = [l for l in LESSONS if category in l["categories"] and level_index(l["level"]) <= top]
    matches.sort(key=lambda l: (bool((progress.get(l["id"]) or {}).get("completed_at")), level_index(l["level"]),
                                l["order"]))
    return [summary(l, progress.get(l["id"])) for l in matches[:limit]]


def recommended(progress: dict, limit: int = 3) -> list[dict]:
    """Lessons for the learner's frequent mistakes, then the next unfinished lesson of their level."""
    from .progress import weak_points  # progress imports nothing from here; keep it lazy anyway

    out, ids = [], set()
    for w in weak_points(30):
        for l in for_category(w["category"], progress, limit=1):
            if l["status"] != "done" and l["id"] not in ids:
                ids.add(l["id"])
                out.append({**l, "reason": f"Sık yaptığın hata: {errors.BY_ID[w['category']]['tr']} ({w['count']})"})
    # The next unfinished lesson of the learner's level; if that level has none (yet), of the level below.
    level = get_level()
    for lv in reversed(LEVELS[:level_index(level) + 1]):
        nxt = next((l for l in LESSONS if l["level"] == lv and l["id"] not in ids
                    and not (progress.get(l["id"]) or {}).get("completed_at")), None)
        if nxt:
            reason = f"Seviyendeki ({level}) sıradaki ders" if lv == level else f"{lv} seviyesinin sıradaki dersi"
            out.append({**summary(nxt, progress.get(nxt["id"])), "reason": reason})
            break
    return out[:limit]


def overview() -> dict:
    progress = _progress()
    return {
        "level": get_level(),
        "levels": [{"id": lv, "count": sum(1 for l in LESSONS if l["level"] == lv),
                    "done": sum(1 for l in LESSONS if l["level"] == lv and (progress.get(l["id"]) or {}).get("completed_at"))}
                   for lv in LEVELS],
        "lessons": [summary(l, progress.get(l["id"])) for l in LESSONS],
        "recommended": recommended(progress),
    }


def open_lesson(lesson_id: str) -> dict | None:
    lesson = BY_ID.get(lesson_id)
    if lesson is None:
        return None
    now = now_iso()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO lesson_progress (lesson_id, first_opened_at, last_opened_at) VALUES (?, ?, ?) "
            "ON CONFLICT(lesson_id) DO UPDATE SET last_opened_at = excluded.last_opened_at",
            (lesson_id, now, now),
        )
    level_lessons = [l for l in LESSONS if l["level"] == lesson["level"]]
    i = level_lessons.index(lesson)
    nxt = level_lessons[i + 1] if i + 1 < len(level_lessons) else None
    return {**lesson, **_status(_progress().get(lesson_id)),
            "category_labels": [errors.BY_ID[c]["tr"] for c in lesson["categories"]],
            "next": {"id": nxt["id"], "title_tr": nxt["title_tr"]} if nxt else None}


def save_result(lesson_id: str, correct: int, total: int) -> dict:
    """Exercise result: keeps the best score; ≥ 80 % completes the lesson."""
    score = correct / total if total else 0
    now = now_iso()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO lesson_progress (lesson_id, first_opened_at, last_opened_at) VALUES (?, ?, ?) "
            "ON CONFLICT(lesson_id) DO NOTHING", (lesson_id, now, now))
        conn.execute(
            "UPDATE lesson_progress SET attempts = attempts + 1, last_score = ?, "
            "best_score = MAX(COALESCE(best_score, 0), ?), "
            "completed_at = COALESCE(completed_at, CASE WHEN ? >= ? THEN ? END) WHERE lesson_id = ?",
            (score, score, score, COMPLETE_AT, now, lesson_id),
        )
    log_practice("lesson", 0.5 * total)  # ~30 s per exercise
    return _status(_progress().get(lesson_id)) | {"score": score}


def reset(lesson_id: str) -> None:
    """Forget a lesson's progress (score, completion)."""
    with get_conn() as conn:
        conn.execute("DELETE FROM lesson_progress WHERE lesson_id = ?", (lesson_id,))


def practice_started(lesson_id: str) -> None:
    now = now_iso()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO lesson_progress (lesson_id, first_opened_at, last_opened_at, practice_count) "
            "VALUES (?, ?, ?, 1) ON CONFLICT(lesson_id) DO UPDATE SET practice_count = practice_count + 1",
            (lesson_id, now, now),
        )


# --------------------------------------------------- "build your own sentences"

PROMPTS = """You are an English teacher. A Turkish learner (CEFR {level}) has just studied this grammar topic: "{topic}".
Write {n} short questions or instructions in simple English ({level} level). Each one must make the learner answer with ONE sentence that uses this structure ({focus}).
Use different everyday situations (home, work, family, friends, travel, hobbies, food). Do not give the answers and do not say which words or forms to use — the learner must choose them. No numbering.
Return JSON: {{"items": ["...", "..."]}}"""

PROMPTS_SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "string"}}},
                  "required": ["items"]}


async def sentence_prompts(lesson_id: str, n: int = 5) -> list[str]:
    lesson = BY_ID[lesson_id]
    async with correction_worker.chat_priority():  # the learner is waiting
        raw = await ollama_client.chat_json(
            llm_models.current(),
            [{"role": "user", "content": PROMPTS.format(level=lesson["level"], topic=lesson["title_en"], n=n,
                                                        focus=lesson["practice"]["focus"])}],
            PROMPTS_SCHEMA,
            options={"temperature": 0.8, "num_predict": 400},
        )
    items = [str(x).strip() for x in raw.get("items") or [] if str(x).strip()]
    return items[:n]


JUDGE = """A Turkish learner is practising this English lesson: "{topic}" (target: {focus}).
Question: "{question}"
Learner's answer: "{answer}"

Judge only these two things. Ignore grammar and spelling mistakes — they are checked separately.
- "answers_question": does the answer actually respond to this question? An unrelated, random or nonsense sentence is false, even if it is correct English.
- "uses_structure": does the answer use the lesson's structure ({topic}), even with small mistakes?
Return JSON: {{"answers_question": true/false, "uses_structure": true/false}}"""

JUDGE_SCHEMA = {"type": "object", "properties": {"answers_question": {"type": "boolean"},
                                                 "uses_structure": {"type": "boolean"}},
                "required": ["answers_question", "uses_structure"]}


async def check_answer(lesson_id: str, question: str, answer: str) -> dict:
    """"Kendi cümlelerini kur": grammar (correction engine) + does it answer the question +
    does it use the lesson's structure. The Turkish verdict is written here, not by the LLM."""
    from .corrections import analyze, not_english

    lesson = BY_ID[lesson_id]
    if not_english(answer):
        return {"verdict": "wrong", "message_tr": "Bu İngilizce bir cümle gibi görünmüyor. Soruya İngilizce, "
                                                  "tam bir cümleyle cevap ver.", "correction": None}
    if len(re.findall(r"[A-Za-z']+", answer)) < 2:
        return {"verdict": "wrong", "message_tr": "Çok kısa. Soruya tam bir cümleyle cevap ver.", "correction": None}
    async with correction_worker.chat_priority():  # the learner is waiting
        correction = await analyze(answer, "text", context=question)  # "your mother…" → she
        judged = await ollama_client.chat_json(
            llm_models.current(),
            [{"role": "user", "content": JUDGE.format(topic=lesson["title_en"], focus=lesson["practice"]["focus"],
                                                      question=question.replace('"', "'"),
                                                      answer=answer.replace('"', "'"))}],
            JUDGE_SCHEMA,
            options={"temperature": 0, "num_predict": 60},
        )
    n = len(correction["errors"])
    if not judged.get("answers_question", True):
        verdict, msg = "wrong", "Cevabın soruyla ilgili değil. Soruyu tekrar oku ve ona cevap ver."
    elif n:
        verdict, msg = "wrong", f"Cümlende {n} hata var — kırmızı kısımlar yanlış, yeşiller doğrusu."
    elif not judged.get("uses_structure", True):
        verdict, msg = "warn", f"Cümlen doğru ama bu dersin konusunu ({lesson['title_tr']}) kullanmadın. Bir de onunla dene."
    else:
        verdict, msg = "ok", "Doğru! Soruya uygun, dilbilgisi de doğru."
    return {"verdict": verdict, "message_tr": msg, "correction": correction}
