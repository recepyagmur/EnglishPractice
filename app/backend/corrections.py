"""Grammar corrections of the learner's messages, computed in the background.

Ollama serves one request at a time on this hardware (a second slot would need
more VRAM), so corrections run only while no chat reply is being generated: a
chat turn pauses (cancels and re-queues) a correction in progress. The chat
reply is therefore never slowed down by corrections.
"""

import asyncio
import json
import logging
import re
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from . import errors, llm_models, ollama_client, pronoun_check
from .db import get_conn, now_iso
from .ollama_client import OllamaError
from .settings_store import get_level, get_settings

log = logging.getLogger("corrections")

LANG_NAMES = {"tr": "Turkish", "en": "English"}

# The parts that change with every sentence (how it was produced, the context, the sentence) come
# LAST: Ollama keeps the start of the prompt cached, so only the end is read again. On a computer
# without a GPU this halves the time of a correction.
PROMPT = """You are an English teacher. Analyze the learner's sentence at the end of this message, written or spoken by a Turkish learner at CEFR level {level}.
Only flag real grammar or vocabulary errors, not stylistic preferences. If the sentence is correct, return no errors.
Turkish speakers often: drop the verb "be" ("I very happy"), drop articles, confuse he/she, forget the third-person -s, and put question words in the wrong order. Every such mistake is an error, even if the meaning is clear.
Turkish has one word ("o") for he, she and it, so check every he/she/him/her/his against the person it refers to, also in an earlier sentence: sister, mother, wife, daughter, aunt, girl, woman → she/her; brother, father, husband, son, uncle, boy, man → he/him/his.

For each error give the exact wrong words ("wrong"), the fix ("right"), one category, and a very short explanation (max one sentence). List each error only once. Anything you change in "corrected" must appear in "errors".
Categories:
{categories}

"corrected": the whole sentence with all errors fixed and nothing else changed.
"more_natural": a more native-sounding way to say the same thing, or null if it is already natural.

IMPORTANT: write every "explanation" in {explanation_language}.{example}

The sentence below was {source_note}. {ignore_note}
Learner's sentence: "{text}"
"""

# One worked example per explanation language keeps small models on format and language.
EXAMPLES = {
    "tr": """
Example — sentence "she very busy and go to work early":
{"has_errors": true, "corrected": "she is very busy and goes to work early", "errors": [
 {"wrong": "she very", "right": "she is very", "category": "Missing Word", "explanation": "Sıfattan önce 'be' fiili (is) gerekir."},
 {"wrong": "go", "right": "goes", "category": "Subject-Verb Agreement", "explanation": "Üçüncü tekil şahısta (she) fiile -s eklenir."}],
 "more_natural": "She's very busy and goes to work early."}""",
    "en": """
Example — sentence "she very busy and go to work early":
{"has_errors": true, "corrected": "she is very busy and goes to work early", "errors": [
 {"wrong": "she very", "right": "she is very", "category": "Missing Word", "explanation": "An adjective needs the verb 'be' (is) before it."},
 {"wrong": "go", "right": "goes", "category": "Subject-Verb Agreement", "explanation": "With he/she/it the verb takes -s."}],
 "more_natural": "She's very busy and goes to work early."}""",
}


def _schema(spoken: bool) -> dict:
    return {
        "type": "object",
        "properties": {
            "has_errors": {"type": "boolean"},
            "corrected": {"type": "string"},
            "errors": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "wrong": {"type": "string"},
                        "right": {"type": "string"},
                        "category": {"type": "string", "enum": errors.names(spoken)},
                        "explanation": {"type": "string"},
                    },
                    "required": ["wrong", "right", "category", "explanation"],
                },
            },
            "more_natural": {"type": ["string", "null"]},
        },
        "required": ["has_errors", "corrected", "errors", "more_natural"],
    }


def _plain(text: str) -> str:
    """Lower-case words only — differences in punctuation/capitalization don't count."""
    return " ".join(re.findall(r"[a-z0-9']+", (text or "").lower().replace("’", "'")))


SOURCE_NOTES = {
    # source: (how the text was produced, what to ignore / check)
    "voice": ("spoken (speech transcript)",
              "It is a speech transcript: ignore punctuation, capitalization and spelling."),
    "text": ("typed in a chat", "Ignore missing final punctuation and capitalization."),
    "writing": ("written as part of a longer text (email, essay…)",
                "Also flag spelling, capitalization and punctuation errors. In English, days, months, "
                "nationalities and languages start with a capital letter (Saturday, March, Turkish, English) "
                "— Turkish speakers often forget this."),
}


# Below this share of dictionary words a chat message is "not English" (Turkish, random letters).
MIN_ENGLISH_SHARE = 0.5


def not_english(text: str) -> bool:
    from .dictionary import english_share  # dictionary imports this module

    share = english_share(text)
    return share is not None and share < MIN_ENGLISH_SHARE


async def analyze(text: str, source: str, context: str = "") -> dict:
    """Ask the LLM for corrections; returns a cleaned result.

    context: the previous sentence(s), shown to the model but not corrected.
    Chat messages that are not English are not sent to the LLM (it calls them perfect):
    the result has not_english=True and no errors."""
    if source in ("voice", "text") and not_english(text):
        return {"has_errors": False, "not_english": True, "original": text, "corrected": text,
                "errors": [], "more_natural": None}
    settings = get_settings()
    spoken = source == "voice"
    source_note, ignore_note = SOURCE_NOTES.get(source, SOURCE_NOTES["text"])
    if context:
        ignore_note += ("\nFor context only (do not correct it), the text before this sentence was: "
                        f'"{context[-300:]}"')
        # he/she against a person in the context is checked by pronoun_check (the LLM over-flags it).
    prompt = PROMPT.format(
        source_note=source_note,
        ignore_note=ignore_note,
        level=get_level(),
        explanation_language=LANG_NAMES.get(settings["explanation_language"], "Turkish"),
        example=EXAMPLES.get(settings["explanation_language"], EXAMPLES["tr"]),
        categories=errors.prompt_lines(spoken),
        text=text.replace('"', "'"),
    )
    raw = await ollama_client.chat_json(
        llm_models.current(),
        [{"role": "user", "content": prompt}],
        _schema(spoken),
        options={"temperature": 0, "num_predict": 400},
    )
    result = _add_pronoun_errors(_clean(text, raw, spoken), context, settings["explanation_language"])
    return {**result, "corrected": _keep_case(text, result["corrected"])}


def _keep_case(original: str, corrected: str) -> str:
    """Some models lower-case the whole corrected sentence (the prompt's example starts in lower
    case): keep the learner's capital first letter, and "I" is always a capital."""
    corrected = re.sub(r"\bi\b", "I", corrected)  # also i'm, i've
    if original[:1].isupper() and corrected[:1].islower():
        corrected = corrected[0].upper() + corrected[1:]
    return corrected


def _add_pronoun_errors(result: dict, context: str, lang: str) -> dict:
    """he/she that does not match the person mentioned before (rule-based; the LLM misses these
    when the person is in an earlier sentence)."""
    found = [e for e in pronoun_check.find_errors(context, result["original"], lang)
             if not any(f" {e['wrong'].lower()} " in f" {_plain(x['wrong'])} " for x in result["errors"])]
    if not found:
        return result
    return {**result, "has_errors": True, "errors": result["errors"] + found,
            "corrected": pronoun_check.apply(result["corrected"], found)}


def _clean(original: str, raw: dict, spoken: bool) -> dict:
    found, seen = [], set()
    for e in raw.get("errors") or []:
        wrong, right = (e.get("wrong") or "").strip(), (e.get("right") or "").strip()
        category = errors.normalize(e.get("category"))
        # Small models sometimes "fix" things that are identical or only differ in
        # punctuation, or list the same error twice.
        key = (_plain(wrong), _plain(right))
        if key[0] == key[1] or key in seen:
            continue
        seen.add(key)
        if spoken and category in errors.WRITTEN_ONLY:
            continue
        found.append({"wrong": wrong, "right": right, "category": category,
                      "explanation": (e.get("explanation") or "").strip()})

    # Drop an error contained in a larger one: same category ("you"→"are you" inside
    # "Where you are going"→…), or the same fix seen wider ("start"→"will start" inside
    # "it start"→"it will start", even if the model gave them different categories).
    def inside(a: str, b: str) -> bool:
        return f" {_plain(a)} " in f" {_plain(b)} "

    found = [
        e for e in found
        if not any(o is not e and len(o["wrong"]) > len(e["wrong"]) and inside(e["wrong"], o["wrong"])
                   and (o["category"] == e["category"] or inside(e["right"], o["right"]))
                   for o in found)
    ]

    corrected = (raw.get("corrected") or "").strip() or original
    if not found or _plain(corrected) == _plain(original):
        found, corrected = [], original
    more_natural = (raw.get("more_natural") or "").strip() or None
    if more_natural and _plain(more_natural) in (_plain(original), _plain(corrected)):
        more_natural = None
    return {"has_errors": bool(found), "not_english": False, "original": original, "corrected": corrected,
            "errors": found, "more_natural": more_natural}


def save(message_id: int, source: str, result: dict) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO corrections (message_id, original, corrected, errors_json, more_natural, source,"
            " not_english, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (message_id, result["original"], result["corrected"], json.dumps(result["errors"], ensure_ascii=False),
             result["more_natural"], source, int(result.get("not_english", False)), now_iso()),
        )
        correction_id = cur.lastrowid
        for e in result["errors"]:
            conn.execute(
                "INSERT INTO error_log (correction_id, message_id, source, category, wrong, right, explanation,"
                " taxonomy_version, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (correction_id, message_id, source, e["category"], e["wrong"], e["right"], e["explanation"],
                 errors.TAXONOMY_VERSION, now_iso()),
            )
    return correction_id


def _message_exists(message_id: int) -> bool:
    with get_conn() as conn:
        return conn.execute("SELECT 1 FROM messages WHERE id = ?", (message_id,)).fetchone() is not None


def for_session(session_id: int) -> dict[int, dict]:
    """Corrections of a session keyed by message id."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT c.* FROM corrections c JOIN messages m ON m.id = c.message_id WHERE m.session_id = ?",
            (session_id,),
        ).fetchall()
    return {r["message_id"]: to_payload(r) for r in rows}


def to_payload(row) -> dict:
    errs = json.loads(row["errors_json"] or "[]")
    return {"message_id": row["message_id"], "original": row["original"], "corrected": row["corrected"],
            "errors": errs, "has_errors": bool(errs), "more_natural": row["more_natural"],
            "not_english": bool(row["not_english"])}


# ------------------------------------------------------------------ worker

@dataclass
class Job:
    message_id: int
    text: str
    source: str
    notify: Callable[[dict], Awaitable[None]] | None = None
    context: str = ""  # what the AI said just before (e.g. "Tell me about your sister" → "she")
    attempts: int = field(default=0)


class CorrectionWorker:
    """Runs corrections one by one, only while no chat reply is being generated."""

    MAX_ATTEMPTS = 3

    def __init__(self) -> None:
        self.queue: deque[Job] = deque()
        self.chat_busy = 0
        self.current: asyncio.Task | None = None
        self.current_job: Job | None = None
        self._changed = asyncio.Event()
        self._runner: asyncio.Task | None = None

    def start(self) -> None:
        self._runner = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._runner:
            self._runner.cancel()

    def submit(self, job: Job) -> None:
        self.queue.append(job)
        self._changed.set()

    def pending(self, message_ids: set[int]) -> bool:
        running = self.current and not self.current.done() and self.current_job.message_id in message_ids
        return bool(running) or any(j.message_id in message_ids for j in self.queue)

    async def wait_for(self, message_ids: set[int], timeout: float = 300) -> bool:  # slow CPU-only laptops
        """Wait until these messages are corrected (e.g. before a session report)."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while self.pending(message_ids):
            if loop.time() > deadline:
                return False
            await asyncio.sleep(0.3)
        return True

    @asynccontextmanager
    async def chat_priority(self):
        """Wrap a chat LLM call: pauses any running correction until the chat is done.
        Waits first while a model is being loaded or speed-tested."""
        await llm_models.manager.wait_idle()
        async with self.pause():
            yield

    @asynccontextmanager
    async def pause(self):
        """No corrections run inside this block (a running one is re-queued)."""
        self.chat_busy += 1
        if self.current and not self.current.done():
            self.current.cancel()  # re-queued by _run
        try:
            yield
        finally:
            self.chat_busy -= 1
            self._changed.set()

    async def _run(self) -> None:
        while True:
            while not self.queue or self.chat_busy:
                self._changed.clear()
                await self._changed.wait()
            job = self.queue.popleft()
            self.current_job = job
            self.current = asyncio.create_task(self._process(job))
            await asyncio.wait({self.current})
            if self.current.cancelled():
                self.queue.appendleft(job)  # paused by a chat turn: same job first
            elif self.current.exception() is not None:
                log.error("correction crashed for message %s", job.message_id, exc_info=self.current.exception())
            elif self.current.result() == "retry":
                self.queue.append(job)

    async def _process(self, job: Job) -> str:
        try:
            result = await analyze(job.text, job.source, job.context)
        except OllamaError as e:
            job.attempts += 1
            log.warning("correction failed (attempt %d): %s", job.attempts, e)
            return "retry" if job.attempts < self.MAX_ATTEMPTS else "failed"
        if not _message_exists(job.message_id):
            return "done"  # session deleted meanwhile
        save(job.message_id, job.source, result)
        if job.notify:
            try:
                await job.notify({"message_id": job.message_id, **result})
            except Exception:
                pass  # the browser went away; the correction is saved anyway
        return "done"


worker = CorrectionWorker()
