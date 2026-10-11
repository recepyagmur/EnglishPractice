"""The Turkish-speaking teacher: answers questions about English in Turkish.

It knows the learner's level and most frequent mistakes, and what it was opened from
(the context): a lesson, one correction ("Neden yanlış?") or a weak point (practice).

The local model can misjudge English, so before it answers, the app's grammar checker
(corrections.analyze) looks at the English the learner wrote — the whole message, or
sentences they quote ("'I am working here since 2020' doğru mu?") — and the result goes
to the model as a note. Whole English messages (e.g. answers to exercises) are also
marked red/green and counted in the statistics like any other sentence the learner writes.
"""

import re
from typing import AsyncIterator

from . import corrections, errors, lessons, llm_models, ollama_client, progress, sessions
from .config import CHAT_HISTORY_LIMIT
from .corrections import worker as correction_worker
from .ollama_client import OllamaError
from .settings_store import get_level, get_settings

Event = tuple[str, dict]

# A whole message with at least this share of English dictionary words is the learner's English.
ENGLISH_MESSAGE_SHARE = 0.8
MIN_CHECK_WORDS = 3
MAX_QUOTES_CHECKED = 2

SYSTEM = """You are "Öğretmen", a friendly and patient English teacher. Your student is a Turkish adult who works in an office. Their English level is {level} (CEFR).{interests}
Talk to them in natural, correct Turkish and address them as "sen". English words, phrases and sentences stay in English.

How to answer:
- Be short: usually at most 120 words. Go longer only when the student asks for more detail.
- Start with the answer itself in 1-3 short Turkish sentences.
- Put every English example sentence on its own line that starts with "- ", followed by its Turkish translation in brackets, like this:
- I have worked here since 2020. (2020'den beri burada çalışıyorum.)
- Prefer examples from work life: emails, meetings, reports, colleagues, customers.
- You may end with one short tip on its own line starting with "İpucu:".
- No headings and no tables. Use **bold** only for the key word or two.
- Give an exercise ONLY when the student asks for practice or in practice mode, never at the end of a normal answer. Write the exercise itself on its own line starting with "> ", one exercise at a time, then wait for the answer. The answer must always be a whole English sentence, so use only these two kinds: translate a short Turkish work sentence into English, or rewrite a wrong English sentence correctly. No fill-in-the-blank and no multiple choice.

Rules:
- Never invent grammar rules. If a sentence is correct, say clearly that it is correct.
- When asked whether something is right, begin with a clear verdict ("Evet, doğru." or "Hayır, burada bir hata var.").
- Notes in square brackets that start with [App …] come from the app, not from the student. Use them, never mention them. The app's grammar check is usually right.
- If the question is not about English, answer in one sentence and bring the talk back to English.

What you know about the student's recent mistakes (last 30 days): {weak_points}{context}"""

CONTEXT_PROMPTS = {
    "lesson": """

The student opened you from the lesson "{title_en}" ({title_tr}, level {level}); their questions are probably about this topic.
Lesson summary (Turkish): {intro_tr}
Typical mistakes Turkish speakers make here: {mistakes}""",
    "error": """

The student asks about a correction the app made to one of their sentences.
Their sentence: "{sentence}"
Corrected: "{corrected}"
The error: "{wrong}" → "{right}" ({category}). {explanation}
Explain simply why it is wrong and how to get it right next time, with 2 similar examples. Do not repeat the whole sentence back unless it helps.""",
    "practice": """

Practice mode: the student wants to practise "{category}" ({category_tr}).{examples}
Give one short exercise at a time on this topic, at level {level} (see the exercise rules above). After each answer: say whether it is right (use the [App …] note about their answer), show the correct sentence, explain in one or two sentences, then give the next exercise. Start with the first exercise right away.""",
}

OPENING_QUESTIONS = {  # the first message, sent for the learner when the context needs one
    "error": "Şu cümlemde bir düzeltme yapıldı: “{sentence}” — “{wrong}” yerine “{right}”. Bunun neden yanlış olduğunu açıklar mısın?",
    "practice": "{category_tr} konusunda çok hata yapıyorum. Bana bu konuda alıştırma yaptırır mısın?",
}


# ------------------------------------------------------------------ context

def _text(value, limit: int = 300) -> str:
    return str(value or "").strip()[:limit]


def clean_context(context: dict | None) -> dict | None:
    """Validate what the page sent; returns the stored form (with a title) or raises ValueError."""
    if not context:
        return None
    kind = context.get("type")
    if kind == "lesson":
        lesson = lessons.BY_ID.get(context.get("lesson_id"))
        if lesson is None:
            raise ValueError("Ders bulunamadı.")
        return {"type": "lesson", "lesson_id": lesson["id"], "title": f"📘 {lesson['title_tr']} ({lesson['level']})"}
    if kind == "error":
        out = {"type": "error", "sentence": _text(context.get("sentence"), 600),
               "corrected": _text(context.get("corrected"), 600), "wrong": _text(context.get("wrong")),
               "right": _text(context.get("right")), "category": errors.normalize(context.get("category")),
               "explanation": _text(context.get("explanation"))}
        if not out["sentence"] or not out["wrong"]:
            raise ValueError("Hata bilgisi eksik.")
        out["title"] = f"❓ {out['wrong']} → {out['right']}"
        return out
    if kind == "practice":
        category = context.get("category")
        if category not in errors.BY_ID:
            raise ValueError("Bilinmeyen hata türü.")
        return {"type": "practice", "category": category, "title": f"🎯 {errors.BY_ID[category]['tr']} alıştırması"}
    raise ValueError("Bilinmeyen bağlam.")


def opening_question(context: dict | None) -> str:
    if not context or context["type"] not in OPENING_QUESTIONS:
        return ""
    values = {**context, "category_tr": errors.BY_ID.get(context.get("category"), {}).get("tr", "")}
    return OPENING_QUESTIONS[context["type"]].format(**values)


def _weak_points_text(category: str | None = None) -> str:
    items = progress.weak_points(30)
    if category:
        items = [w for w in items if w["category"] == category]
    lines = []
    for w in items[:3]:
        examples = ", ".join(f'"{e["wrong"]}" → "{e["right"]}"' for e in w["examples"][:2] if e["wrong"])
        lines.append(f"\n- {errors.BY_ID[w['category']]['name']} ({w['count']} times)" + (f": {examples}" if examples else ""))
    return "".join(lines)


def _context_prompt(context: dict | None) -> str:
    if not context:
        return ""
    kind = context["type"]
    if kind == "lesson":
        lesson = lessons.BY_ID.get(context["lesson_id"])
        if lesson is None:  # removed from the content since
            return ""
        mistakes = "; ".join(f'"{m["wrong"]}" → "{m["right"]}"' for m in lesson.get("mistakes", [])[:4]) or "-"
        return CONTEXT_PROMPTS["lesson"].format(title_en=lesson["title_en"], title_tr=lesson["title_tr"],
                                                level=lesson["level"], intro_tr=lessons.plain(lesson["intro_tr"]),
                                                mistakes=mistakes)
    if kind == "error":
        return CONTEXT_PROMPTS["error"].format(**{**context, "category": errors.BY_ID[context["category"]]["name"]})
    if kind == "practice":
        examples = _weak_points_text(context["category"])
        return CONTEXT_PROMPTS["practice"].format(
            category=errors.BY_ID[context["category"]]["name"], category_tr=errors.BY_ID[context["category"]]["tr"],
            level=get_level(), examples=f" Their recent mistakes in it:{examples}" if examples else "")
    return ""


_PROMPTS: dict[int, str] = {}  # session → its system prompt, fixed for the session


def _session_prompt(session_id: int, context: dict | None) -> str:
    """The same text for the whole session: the weak-point list changes as answers are checked,
    and a changed system prompt would make Ollama read the whole conversation again (slow on a CPU)."""
    if session_id not in _PROMPTS:
        if len(_PROMPTS) > 200:
            _PROMPTS.clear()
        _PROMPTS[session_id] = system_prompt(context)
    return _PROMPTS[session_id]


def system_prompt(context: dict | None) -> str:
    interests = get_settings()["interests"].strip()
    return SYSTEM.format(
        level=get_level(),
        interests=f" Their interests: {interests}." if interests else "",
        weak_points=_weak_points_text() or " none recorded yet.",
        context=_context_prompt(context),
    )


# ------------------------------------------------------------------ grammar check

_QUOTED = re.compile(
    r"""(?:^|(?<=[\s(]))(?:"([^"]+)"|“([^”]+)”|‘([^’]+)’|'(.+?)'(?!(?:t|s|re|ve|ll|d|m)\b))""")


def _english(text: str, share: float) -> bool:
    from .dictionary import english_share  # dictionary imports corrections

    words = re.findall(r"[A-Za-z']+", text)
    s = english_share(text)
    return len(words) >= MIN_CHECK_WORDS and s is not None and s >= share


def english_parts(text: str) -> tuple[bool, list[str]]:
    """(the whole message is English, quoted English sentences to check)."""
    if _english(text, ENGLISH_MESSAGE_SHARE):
        return True, [text]
    quotes = [next(g for g in m.groups() if g) for m in _QUOTED.finditer(text)]
    return False, [q.strip() for q in quotes if _english(q, corrections.MIN_ENGLISH_SHARE)][:MAX_QUOTES_CHECKED]


def _check_note(sentence: str, result: dict, whole: bool) -> str:
    what = "the student's message" if whole else f'"{sentence}"'
    if not result["has_errors"]:
        return f"[App grammar check of {what}: no grammar errors.]"
    found = "; ".join(f'"{e["wrong"]}" → "{e["right"]}" ({errors.BY_ID[e["category"]]["name"]})' for e in result["errors"])
    return f'[App grammar check of {what}: errors: {found}. Corrected: "{result["corrected"]}"]'


# ------------------------------------------------------------------ turns

def title(context: dict | None, first_question: str | None) -> str:
    if context and context.get("title"):
        return context["title"]
    q = (first_question or "").strip().replace("\n", " ")
    return q[:70] + ("…" if len(q) > 70 else "") or "Soru"


async def turn(session_id: int | None, text: str, context: dict | None) -> AsyncIterator[Event]:
    """Yields ("meta" | "status" | "correction" | "delta" | "done" | "error", data)."""
    if session_id is not None and sessions.mode_of(session_id) == sessions.TEACHER:
        context = sessions.context_of(session_id)
    else:
        try:
            context = clean_context(context)
        except ValueError as e:
            yield "error", {"message": str(e)}
            return
        text = text.strip() or opening_question(context)
        if not text:  # nothing to ask yet: no empty session is stored
            yield "error", {"message": "Bir soru yaz."}
            return
        session_id = sessions.create_session(sessions.TEACHER, context=context)
    text = text.strip()
    if not text:
        yield "error", {"message": "Bir soru yaz."}
        return

    history = sessions.recent_messages(session_id, CHAT_HISTORY_LIMIT)
    previous = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), "")
    # Context for the he/she check: only the teacher's English exercise lines ("> Tell me about your
    # sister."). Its Turkish text would mislead it ("her gün" = every day, not "her").
    previous = " ".join(line.lstrip("> ").strip() for line in previous.splitlines()
                        if line.startswith(">") and _english(line, corrections.MIN_ENGLISH_SHARE))
    user_message_id = sessions.add_message(session_id, "user", text, {"source": "teacher"})
    yield "meta", {"session_id": session_id, "user_message_id": user_message_id, "user_text": text, "context": context}

    notes = []
    whole, parts = english_parts(text)
    if parts:
        yield "status", {"message": "Cümle kontrol ediliyor…"}
        for part in parts:
            try:
                async with correction_worker.chat_priority():
                    result = await corrections.analyze(part, "text", context=previous if whole else "")
            except OllamaError as e:
                sessions.delete_message(user_message_id)
                yield "error", {"message": str(e)}
                return
            notes.append(_check_note(part, result, whole))
            if whole:  # the learner's own English: marked and counted like everywhere else
                corrections.save(user_message_id, "text", result)
                yield "correction", {"message_id": user_message_id, **result}

    llm_messages = [{"role": "system", "content": _session_prompt(session_id, context)}, *history,
                    {"role": "user", "content": "\n\n".join([text, *notes])}]
    reply, model = "", None
    try:
        if waiting := llm_models.manager.wait_message():
            yield "status", {"message": waiting}
        async with correction_worker.chat_priority():
            model = llm_models.current()
            async for chunk in ollama_client.chat_stream(model, llm_messages, options={"num_predict": 900}):
                reply += chunk
                yield "delta", {"text": chunk}
    except OllamaError as e:
        if not reply:
            sessions.delete_message(user_message_id)  # a retry must not leave the question twice
        yield "error", {"message": str(e)}
        return
    finally:
        if reply.strip():  # also when the page stopped reading (closed / navigated away)
            message_id = sessions.add_message(session_id, "assistant", reply.strip(), {"model": model, "notes": notes})
        else:
            message_id = None
    yield "done", {"message_id": message_id, "text": reply.strip()}


def history() -> list[dict]:
    return [{"id": s["id"], "title": title(s["context"], s["first_question"]), "context": s["context"],
             "started_at": s["started_at"], "last_message_at": s["last_message_at"],
             "message_count": s["message_count"]}
            for s in sessions.list_sessions(teacher=True)]


def get(session_id: int) -> dict | None:
    s = sessions.get_session(session_id)
    if s is None or s["mode"] != sessions.TEACHER:
        return None
    first = next((m["text"] for m in s["messages"] if m["role"] == "user"), None)
    return {"id": s["id"], "title": title(s["context"], first), "context": s["context"],
            "started_at": s["started_at"], "messages": s["messages"],
            "corrections": corrections.for_session(session_id)}

