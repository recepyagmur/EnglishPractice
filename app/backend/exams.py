"""Level exams: a thorough test at the end of each level (when all its lessons are done).

Four parts, graded on the server when the exam is handed in:
- grammar (40 %): hand-written questions on every lesson of the level (app/content/exams/<LEVEL>.json),
- listening (20 %): dictation + short texts with questions (the browser plays them with TTS),
- speaking (20 %): the learner answers out loud; Whisper's transcript is checked for relevance
  (LLM yes/no) and grammar (correction engine),
- writing (20 %): a short message; relevance, length and grammar.
Every part is a pool: each attempt draws its own set (stored with the attempt), so a retake asks other questions.
Pass: ≥ 70 % overall and ≥ 50 % in every part. Turkish feedback is written here, not by the LLM.
"""

import difflib
import json
import random
import re
from collections import Counter

from . import errors, lessons, llm_models, ollama_client, writing
from .config import APP_DIR
from .corrections import analyze, not_english
from .corrections import worker as correction_worker
from .db import get_conn, now_iso
from .settings_store import get_settings

CONTENT_DIR = APP_DIR / "content" / "exams"
WEIGHTS = {"grammar": 0.4, "listening": 0.2, "speaking": 0.2, "writing": 0.2}
PASS_SCORE = 0.7
SECTION_MIN = 0.5
MAX_WRITING_SENTENCES = 15  # longer texts: only the first ones are checked (and counted)
SECTION_NAMES = {"grammar": "Dilbilgisi", "listening": "Dinleme", "speaking": "Konuşma", "writing": "Yazma"}


def _load() -> dict[str, dict]:
    out = {}
    for level in lessons.LEVELS:
        path = CONTENT_DIR / f"{level}.json"
        if path.exists():
            out[level] = json.loads(path.read_text(encoding="utf-8"))
    return out


EXAMS = _load()


# ------------------------------------------------------------------ answers

_CONTRACTIONS = [
    (r"\bcan't\b", "can not"), (r"\bcannot\b", "can not"), (r"\bwon't\b", "will not"), (r"n't\b", " not"),
    (r"'m\b", " am"), (r"'re\b", " are"), (r"'ve\b", " have"), (r"'ll\b", " will"),
    (r"\b(he|she|it|that|there|what|where|who|here)'s\b", r"\1 is"), (r"'d have\b", " would have"),
    # abbreviations: 2 p.m. = 2pm = 2 pm, e.g. = eg, Mr. = Mr
    (r"\b([a-z])\.([a-z])\.", r"\1\2"), (r"\b(mr|mrs|ms|dr)\.", r"\1"), (r"(\d)\s*(am|pm)\b", r"\1 \2"),
]


def normalize_answer(text: str) -> str:
    """Same rules as the lesson exercises (lessons.js normalizeAnswer)."""
    s = text.lower().replace("’", "'").replace("‘", "'")
    s = re.sub(r"[“”\"]", "", s).strip()
    for pattern, rep in _CONTRACTIONS:
        s = re.sub(pattern, rep, s)
    s = re.sub(r"\s+", " ", s.replace(",", ""))
    return re.sub(r"[.!?]+$", "", s).strip()


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", normalize_answer(text))


def _order_key(text: str) -> str:
    """Word-order answers: a tile may carry the final mark ("today."), another correct order puts it
    inside, so inner . ? ! do not count (as lessons.js renderOrder)."""
    return normalize_answer(re.sub(r"[.?!]", " ", text))


# A pronoun's 's is "is" — or "has" before a past participle ("She's finished" = "She has finished");
# 'd is "would" — or "had" before a participle or "better". Only there: "He's a car" must not match
# "He has a car". Keep in sync with lessons.js answerForms.
_PARTICIPLES = set(
    "been got gotten had done gone seen made said sent left lost met paid put read spent taken told thought "
    "bought brought built found heard held kept known run sold written won begun come become given forgotten "
    "chosen spoken broken eaten fallen flown grown shown thrown drawn worn sat stood understood taught caught "
    "felt led set cut hit let shut hurt cost quit sung drunk swum rung forgiven driven ridden risen hidden "
    "bitten beaten woken fed meant slept sold dealt lent stuck struck".split())
_ADVERBS = set("just already never ever not always recently finally also still only really probably "
               "definitely certainly obviously clearly".split())
_PRONOUN_S = re.compile(r"\b(he|she|it|that|there|what|where|who|here)'s\b", re.I)
_PRONOUN_D = re.compile(r"\b(i|you|he|she|it|we|they|there|who|that)'d\b", re.I)


def _before_participle(rest: str) -> bool:
    words = re.findall(r"[a-z']+", rest.lower())[:2]
    if words and words[0] in _ADVERBS:
        words = words[1:]
    return bool(words) and (words[0] in _PARTICIPLES or words[0].endswith("ed") or words[0].endswith("en"))


def _readings(text: str, pattern: re.Pattern, plain: str, perfect: str, extra=()) -> set[str]:
    """Each contraction read the plain way, or the perfect way when a participle follows (all at once:
    mixed readings in one answer are rare)."""
    perfect_text = pattern.sub(lambda m: f"{m.group(1)} {perfect}" if _before_participle(text[m.end():])
                               or text[m.end():].lower().lstrip().startswith(extra) else m.group(0), text)
    return {pattern.sub(rf"\1 {plain}", text), pattern.sub(rf"\1 {plain}", perfect_text)}


def answer_forms(text: str, key=normalize_answer) -> set[str]:
    """Every reading of an answer."""
    forms = _readings(text.replace("’", "'").replace("‘", "'"), _PRONOUN_S, "is", "has")
    forms = set().union(*(_readings(f, _PRONOUN_D, "would", "had", ("better",)) for f in forms))
    return {key(f) for f in forms}


def answer_ok(q: dict, given: str) -> bool:
    if not given.strip():
        return False
    key = _order_key if q["type"] == "order" else normalize_answer
    accepted = set().union(*(answer_forms(a, key) for a in q["answer"]))
    return bool(answer_forms(given, key) & accepted)


# Dictation: a missing apostrophe ("dont") is a slip, not a different word.
_NO_APOSTROPHE = re.compile(r"\b(do|does|did|is|are|was|were|has|have|had|could|should|would|ca|wo)nt\b")


def _dictation_words(text: str) -> list[str]:
    return _words(_NO_APOSTROPHE.sub(r"\1n't", text.lower()))


def _word_edits(a: list[str], b: list[str]) -> int:
    """Words inserted, deleted or replaced to turn a into b."""
    edits = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag != "equal":
            edits += max(i2 - i1, j2 - j1)
    return edits


# ----------------------------------------------------------------- overview

def _lessons_done(level: str) -> tuple[int, int]:
    overview = lessons.overview()
    lv = next(l for l in overview["levels"] if l["id"] == level)
    return lv["done"], lv["count"]


def _attempts(level: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT id, score, passed, finished_at FROM exam_attempts WHERE level = ? "
                            "AND finished_at IS NOT NULL ORDER BY id DESC", (level,)).fetchall()
    return [dict(r) for r in rows]


def status() -> list[dict]:
    """Per level: is there an exam, is it unlocked, the best and last results."""
    out = []
    for level in lessons.LEVELS:
        done, total = _lessons_done(level)
        attempts = _attempts(level) if level in EXAMS else []
        out.append({
            "level": level, "available": level in EXAMS, "title_tr": EXAMS.get(level, {}).get("title_tr"),
            "lessons_done": done, "lessons_total": total, "unlocked": bool(total) and done == total,
            "attempts": len(attempts), "passed": any(a["passed"] for a in attempts),
            "best_score": max((a["score"] for a in attempts), default=None),
            "last": attempts[0] if attempts else None,
        })
    return out


# --------------------------------------------------------------------- start

def _counts(exam: dict) -> dict[str, int]:
    """How many items of each pool an attempt asks."""
    listening = exam["listening"]
    return {"dictation": listening["dictation_count"], "comprehension": listening["comprehension_count"],
            "speaking": exam["speaking_count"]}


def _pick_grammar(exam: dict) -> list[dict]:
    """Round-robin over the lessons so every topic is asked about; within a lesson, the question type asked
    least so far, so every attempt mixes choice / fill / fix / transform / order."""
    by_lesson: dict[str, list] = {}
    for q in exam["grammar"]:
        by_lesson.setdefault(q["lesson"], []).append(q)
    pools = [random.sample(qs, len(qs)) for qs in by_lesson.values()]
    random.shuffle(pools)  # which lessons get one more question when the count does not divide evenly
    want = min(exam["grammar_count"], len(exam["grammar"]))
    picked, types = [], Counter()
    while len(picked) < want:
        for pool in pools:
            if pool and len(picked) < want:
                q = min(pool, key=lambda x: types[x["type"]])  # the pool is shuffled: ties are random
                pool.remove(q)
                picked.append(q)
                types[q["type"]] += 1
    random.shuffle(picked)
    return picked


def _selection(exam: dict, stored) -> dict:
    """The items of an attempt. Attempts started before the pools (a plain list of grammar ids) asked the
    first items of every part — the original ones, which stay first in the files."""
    if isinstance(stored, list):
        n = _counts(exam)
        return {"grammar": stored,
                "dictation": [d["id"] for d in exam["listening"]["dictation"][:n["dictation"]]],
                "comprehension": [c["id"] for c in exam["listening"]["comprehension"][:n["comprehension"]]],
                "speaking": [s["id"] for s in exam["speaking"][:n["speaking"]]],
                "writing": exam["writing"][0]["id"]}
    return stored


def _by_ids(items: list[dict], ids: list[str]) -> list[dict]:
    by_id = {x["id"]: x for x in items}
    return [by_id[i] for i in ids if i in by_id]


def _writing_task(exam: dict, sel: dict) -> dict:
    return next((w for w in exam["writing"] if w["id"] == sel["writing"]), exam["writing"][0])


def start(level: str) -> dict:
    """A new attempt: a balanced random set from every pool."""
    exam = EXAMS[level]
    n = _counts(exam)
    listening = exam["listening"]
    picked = _pick_grammar(exam)
    sel = {
        "grammar": [q["id"] for q in picked],
        "dictation": [d["id"] for d in random.sample(listening["dictation"], n["dictation"])],
        "comprehension": [c["id"] for c in random.sample(listening["comprehension"], n["comprehension"])],
        "speaking": [s["id"] for s in random.sample(exam["speaking"], n["speaking"])],
        "writing": random.choice(exam["writing"])["id"],
    }
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO exam_attempts (level, started_at, questions_json) VALUES (?, ?, ?)",
                           (level, now_iso(), json.dumps(sel)))
        attempt_id = cur.lastrowid
    public_q = [{k: q[k] for k in ("id", "type", "q", "options", "instruction_tr", "words") if k in q} for q in picked]
    return {
        "attempt_id": attempt_id, "level": level, "title_tr": exam["title_tr"], "tts_speed": exam.get("tts_speed", 1.0),
        "weights": WEIGHTS, "pass_score": PASS_SCORE, "section_min": SECTION_MIN,
        "grammar": public_q,
        # The texts are needed to play them (TTS); the page does not show them before the end.
        "listening": {"dictation": _by_ids(listening["dictation"], sel["dictation"]),
                      "comprehension": [{"id": c["id"], "text": c["text"],
                                         "questions": [{k: q[k] for k in ("id", "q_tr", "options")} for q in c["questions"]]}
                                        for c in _by_ids(listening["comprehension"], sel["comprehension"])]},
        "speaking": [{k: s[k] for k in ("id", "question_en", "instruction_tr")}
                     for s in _by_ids(exam["speaking"], sel["speaking"])],
        "writing": {k: _writing_task(exam, sel)[k] for k in ("instruction_tr", "prompt_en", "min_words")},
    }


# --------------------------------------------------------------------- grade

JUDGE = """An English learner (CEFR {level}) answered this exam task.
Task: "{task}"
Answer: "{answer}"

Ignore grammar mistakes. Does the answer actually respond to the task (its meaning fits)? An unrelated or nonsense answer is false.
Return JSON: {{"relevant": true/false}}"""

JUDGE_SCHEMA = {"type": "object", "properties": {"relevant": {"type": "boolean"}}, "required": ["relevant"]}


async def _relevant(level: str, task: str, answer: str) -> bool:
    raw = await ollama_client.chat_json(
        llm_models.current(),
        [{"role": "user", "content": JUDGE.format(level=level, task=task.replace('"', "'"),
                                                  answer=answer.replace('"', "'")[:1500])}],
        JUDGE_SCHEMA, options={"temperature": 0, "num_predict": 30})
    return bool(raw.get("relevant", True))


def _grade_grammar(exam: dict, ids: list[str], answers: dict) -> tuple[float, list[dict]]:
    by_id = {q["id"]: q for q in exam["grammar"]}
    items = []
    for qid in ids:
        q = by_id[qid]
        given = answers.get(qid)
        if q["type"] == "choice":
            ok = given is not None and int(given) == q["answer"]
            your = q["options"][int(given)] if given is not None and 0 <= int(given) < len(q["options"]) else ""
            correct = q["options"][q["answer"]]
        else:
            your = str(given or "").strip()
            ok = answer_ok(q, your)
            correct = q["answer"][0]
        items.append({"id": qid, "q": q.get("q", ""), "type": q["type"], "your": your, "correct": correct, "ok": ok,
                      "explain_tr": q["explain_tr"], "lesson": q["lesson"],
                      **{k: q[k] for k in ("instruction_tr", "words") if k in q}})
    return (sum(i["ok"] for i in items) / len(items) if items else 0), items


def _grade_listening(exam: dict, sel: dict, answers: dict) -> tuple[float, list[dict]]:
    items, points = [], []
    for d in _by_ids(exam["listening"]["dictation"], sel["dictation"]):
        your = str(answers.get(d["id"]) or "")
        want, got = _dictation_words(d["text"]), _dictation_words(your)
        if not got:
            score = 0.0
        elif _word_edits(want, got) <= 1:  # one small slip is forgiven
            score = 1.0
        else:
            score = round(difflib.SequenceMatcher(None, want, got).ratio() * 0.9, 2)
        points.append(score)
        items.append({"kind": "dictation", "text": d["text"], "your": your, "score": score})
    for c in _by_ids(exam["listening"]["comprehension"], sel["comprehension"]):
        for q in c["questions"]:
            given = answers.get(q["id"])
            ok = given is not None and int(given) == q["answer"]
            points.append(1.0 if ok else 0.0)
            items.append({"kind": "comprehension", "text": c["text"], "q_tr": q["q_tr"], "ok": ok,
                          "your": q["options"][int(given)] if given is not None else "",
                          "correct": q["options"][q["answer"]]})
    return (sum(points) / len(points) if points else 0), items


async def _grade_speaking(level: str, exam: dict, sel: dict, answers: dict) -> tuple[float, list[dict]]:
    items = []
    for s in _by_ids(exam["speaking"], sel["speaking"]):
        text = str((answers.get(s["id"]) or {}).get("text") or "").strip()
        typed = bool((answers.get(s["id"]) or {}).get("typed"))
        item = {"question_en": s["question_en"], "text": text, "typed": typed, "correction": None}
        if not text:
            item.update(score=0.0, message_tr="Cevap verilmedi.")
        elif not_english(text):
            item.update(score=0.0, message_tr="Cevap İngilizce değildi.")
        else:
            correction = await analyze(text, "voice" if not typed else "text", context=s["question_en"])
            relevant = await _relevant(level, s["question_en"], text)
            n = len(correction["errors"])
            short = len(_words(text)) < 5
            grammar = max(0.0, 1 - 0.25 * n)
            score = 0.0 if not relevant else (0.4 + 0.6 * grammar) * (0.6 if short else 1.0)
            msg = ("Cevabın soruyla ilgili değildi." if not relevant else
                   f"{n} dilbilgisi hatası." if n else "Soruya uygun ve dilbilgisi doğru. ✓")
            if relevant and short:
                msg += " Cevabın çok kısaydı; birkaç cümle kurmayı dene."
            item.update(score=round(score, 2), message_tr=msg, correction=correction)
        items.append(item)
    return (sum(i["score"] for i in items) / len(items) if items else 0), items


async def _grade_writing(level: str, task: dict, text: str) -> tuple[float, dict]:
    text = text.strip()
    words = len(_words(text))
    result = {"text": text, "words": words, "min_words": task["min_words"], "corrections": []}
    if not text:
        return 0.0, {**result, "message_tr": "Metin yazılmadı."}
    if not_english(text):
        return 0.0, {**result, "message_tr": "Metin İngilizce değildi."}
    relevant = await _relevant(level, task["prompt_en"], text)
    lang = get_settings()["explanation_language"]
    checked = writing.split_sentences(text)[:MAX_WRITING_SENTENCES]
    n, previous = 0, ""
    for sentence in checked:
        c = await analyze(sentence["text"], "writing", context=previous)
        previous = sentence["text"]
        # Capitalization slips the model leaves out (the same code check as the writing mode).
        found = {e["wrong"].lower() for e in c["errors"]}
        extra = [{k: e[k] for k in ("wrong", "right", "category", "explanation")}
                 for e in writing._capitalization_errors(sentence, lang) if e["wrong"].lower() not in found]
        if c["errors"] or extra:
            c = {**c, "has_errors": True, "errors": c["errors"] + extra}
            n += len(c["errors"])
            result["corrections"].append(c)
    grammar = max(0.0, 1 - 0.5 * n / max(1, len(checked)))
    length = min(1.0, words / task["min_words"])
    # Off-topic writing cannot pass the part (as in speaking, where it scores 0).
    score = (0.3 + 0.7 * grammar) * length if relevant else 0.3 * grammar * length
    msg = [] if relevant else ["Metin istenen konuyla ilgili değildi."]
    if words < task["min_words"]:
        msg.append(f"Metin kısaydı ({words}/{task['min_words']} kelime).")
    msg.append(f"{n} dilbilgisi hatası." if n else "Dilbilgisi hatası yok. ✓")
    return round(score, 2), {**result, "message_tr": " ".join(msg), "relevant": relevant}


async def submit(attempt_id: int, answers: dict) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM exam_attempts WHERE id = ?", (attempt_id,)).fetchone()
    if row is None:
        raise KeyError(attempt_id)
    level, exam = row["level"], EXAMS[row["level"]]
    sel = _selection(exam, json.loads(row["questions_json"]))
    grammar, grammar_items = _grade_grammar(exam, sel["grammar"], answers.get("grammar") or {})
    listening, listening_items = _grade_listening(exam, sel, answers.get("listening") or {})
    async with correction_worker.chat_priority():  # the learner is waiting for the result
        speaking, speaking_items = await _grade_speaking(level, exam, sel, answers.get("speaking") or {})
        writing, writing_item = await _grade_writing(level, _writing_task(exam, sel), str(answers.get("writing") or ""))
    sections = {"grammar": grammar, "listening": listening, "speaking": speaking, "writing": writing}
    total = sum(WEIGHTS[k] * v for k, v in sections.items())
    # round(…, 6): float noise must not fail an exactly-70 % result (the page shows %70 then)
    passed = round(total, 6) >= PASS_SCORE and all(round(v, 6) >= SECTION_MIN for v in sections.values())
    # Lessons to review: the ones behind wrong grammar answers, most mistakes first.
    wrong = {}
    for i in grammar_items:
        if not i["ok"]:
            wrong[i["lesson"]] = wrong.get(i["lesson"], 0) + 1
    review = [{"id": lid, "title_tr": lessons.BY_ID[lid]["title_tr"], "mistakes": n}
              for lid, n in sorted(wrong.items(), key=lambda kv: -kv[1]) if lid in lessons.BY_ID]
    next_level = lessons.LEVELS[lessons.LEVELS.index(level) + 1] if level != lessons.LEVELS[-1] else None
    result = {
        "attempt_id": attempt_id, "level": level, "title_tr": exam["title_tr"], "score": round(total, 3),
        "passed": passed, "pass_score": PASS_SCORE, "section_min": SECTION_MIN,
        "sections": [{"id": k, "name": SECTION_NAMES[k], "score": round(v, 3), "weight": WEIGHTS[k],
                      "ok": v >= SECTION_MIN} for k, v in sections.items()],
        "grammar": grammar_items, "listening": listening_items, "speaking": speaking_items, "writing": writing_item,
        "review_lessons": review, "next_level": next_level,
        "category_labels": {c["id"]: c["tr"] for c in errors.CATEGORIES},
    }
    with get_conn() as conn:
        conn.execute("UPDATE exam_attempts SET finished_at = ?, score = ?, passed = ?, result_json = ? WHERE id = ?",
                     (now_iso(), total, int(passed), json.dumps(result, ensure_ascii=False), attempt_id))
    return result


def get_result(attempt_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT result_json FROM exam_attempts WHERE id = ?", (attempt_id,)).fetchone()
    return json.loads(row["result_json"]) if row and row["result_json"] else None


def delete_attempt(attempt_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM exam_attempts WHERE id = ?", (attempt_id,))
