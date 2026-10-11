"""Offline English→Turkish dictionary lookup (data/dictionary.db, built by
setup/build_dictionary.py), with an LLM fallback for words it does not know and
for the meaning in a given sentence."""

import json
import re
import sqlite3
import threading

from . import llm_models, ollama_client
from .config import DATA_DIR
from .corrections import worker as correction_worker
from .settings_store import get_level

DB_PATH = DATA_DIR / "dictionary.db"
_local = threading.local()


def available() -> bool:
    return DB_PATH.exists()


def _conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    return conn


def normalize(word: str) -> str:
    word = word.strip().replace("’", "'")
    word = re.sub(r"^[^A-Za-z]+|[^A-Za-z]+$", "", word)
    return re.sub(r"'s$", "", word)


def _entries(word: str) -> list[dict]:
    rows = _conn().execute(
        "SELECT word, pos, ipa, tr_json, definitions_json, example FROM entries WHERE word = ? COLLATE NOCASE",
        (word,),
    ).fetchall()
    # Exact case first ("polish" before "Polish" when the click was lower-case).
    rows = sorted(rows, key=lambda r: r["word"] != word)
    return [{"word": r["word"], "pos": r["pos"], "ipa": r["ipa"], "translations": json.loads(r["tr_json"]),
             "definitions": json.loads(r["definitions_json"]), "example": r["example"]} for r in rows]


def _suffix_candidates(word: str) -> list[tuple[str, str]]:
    """Regular inflections the forms table may lack: (lemma, how)."""
    w = word.lower()
    rules = [
        ("ies", "y", "plural / 3rd person"), ("ied", "y", "past"), ("ves", "f", "plural"),
        ("es", "", "plural / 3rd person"), ("s", "", "plural / 3rd person"),
        ("ed", "", "past"), ("ed", "e", "past"), ("ing", "", "-ing form"), ("ing", "e", "-ing form"),
        ("er", "", "comparative"), ("est", "", "superlative"), ("ly", "", "adverb"),
    ]
    out = []
    for suffix, replacement, how in rules:
        if w.endswith(suffix) and len(w) - len(suffix) >= 2:
            stem = w[: -len(suffix)] + replacement
            out.append((stem, how))
            if len(stem) > 2 and stem[-1] == stem[-2] and suffix in ("ed", "ing", "er", "est"):
                out.append((stem[:-1], how))  # stopped → stop, bigger → big
    return out


# Which part of speech an inflection tag points to ("sounds" as 3rd person → verb first).
_TAG_POS = [
    (("third-person", "past", "participle", "gerund", "present"), "verb"),
    (("plural",), "noun"),
    (("comparative", "superlative"), "adj"),
]
MAX_ENTRIES = 4


def _row_label(tags: set[str]) -> str | None:
    """Turkish label for one inflection row (exact tag tokens, most specific first)."""
    if "past" in tags and "participle" in tags:
        return "geçmiş zaman / V3"
    if "past" in tags:
        return "geçmiş zaman"
    if "participle" in tags or "gerund" in tags:
        return "-ing hali"
    if "third-person" in tags and "singular" in tags:
        return "3. tekil şahıs (-s)"
    if "plural" in tags and not tags & {"first-person", "second-person", "third-person"}:
        return "çoğul"
    if "comparative" in tags:
        return "karşılaştırma (-er)"
    if "superlative" in tags:
        return "üstünlük (-est)"
    return None


def _via_tr(rows) -> str:
    """How the clicked form relates to the dictionary word ("went" → "geçmiş zaman")."""
    labels = [_row_label(set((r["tags"] or "").split(","))) for r in rows]
    labels = list(dict.fromkeys(l for l in labels if l))
    if "geçmiş zaman / V3" in labels and "geçmiş zaman" in labels:
        labels.remove("geçmiş zaman")
    return " / ".join(labels[:2]) or "çekimli hali"


def _pos_order(tags: str) -> list[str]:
    return [pos for keys, pos in _TAG_POS if any(k in tags for k in keys)]


# Short words and contractions the dictionary may not list as entries.
_COMMON = {"i", "a", "an", "the", "im", "ive", "ill", "id", "dont", "doesnt", "didnt", "isnt", "arent", "wasnt",
           "werent", "cant", "couldnt", "wont", "wouldnt", "shouldnt", "havent", "hasnt", "youre", "theyre", "were",
           "its", "lets", "thats", "whats", "ok", "okay", "yeah", "hi", "hello"}
_TEXT_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")


def is_english_word(raw: str) -> bool:
    word = normalize(raw).lower()
    if not word or not word.isascii():  # ç, ş, ğ, ı, ö, ü → not an English word
        return False
    if word.replace("'", "") in _COMMON:
        return True
    conn = _conn()
    if conn.execute("SELECT 1 FROM entries WHERE word = ? COLLATE NOCASE LIMIT 1", (word,)).fetchone():
        return True
    if conn.execute("SELECT 1 FROM forms WHERE form = ? COLLATE NOCASE LIMIT 1", (word,)).fetchone():
        return True
    return any(conn.execute("SELECT 1 FROM entries WHERE word = ? COLLATE NOCASE LIMIT 1", (stem,)).fetchone()
               for stem, _ in _suffix_candidates(word))


def english_share(text: str) -> float | None:
    """Share of the words that are English (offline dictionary). Turkish text and keyboard
    mashing score low; names lower it a little. None when the dictionary is not installed."""
    if not available():
        return None
    words = _TEXT_WORD.findall(text)
    if not words:
        return 0.0
    return sum(is_english_word(w) for w in words) / len(words)


def lookup(raw_word: str) -> dict:
    """{"query", "lemma", "via", "entries": [...]}; entries is empty when unknown."""
    word = normalize(raw_word)
    result = {"query": word, "lemma": word, "via": None, "entries": []}
    if not word or not available():
        return result
    entries = _entries(word)
    forms = _conn().execute("SELECT lemma, tags FROM forms WHERE form = ? COLLATE NOCASE", (word,)).fetchall()
    lemmas = list(dict.fromkeys(r["lemma"] for r in forms if r["lemma"].lower() != word.lower()))
    if lemmas:
        tags = ",".join(r["tags"] or "" for r in forms)
        lemma_entries = [e for lemma in lemmas for e in _entries(lemma)]
        # An inflected form: show the base word's meanings, the likely part of speech first.
        order = _pos_order(tags)
        lemma_entries.sort(key=lambda e: order.index(e["pos"]) if e["pos"] in order else len(order))
        if not entries:
            result.update(lemma=lemma_entries[0]["word"] if lemma_entries else lemmas[0], via=_via_tr(forms))
        entries += lemma_entries
    # Same word + part of speech + translations twice (separate etymologies): keep one.
    unique, seen = [], set()
    for e in entries:
        key = (e["word"].lower(), e["pos"], tuple(t["word"] for t in e["translations"][:3]))
        if key not in seen:
            seen.add(key)
            unique.append(e)
    entries = unique[:MAX_ENTRIES]
    if not entries:
        for stem, how in _suffix_candidates(word):
            entries = _entries(stem)
            if entries:
                result.update(lemma=entries[0]["word"], via=how)
                break
    result["entries"] = entries
    return result


EXPLAIN_PROMPT = """A Turkish learner of English (level {level}) clicked the word "{word}" in this sentence:
"{sentence}"

Give its meaning IN THIS SENTENCE:
- "meaning_tr": the Turkish meaning (1-4 words)
- "definition": a very simple English definition (max 12 words)
- "lemma": the dictionary form of the word"""

EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {"meaning_tr": {"type": "string"}, "definition": {"type": "string"}, "lemma": {"type": "string"}},
    "required": ["meaning_tr", "definition", "lemma"],
}


TRANSLATION_MODEL = "translategemma:4b"
# TranslateGemma's recommended prompt; it works for general chat models too.
TRANSLATE_PROMPT = ("You are a professional English (en) to Turkish (tr) translator. Your goal is to accurately "
                    "convey the meaning and nuances of the original English text while adhering to Turkish grammar, "
                    "vocabulary, and cultural sensitivities. Produce only the Turkish translation, without any "
                    "additional explanations or commentary. Please translate the following English text into "
                    "Turkish:\n\n\n{text}")

# For the chat model: asking for natural spoken Turkish with two short examples gave clearly
# better translations with the chat model (tested with qwen3:8b) than the TranslateGemma prompt (questions, conditionals, idioms).
CHAT_MODEL_TRANSLATE_PROMPT = (
    "Translate this English text into natural, fluent Turkish, the way a native Turkish speaker would say it in "
    "conversation. Keep the exact meaning (tense, who does what, questions stay questions). Use correct Turkish "
    "suffixes and word order. Output only the Turkish translation.\n\nExamples:\n"
    "English: Have you ever been to Paris?\nTurkish: Hiç Paris'e gittin mi?\n"
    "English: We usually eat out on Fridays.\nTurkish: Cuma günleri genelde dışarıda yemek yeriz.\n\n"
    "English: {text}\nTurkish:")


async def translate(text: str) -> dict:
    """English → Turkish with TranslateGemma when installed, else the chat model."""
    try:
        installed = await ollama_client.list_models()
    except ollama_client.OllamaError:
        installed = []
    model = TRANSLATION_MODEL if TRANSLATION_MODEL in installed else llm_models.current()
    prompt = TRANSLATE_PROMPT if model == TRANSLATION_MODEL else CHAT_MODEL_TRANSLATE_PROMPT
    async with correction_worker.chat_priority():
        result = await ollama_client.complete(model, prompt.format(text=text.strip()[:1500]),
                                              options={"temperature": 0, "num_predict": 300})
    translation = result.strip().removeprefix("Turkish:").strip().strip('"')
    return {"translation": translation, "model": model}


async def explain(word: str, sentence: str) -> dict:
    """Meaning of the word in context, from the LLM (marked as AI-generated in the UI)."""
    async with correction_worker.chat_priority():
        raw = await ollama_client.chat_json(
            llm_models.current(),
            [{"role": "user", "content": EXPLAIN_PROMPT.format(
                level=get_level(), word=normalize(word), sentence=sentence.replace('"', "'")[:400])}],
            EXPLAIN_SCHEMA,
            options={"temperature": 0, "num_predict": 120},
        )
    return {k: (raw.get(k) or "").strip() for k in ("meaning_tr", "definition", "lemma")}
