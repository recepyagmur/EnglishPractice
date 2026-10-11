"""End-of-session report: what went well, main mistakes, phrases to learn.

Built so that a small local model cannot invent things:
- main mistakes come from the stored corrections (real examples, stable category
  ids), with the explanation given at correction time as the tip;
- phrases for ready-made scenarios are hand-picked (scenario_phrases.py);
- the LLM writes only the encouragement, and phrases for free conversation and
  custom scenarios (filtered so it cannot echo the partner or the learner's errors).
"""

import re
from collections import defaultdict

from . import corrections, llm_models, ollama_client, sessions
from .scenario_phrases import PHRASES
from .corrections import worker as correction_worker
from .db import now_iso
from .settings_store import get_level, get_settings

LANG_NAMES = {"tr": "Turkish", "en": "English"}
MAX_TRANSCRIPT_MESSAGES = 30  # keeps the prompt well inside the 4096-token context
MAX_MISTAKE_GROUPS = 3

PROMPT = """Here is the transcript of an English practice session. The learner is a Turkish speaker at CEFR level {level}{context}.

Transcript:
{transcript}

{mistakes}

Return JSON:
- "went_well": 2 short, concrete things THE LEARNER did well in their own messages. Do not praise a sentence that contains one of the mistakes above.{phrases_instruction}

IMPORTANT: write the "went_well" items in {lang}."""

PHRASES_INSTRUCTION = """
- "phrases_to_learn": 5 NEW useful English phrases that THE LEARNER{learner_part} could say in this kind of conversation, at about level {level}. Do not copy sentences from the transcript. Each {{"phrase", "meaning_tr" (correct Turkish meaning), "example" (one short sentence, no speaker label)}}."""

PHRASES_SCHEMA = {
    "phrases_to_learn": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {"phrase": {"type": "string"}, "meaning_tr": {"type": "string"},
                           "example": {"type": "string"}},
            "required": ["phrase", "meaning_tr", "example"],
        },
    },
}


class ReportError(Exception):
    pass


def _mistake_groups(by_message: dict[int, dict]) -> list[dict]:
    """Most frequent categories with the learner's real examples."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for c in by_message.values():
        for e in c["errors"]:
            groups[e["category"]].append(e)
    ranked = sorted(groups.items(), key=lambda kv: -len(kv[1]))[:MAX_MISTAKE_GROUPS]
    return [{"category": cid, "count": len(errs), "examples": errs[:3],
             # The explanation written at correction time doubles as the tip.
             "tip": next((e["explanation"] for e in errs if e.get("explanation")), "")}
            for cid, errs in ranked]


def _plain(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", (text or "").lower().replace("’", "'")))


def _curated_phrases(scenario_id: str, learner_text: str) -> list[dict]:
    """Hand-picked phrases; skip those the learner already used."""
    said = _plain(learner_text)
    picked = []
    for phrase, meaning, example in PHRASES.get(scenario_id, []):
        core = _plain(phrase.split("…")[0])
        if core and core in said:
            continue
        picked.append({"phrase": phrase, "meaning_tr": meaning, "example": example})
    return picked[:5]


def _clean_generated_phrases(items: list[dict], messages: list[dict], mistakes: list[str]) -> list[dict]:
    """Drop phrases that just repeat the partner's lines or the learner's mistakes."""
    partner = [_plain(m["text"]) for m in messages if m["role"] != "user"]
    wrong = [_plain(w) for w in mistakes]
    out = []
    for p in items:
        phrase = (p.get("phrase") or "").strip()
        key = _plain(phrase)
        if not key or any(key in line for line in partner) or any(w and w in key for w in wrong):
            continue
        example = re.sub(r"^\s*(learner|partner|you|me)\s*:\s*", "", p.get("example") or "", flags=re.I).strip()
        out.append({"phrase": phrase, "meaning_tr": (p.get("meaning_tr") or "").strip(), "example": example})
    return out[:5]


def _stats(user_messages: list[dict], by_message: dict[int, dict]) -> dict:
    counts = defaultdict(int)
    for c in by_message.values():
        for e in c["errors"]:
            counts[e["category"]] += 1
    return {
        "user_messages": len(user_messages),
        "checked": len(by_message),
        "perfect": sum(1 for c in by_message.values() if not c["errors"] and not c.get("not_english")),
        "error_count": sum(counts.values()),
        # Stable category ids, most frequent first — the same ids the error log uses.
        "categories": [{"id": cid, "count": n} for cid, n in sorted(counts.items(), key=lambda kv: -kv[1])],
    }


async def build(session_id: int) -> dict:
    session = sessions.get_session(session_id)
    if session is None:
        raise ReportError("Oturum bulunamadı.")
    user_messages = [m for m in session["messages"] if m["role"] == "user"]
    if not user_messages:
        raise ReportError("Bu oturumda henüz bir şey söylemedin, rapor oluşturulamadı.")

    # Corrections of the last messages may still be running.
    await correction_worker.wait_for({m["id"] for m in user_messages})
    by_message = corrections.for_session(session_id)
    groups = _mistake_groups(by_message)

    settings = get_settings()
    lang = LANG_NAMES.get(settings["explanation_language"], "Turkish")
    scenario = session["scenario"]
    transcript = "\n".join(
        f"{'LEARNER' if m['role'] == 'user' else 'PARTNER'}: {m['text']}"
        for m in session["messages"][-MAX_TRANSCRIPT_MESSAGES:]
    )
    all_mistakes = [e for c in by_message.values() for e in c["errors"]]
    mistakes = ("The learner's mistakes (wrong → right):\n" + "\n".join(f"- {e['wrong']} → {e['right']}" for e in all_mistakes)
                if all_mistakes else "The learner made no mistakes in this session.")
    curated = _curated_phrases(scenario["id"], " ".join(m["text"] for m in user_messages)) if scenario else []
    level = get_level()
    prompt = PROMPT.format(
        level=level,
        context=f", playing {scenario['learner_role']} and talking to {scenario['role']}" if scenario else "",
        transcript=transcript,
        mistakes=mistakes,
        lang=lang,
        phrases_instruction="" if curated else PHRASES_INSTRUCTION.format(
            learner_part=f" (as {scenario['learner_role']})" if scenario else "", level=level),
    )
    properties = {"went_well": {"type": "array", "items": {"type": "string"}}}
    if not curated:
        properties.update(PHRASES_SCHEMA)
    schema = {"type": "object", "properties": properties, "required": list(properties)}

    async with correction_worker.chat_priority():  # the learner is waiting for this
        raw = await ollama_client.chat_json(
            llm_models.current(), [{"role": "user", "content": prompt}], schema,
            # Same context size as chat: a different num_ctx makes Ollama reload the model.
            options={"temperature": 0.4, "num_predict": 600},
        )

    report = {
        "went_well": [s for s in raw.get("went_well") or [] if s][:3],
        "main_mistakes": [
            {"category": g["category"], "count": g["count"],
             "examples": [{"wrong": e["wrong"], "right": e["right"]} for e in g["examples"]],
             "tip": g["tip"]}
            for g in groups
        ],
        "phrases_to_learn": curated or _clean_generated_phrases(
            raw.get("phrases_to_learn") or [], session["messages"], [e["wrong"] for e in all_mistakes]),
        "stats": _stats(user_messages, by_message),
        "correction_mode": settings["correction_mode"],
        "created_at": now_iso(),
    }
    sessions.save_summary(session_id, report)
    return report
