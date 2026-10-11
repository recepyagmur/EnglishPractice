"""Writing practice: task types, topic suggestions and the review of a text.

The review is done sentence by sentence with the same correction prompt as the
conversation (better accuracy with a small model than one big prompt, and the
results can be shown as they come), followed by an overall assessment and a
streamed "more natural" rewrite.
"""

import json
import random
import re
from typing import AsyncIterator

from . import corrections, errors, llm_models, ollama_client
from .corrections import worker as correction_worker
from .db import get_conn, now_iso
from .ollama_client import OllamaError
from .settings_store import get_level, get_settings

LANG_NAMES = {"tr": "Turkish", "en": "English"}
LEVELS = ["A2", "B1", "B2", "C1", "C2"]
MAX_WORDS = 600
# Lines this short ("Dear Mark,", "Best wishes,", a signature) are not checked.
MIN_CHECK_WORDS = 3

# id: label (UI), English task description (prompt), target words at B2 (None = free), minutes
TASK_TYPES = {
    "free": {"label_tr": "Serbest yazı", "task": "free writing on a topic of their choice", "words": None, "minutes": None},
    "email": {"label_tr": "E-posta", "task": "an email", "words": (80, 150), "minutes": None},
    "essay": {"label_tr": "Essay", "task": "an opinion essay", "words": (150, 250), "minutes": None},
    "story": {"label_tr": "Hikaye", "task": "a short story", "words": (100, 200), "minutes": None},
    "journal": {"label_tr": "Günlük", "task": "a daily journal entry about their day", "words": (60, 150), "minutes": None},
    "ielts": {"label_tr": "IELTS / TOEFL görevi", "task": "an IELTS Writing Task 2 style essay", "words": (250, 300),
              "minutes": 40},
}
# Shorter targets for lower levels (IELTS keeps its official length).
WORD_SCALE = {"A2": 0.6, "B1": 0.8, "B2": 1.0, "C1": 1.2, "C2": 1.3}

# Used when the LLM is unavailable.
FALLBACK_TOPICS = {
    "free": ["Write about something that made you happy recently."],
    "email": ["Write an email to a friend inviting them to your birthday party.",
              "Write an email to your manager asking for a day off next week."],
    "essay": ["Some people think working from home is better than working in an office. What do you think?",
              "Should children learn to code at school? Give your opinion."],
    "story": ["Write a story that begins: 'When I opened the door, I couldn't believe my eyes.'"],
    "journal": ["Write about your day today: what you did, who you met and how you felt."],
    "ielts": ["Some people believe technology has made our lives more complicated. "
              "To what extent do you agree or disagree?"],
}


def task_types() -> list[dict]:
    level = get_level()
    out = []
    for tid, t in TASK_TYPES.items():
        words = t["words"]
        if words and tid != "ielts":
            scale = WORD_SCALE.get(level, 1.0)
            words = (round(words[0] * scale / 10) * 10, round(words[1] * scale / 10) * 10)
        out.append({"id": tid, "label_tr": t["label_tr"], "words": words, "minutes": t["minutes"]})
    return out


TOPIC_PROMPT = """Suggest one writing task for a Turkish English learner at CEFR level {level}.
Type: {task}.{interests}
The task instruction must be in simple English (1-2 sentences), and a Turkish translation of it.
Make it concrete and personal, not generic. Avoid these recent topics: {avoid}."""

TOPIC_SCHEMA = {
    "type": "object",
    "properties": {"prompt": {"type": "string"}, "prompt_tr": {"type": "string"}},
    "required": ["prompt", "prompt_tr"],
}


async def suggest_topic(task_type: str, avoid: list[str]) -> dict:
    t = TASK_TYPES.get(task_type, TASK_TYPES["free"])
    settings = get_settings()
    interests = settings["interests"].strip()
    try:
        async with correction_worker.chat_priority():
            raw = await ollama_client.chat_json(
                llm_models.current(),
                [{"role": "user", "content": TOPIC_PROMPT.format(
                    level=get_level(), task=t["task"],
                    interests=f" The learner's interests: {interests}." if interests else "",
                    avoid="; ".join(avoid[-5:]) or "none")}],
                TOPIC_SCHEMA,
                options={"temperature": 0.9, "num_predict": 200},
            )
        return {"prompt": raw["prompt"].strip(), "prompt_tr": raw.get("prompt_tr", "").strip()}
    except (OllamaError, KeyError):
        return {"prompt": random.choice(FALLBACK_TOPICS[task_type if task_type in FALLBACK_TOPICS else "free"]),
                "prompt_tr": ""}


# ----------------------------------------------------------------- review

def split_sentences(text: str) -> list[dict]:
    """Sentences with their character offsets in `text` (line breaks also end a sentence)."""
    out = []
    for m in re.finditer(r"[^.!?\n]+(?:[.!?]+[\"')\]]*)?", text):
        chunk = m.group()
        stripped = chunk.strip()
        if not any(c.isalpha() for c in stripped):
            continue
        start = m.start() + (len(chunk) - len(chunk.lstrip()))
        out.append({"start": start, "end": start + len(stripped), "text": stripped})
    return out


# Words English always capitalizes but Turkish doesn't (days, months, nationalities /
# languages). Checked by code: the small model often misses them.
_CAPITALIZED = {
    w.lower(): w for w in (
        "Monday Tuesday Wednesday Thursday Friday Saturday Sunday "
        "January February March April May June July August September October November December "
        "Turkish English American British German French Spanish Italian Russian Arabic Chinese "
        "Japanese Korean Greek Dutch Persian Kurdish Turkey England America Germany France Spain "
        "Italy Russia China Japan Istanbul Ankara Izmir London Paris Europe Asia"
    ).split()
}
# "may" and "march" are also ordinary words; only flag them next to a date-like word.
_AMBIGUOUS = {"may", "march"}
CAP_EXPLANATION = {
    "tr": "Gün, ay, ülke, milliyet ve dil adları İngilizcede büyük harfle başlar.",
    "en": "Days, months, countries, nationalities and languages start with a capital letter.",
}
I_EXPLANATION = {"tr": "'I' (ben) her zaman büyük harfle yazılır.", "en": "The pronoun 'I' is always capitalized."}


def _capitalization_errors(sentence: dict, lang: str) -> list[dict]:
    out = []
    for m in re.finditer(r"[A-Za-z]+", sentence["text"]):
        word = m.group()
        fixed = None
        if word == "i":
            fixed, why = "I", I_EXPLANATION
        elif word.islower() and word in _CAPITALIZED:
            if word in _AMBIGUOUS:
                before = sentence["text"][:m.start()].lower().split()[-1:]
                after = sentence["text"][m.end():].split()[:1]
                is_month = (before and (before[0] in ("in", "of", "since", "early", "late", "until")
                                        or before[0].rstrip("thsndrd.").isdigit())
                            or after and after[0].rstrip(",.").rstrip("thsndrd").isdigit())
                if not is_month:
                    continue
            fixed, why = _CAPITALIZED[word], CAP_EXPLANATION
        if fixed:
            start = sentence["start"] + m.start()
            out.append({"wrong": word, "right": fixed, "category": "punctuation",
                        "explanation": why.get(lang, why["tr"]), "start": start, "end": start + len(word)})
    return out


def _locate(sentence: dict, wrong: str) -> tuple[int, int] | None:
    """Absolute offsets of `wrong` inside the sentence (case-insensitive)."""
    idx = sentence["text"].lower().find(wrong.lower()) if wrong else -1
    if idx < 0:
        return None
    return sentence["start"] + idx, sentence["start"] + idx + len(wrong)


ASSESS_PROMPT = """You are an experienced English writing teacher. A Turkish learner (self-reported level {level}) wrote the text below for this task: {task}{topic}.

Text ({words} words):
\"\"\"{text}\"\"\"

A sentence-by-sentence check found {error_count} errors ({errors_per_100:.1f} per 100 words){by_category}.

Return JSON:
- "scores": "grammar", "vocabulary", "coherence", "task_achievement", each an integer 1-10. Base the grammar score on the error rate above (about 0-1 errors per 100 words = 9-10, 3 = 7, 6 = 5, 10+ = 3).
- "estimated_cefr": the level this text shows: one of A2, B1, B2, C1, C2.
- "summary": 2-3 sentences of encouraging, specific feedback (in {lang}).
- "suggested_phrases": 3-5 more advanced words or phrases the learner could have used in THIS text, each {{"phrase", "example" (a short example sentence)}}.

IMPORTANT: write the "summary" in {lang}."""

ASSESS_SCHEMA = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "object",
            "properties": {k: {"type": "integer"} for k in ("grammar", "vocabulary", "coherence", "task_achievement")},
            "required": ["grammar", "vocabulary", "coherence", "task_achievement"],
        },
        "estimated_cefr": {"type": "string", "enum": LEVELS},
        "summary": {"type": "string"},
        "suggested_phrases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"phrase": {"type": "string"}, "example": {"type": "string"}},
                "required": ["phrase", "example"],
            },
        },
    },
    "required": ["scores", "estimated_cefr", "summary", "suggested_phrases"],
}

IMPROVE_PROMPT = """Rewrite this text by a Turkish English learner (level {level}) so that it is correct and sounds natural, at about level {target}.
Keep the learner's ideas, order and paragraphs; do not add new content. Output only the rewritten text, nothing else.

Text:
\"\"\"{text}\"\"\""""


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9'’-]+", text))


def _save_writing(task_type: str, prompt: str, text: str) -> int:
    with get_conn() as conn:
        return conn.execute(
            "INSERT INTO writings (task_type, prompt, text, created_at) VALUES (?, ?, ?, ?)",
            (task_type, prompt, text, now_iso()),
        ).lastrowid


def _save_review(writing_id: int, review: dict) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE writings SET review_json = ? WHERE id = ?",
                     (json.dumps(review, ensure_ascii=False), writing_id))
        conn.execute("DELETE FROM error_log WHERE writing_id = ?", (writing_id,))
        for e in review["errors"]:
            conn.execute(
                "INSERT INTO error_log (writing_id, source, category, wrong, right, explanation, taxonomy_version,"
                " created_at) VALUES (?, 'writing', ?, ?, ?, ?, ?, ?)",
                (writing_id, e["category"], e["wrong"], e["right"], e["explanation"],
                 errors.TAXONOMY_VERSION, now_iso()),
            )


async def review(task_type: str, prompt: str, text: str) -> AsyncIterator[tuple[str, dict]]:
    """Yields: saved → progress/sentence* → assessment → improved_delta* → done | error."""
    settings = get_settings()
    level = get_level()
    task = TASK_TYPES.get(task_type, TASK_TYPES["free"])
    writing_id = _save_writing(task_type, prompt, text)
    sentences = split_sentences(text)
    yield "saved", {"writing_id": writing_id, "sentences": len(sentences)}

    all_errors, checked = [], []
    async with correction_worker.chat_priority():  # background corrections wait
        try:
            # 1. sentence by sentence
            for i, s in enumerate(sentences):
                if word_count(s["text"]) < MIN_CHECK_WORDS:
                    result = {"corrected": s["text"], "errors": [], "more_natural": None, "skipped": True}
                else:
                    context = " ".join(x["text"] for x in sentences[max(0, i - 2):i])
                    result = await corrections.analyze(s["text"], "writing", context)
                errs = []
                for e in result["errors"]:
                    pos = _locate(s, e["wrong"])
                    errs.append({**e, "start": pos[0] if pos else None, "end": pos[1] if pos else None})
                # Add capitalization slips the model did not report itself.
                covered = [(e["start"], e["end"]) for e in errs if e["start"] is not None]
                for c in _capitalization_errors(s, settings["explanation_language"]):
                    if not any(a <= c["start"] < b for a, b in covered):
                        errs.append(c)
                errs.sort(key=lambda e: e["start"] if e["start"] is not None else 1 << 30)
                item = {"index": i, "start": s["start"], "end": s["end"], "original": s["text"],
                        "corrected": result["corrected"], "errors": errs, "more_natural": result["more_natural"]}
                checked.append(item)
                all_errors.extend(errs)
                yield "sentence", item

            # 2. overall assessment
            words = word_count(text)
            counts: dict[str, int] = {}
            for e in all_errors:
                counts[e["category"]] = counts.get(e["category"], 0) + 1
            by_category = (": " + ", ".join(f"{errors.BY_ID[c]['name']} {n}" for c, n in
                                            sorted(counts.items(), key=lambda kv: -kv[1]))) if counts else ""
            raw = await ollama_client.chat_json(
                llm_models.current(),
                [{"role": "user", "content": ASSESS_PROMPT.format(
                    level=level, task=task["task"], topic=f' — "{prompt}"' if prompt else "",
                    words=words, text=text, error_count=len(all_errors),
                    errors_per_100=len(all_errors) * 100 / max(words, 1), by_category=by_category,
                    lang=LANG_NAMES.get(settings["explanation_language"], "Turkish"))}],
                ASSESS_SCHEMA,
                options={"temperature": 0.2, "num_predict": 600},
            )
            scores = {k: max(1, min(10, int(v))) for k, v in (raw.get("scores") or {}).items()}
            assessment = {
                "scores": scores,
                "estimated_cefr": raw.get("estimated_cefr") if raw.get("estimated_cefr") in LEVELS else None,
                "summary": (raw.get("summary") or "").strip(),
                "suggested_phrases": (raw.get("suggested_phrases") or [])[:5],
                "words": words,
                "error_count": len(all_errors),
                "categories": [{"id": c, "count": n} for c, n in sorted(counts.items(), key=lambda kv: -kv[1])],
            }
            yield "assessment", assessment

            # 3. a more natural version, streamed
            target = LEVELS[min(LEVELS.index(level) + 1, len(LEVELS) - 1)] if level in LEVELS else "B2"
            improved = ""
            async for chunk in ollama_client.chat_stream(
                llm_models.current(),
                [{"role": "user", "content": IMPROVE_PROMPT.format(level=level, target=target, text=text)}],
            ):
                improved += chunk
                yield "improved_delta", {"text": chunk}
        except OllamaError as e:
            yield "error", {"message": str(e)}
            return

    result = {"sentences": checked, "errors": all_errors, "assessment": assessment,
              "improved_version": improved.strip().strip('"').strip()}
    _save_review(writing_id, result)
    yield "done", {"writing_id": writing_id, "review": result}


# ---------------------------------------------------------------- history

def list_writings(limit: int = 100) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, task_type, prompt, text, review_json, created_at FROM writings"
            " WHERE review_json IS NOT NULL ORDER BY id DESC LIMIT ?", (limit,),
        ).fetchall()
    out = []
    for r in rows:
        review = json.loads(r["review_json"])
        out.append({
            "id": r["id"], "task_type": r["task_type"], "prompt": r["prompt"], "created_at": r["created_at"],
            "words": word_count(r["text"]), "estimated_cefr": review["assessment"].get("estimated_cefr"),
            "error_count": len(review["errors"]), "preview": r["text"][:80],
        })
    return out


def get_writing(writing_id: int) -> dict | None:
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM writings WHERE id = ?", (writing_id,)).fetchone()
    if r is None:
        return None
    return {**{k: r[k] for k in ("id", "task_type", "prompt", "text", "created_at")},
            "review": json.loads(r["review_json"]) if r["review_json"] else None}


def delete_writing(writing_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM writings WHERE id = ?", (writing_id,))
