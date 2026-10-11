"""Level word lists (A1–C1) for vocabulary study: cards, quizzes and checked example sentences.

The lists (app/content/vocab/<LEVEL>.json) come from the CEFR-J Wordlist and the Octanove C1 profile;
the Turkish meanings were checked by hand (format and sources: app/content/vocab/README.md).
Words being learned live in the vocabulary notebook (vocab.py) with spaced repetition, so the
notebook's daily review and this page share the same schedule.

Example sentences are made by the LLM only when the learner asks, and a sentence is shown only if
the correction engine finds no error in it, it really contains the word, and its Turkish translation
passes a separate check (checked_turkish). Accepted ones are kept.
"""

import json
import re

from . import llm_models, ollama_client, vocab
from .config import APP_DIR
from .corrections import analyze, not_english
from .corrections import worker as correction_worker
from .db import get_conn, now_iso
from .settings_store import get_level

CONTENT_DIR = APP_DIR / "content" / "vocab"
LEVELS = ["A1", "A2", "B1", "B2", "C1"]
LEARNED_INTERVAL = 21  # days, as in the notebook ("öğrenildi")
MAX_EXAMPLES = 6       # kept per word

POS_TR = {"noun": "isim", "verb": "fiil", "adjective": "sıfat", "adverb": "zarf", "pronoun": "zamir",
          "preposition": "edat", "determiner": "belirleyici", "conjunction": "bağlaç", "number": "sayı",
          "interjection": "ünlem", "modal auxiliary": "yardımcı fiil", "be-verb": "fiil", "do-verb": "fiil",
          "have-verb": "fiil"}


def _load() -> dict[str, list[dict]]:
    out = {}
    for level in LEVELS:
        path = CONTENT_DIR / f"{level}.json"
        if path.exists():
            out[level] = json.loads(path.read_text(encoding="utf-8"))["words"]
    return out


WORDS = _load()
BY_WORD = {w["w"].lower(): {**w, "level": lv} for lv, ws in WORDS.items() for w in ws}

# The most frequent English words (app/content/vocab/top3000.json): New General Service List 1.2 (Browne, Culligan
# & Phillips, CC BY-SA 4.0) plus the next most frequent words of its corpus, in frequency order. A word that is in a
# level list takes its checked meaning from there (one meaning per word, and the same notebook entry); the file
# only carries meanings for the words no level list has. Format: app/content/vocab/README.md.
FREQ_ID = "TOP3000"
FREQ_LABEL = "⭐ En sık 3000"


def _load_freq() -> list[dict]:
    path = CONTENT_DIR / "top3000.json"
    if not path.exists():
        return []
    out = []
    for item in json.loads(path.read_text(encoding="utf-8"))["words"]:
        base = BY_WORD.get(item["w"].lower())
        if base:
            entry = {**{k: v for k, v in base.items() if k != "level"}, "cefr": base["level"]}
        else:
            entry = {k: v for k, v in item.items() if k in ("w", "pos", "tr", "ipa")}
            entry["cefr"] = None
        entry["rank"] = item["rank"]
        out.append(entry)
    return out


FREQ = _load_freq()
for _f in FREQ:  # words only in the frequency list: learnable like the others (their notebook level is the list)
    BY_WORD.setdefault(_f["w"].lower(), {**{k: v for k, v in _f.items() if k not in ("rank", "cefr")}, "level": FREQ_ID})
LISTS = LEVELS + ([FREQ_ID] if FREQ else [])


def _status(rows: dict, word: str) -> dict:
    v = rows.get(vocab.word_key(word))
    if v is None:
        return {"status": "new", "vocab_id": None}
    return {"status": "learned" if v["interval"] >= LEARNED_INTERVAL else "learning", "vocab_id": v["id"],
            "due": v["due_date"]}


def _notebook() -> dict:
    with get_conn() as conn:
        rows = conn.execute("SELECT id, word, interval, due_date FROM vocab").fetchall()
    return {vocab.word_key(r["word"]): dict(r) for r in rows}


def overview() -> dict:
    nb = _notebook()
    levels = []
    for level in LEVELS:
        ws = WORDS.get(level, [])
        st = [_status(nb, w["w"])["status"] for w in ws]
        levels.append({"level": level, "total": len(ws), "learning": st.count("learning"), "learned": st.count("learned")})
    if FREQ:
        st = [_status(nb, w["w"])["status"] for w in FREQ]
        levels.append({"level": FREQ_ID, "label": FREQ_LABEL, "kind": "frequency", "total": len(FREQ),
                       "learning": st.count("learning"), "learned": st.count("learned")})
    return {"levels": levels, "my_level": get_level(), "due": vocab.stats()["due"]}


def level_words(level: str) -> list[dict]:
    nb = _notebook()
    words = FREQ if level == FREQ_ID else WORDS.get(level, [])
    return [{**w, "pos_tr": ", ".join(dict.fromkeys(POS_TR.get(p, p) for p in w["pos"])), **_status(nb, w["w"])}
            for w in words]


def learn(words: list[str]) -> list[dict]:
    """Put list words into the notebook (due today: the study session quizzes them right away)."""
    out = []
    for word in words:
        w = BY_WORD.get(word.lower())
        if not w:
            continue
        entry, _ = vocab.add(w["w"], meaning_tr=w["tr"], ipa=w.get("ipa") or "", source="list",
                             level=w["level"], pos=", ".join(w["pos"]))
        out.append(entry)
    return out


# ------------------------------------------------------------- examples

EXAMPLE_PROMPT = """Write {n} different example sentences for a Turkish learner of English at CEFR level {level}.
Each sentence must use the English word "{word}" ({pos}) with this meaning: "{tr}" (Turkish).
- Natural, correct, everyday or work-life English; 6 to 14 words; vocabulary at the {level} level.
- You may use a grammatical form of the word (plural, past tense, -ing…), but the word must be in the sentence.
- For each sentence, give an accurate, natural Turkish translation.
- Do not write sentences about violence, illness, death or other upsetting topics."""

EXAMPLE_SCHEMA = {
    "type": "object",
    "properties": {"examples": {"type": "array", "items": {
        "type": "object", "properties": {"en": {"type": "string"}, "tr": {"type": "string"}},
        "required": ["en", "tr"]}}},
    "required": ["examples"],
}


TR_CHECK_PROMPT = """You check Turkish translations of English sentences for a language-learning app. The Turkish must be
correct and natural: right case suffixes (-ı/-i, -e/-a, -de/-da…), verb endings, word order and spelling, no
repeated words, no apostrophe after a number written in letters, and the same meaning as the English.
English: {en}
Turkish: {tr}
If the Turkish is already correct and natural, return it unchanged. Otherwise return the corrected Turkish.
Answer with JSON: {{"ok": true|false, "turkish": "..."}}"""
TR_CHECK_SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}, "turkish": {"type": "string"}},
                   "required": ["ok", "turkish"]}


async def _tr_ok(model: str, en: str, tr: str) -> tuple[bool, str]:
    r = await ollama_client.chat_json(model, [{"role": "user", "content": TR_CHECK_PROMPT.format(en=en, tr=tr)}],
                                      TR_CHECK_SCHEMA, options={"temperature": 0, "num_predict": 200})
    return bool(r.get("ok")), (r.get("turkish") or "").strip()


async def checked_turkish(model: str, en: str, own_tr: str) -> str | None:
    """A Turkish translation that passed the check, or None. Candidates: the app's translation prompt
    (tested to be the better one) and the translation written with the sentence; a corrected version
    is accepted only if it passes the check itself."""
    from .dictionary import CHAT_MODEL_TRANSLATE_PROMPT

    translated = (await ollama_client.complete(model, CHAT_MODEL_TRANSLATE_PROMPT.format(text=en),
                                               options={"temperature": 0, "num_predict": 200}))
    translated = translated.strip().removeprefix("Turkish:").strip().strip('"')
    fixed = ""
    for tr in dict.fromkeys(t for t in (translated, own_tr) if t):
        ok, suggestion = await _tr_ok(model, en, tr)
        if ok:
            return tr
        fixed = fixed or suggestion
    if fixed:
        ok, _ = await _tr_ok(model, en, fixed)
        if ok:
            return fixed
    return None


def word_forms(word: str) -> set[str]:
    """The word and its inflected forms (from the offline dictionary, plus regular endings)."""
    w = word.lower()
    forms = {w, w + "s", w + "es", w + "ed", w + "d", w + "ing", w + "er", w + "est"}
    if w.endswith("e"):
        forms |= {w[:-1] + "ing", w[:-1] + "ed"}
    if w.endswith("y"):
        forms |= {w[:-1] + "ies", w[:-1] + "ied"}
    if len(w) > 2 and w[-1] not in "aeiouwy" and w[-2] in "aeiou":  # stop → stopped, stopping
        forms |= {w + w[-1] + "ed", w + w[-1] + "ing"}
    try:
        from .dictionary import _conn

        forms |= {r[0].lower() for r in _conn().execute(
            "SELECT form FROM forms WHERE lemma = ? COLLATE NOCASE", (word,))}
    except Exception:  # dictionary not installed
        pass
    return forms


def contains_word(sentence: str, word: str) -> bool:
    low = sentence.lower().replace("’", "'")
    if " " in word or "-" in word or "." in word:  # "CD player", "a.m."
        return word.lower() in low
    tokens = set(re.findall(r"[a-z]+(?:'[a-z]+)?", low))
    return bool(tokens & word_forms(word))


def examples(word: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT id, en, tr FROM word_examples WHERE word = ? COLLATE NOCASE ORDER BY id",
                            (word,)).fetchall()
    return [dict(r) for r in rows]


async def generate_examples(word: str, n: int = 2) -> dict:
    """Make new example sentences for a word; only checked ones are kept and returned.
    {"examples": all kept ones, "added": how many new, "rejected": how many failed the check}"""
    w = BY_WORD.get(word.lower()) or {"w": word, "pos": [], "tr": "", "level": get_level()}
    have = examples(w["w"])
    if len(have) >= MAX_EXAMPLES:
        return {"examples": have, "added": 0, "rejected": 0}
    known = {e["en"].lower() for e in have}
    added = rejected = 0
    model = llm_models.current()
    async with correction_worker.chat_priority():  # the learner is waiting
        for _ in range(2):  # a second round only if the first gave too few good sentences
            raw = await ollama_client.chat_json(
                model,
                [{"role": "user", "content": EXAMPLE_PROMPT.format(
                    n=n + 1, level=w["level"], word=w["w"], pos=", ".join(w["pos"]) or "word",
                    tr=w["tr"] or "its most common meaning")}],
                EXAMPLE_SCHEMA,
                options={"temperature": 0.7, "num_predict": 500},
            )
            for ex in raw.get("examples") or []:
                en, tr = (ex.get("en") or "").strip(), (ex.get("tr") or "").strip()
                if not en or not tr or en.lower() in known or added >= n:
                    continue
                ok = contains_word(en, w["w"]) and not (await analyze(en, "writing"))["errors"]
                tr = await checked_turkish(model, en, tr) if ok else None
                if not tr:  # the English or the Turkish did not pass its check
                    rejected += 1
                    continue
                known.add(en.lower())
                with get_conn() as conn:
                    conn.execute("INSERT INTO word_examples (word, en, tr, model, created_at) VALUES (?, ?, ?, ?, ?)",
                                 (w["w"], en, tr, model, now_iso()))
                added += 1
            if added >= n:
                break
    return {"examples": examples(w["w"]), "added": added, "rejected": rejected}


def delete_example(example_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM word_examples WHERE id = ?", (example_id,))


# ------------------------------------------------------- own sentence

JUDGE = """A learner wrote an English sentence to practise the word "{word}" (meaning in Turkish: "{tr}").
Sentence: "{text}"
Answer with JSON: "uses_word": does the sentence contain the word "{word}" (any grammatical form of it)?
"meaning_fits": is the word used with the given meaning (or a close one) and does the sentence make sense?"""
JUDGE_SCHEMA = {"type": "object", "properties": {"uses_word": {"type": "boolean"}, "meaning_fits": {"type": "boolean"}},
                "required": ["uses_word", "meaning_fits"]}


async def check_sentence(word: str, text: str) -> dict:
    """The learner's own sentence with the word: grammar (correction engine) + is the word used,
    with the right meaning. The Turkish verdict is written here, not by the LLM."""
    w = BY_WORD.get(word.lower()) or {"w": word, "tr": ""}
    text = text.strip()
    if not_english(text):
        return {"verdict": "wrong", "message_tr": "Bu İngilizce bir cümle gibi görünmüyor.", "correction": None}
    if len(re.findall(r"[A-Za-z']+", text)) < 3:
        return {"verdict": "wrong", "message_tr": "Çok kısa. Kelimeyle tam bir cümle kur.", "correction": None}
    if not contains_word(text, w["w"]):
        return {"verdict": "wrong", "message_tr": f"Cümlende “{w['w']}” kelimesi yok. Onu kullanarak bir cümle kur.",
                "correction": None}
    async with correction_worker.chat_priority():
        correction = await analyze(text, "text")
        judged = await ollama_client.chat_json(
            llm_models.current(),
            [{"role": "user", "content": JUDGE.format(word=w["w"], tr=w["tr"] or "its usual meaning",
                                                      text=text.replace('"', "'"))}],
            JUDGE_SCHEMA, options={"temperature": 0, "num_predict": 40})
    n = len(correction["errors"])
    if n:
        verdict, msg = "wrong", f"Cümlende {n} hata var — kırmızı kısımlar yanlış, yeşiller doğrusu."
    elif not judged.get("meaning_fits", True):
        verdict, msg = "warn", f"Dilbilgisi doğru ama “{w['w']}” bu cümlede “{w['tr']}” anlamıyla kullanılmamış gibi. Bir daha dene."
    else:
        verdict, msg = "ok", "Doğru! Kelimeyi doğru anlamda ve hatasız kullandın."
    return {"verdict": verdict, "message_tr": msg, "correction": correction}
