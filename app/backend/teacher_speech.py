"""The teacher's reply read aloud in two voices: Turkish parts by the Turkish voice (tts_tr.py), English
parts by the English one (Kokoro, tts.py) — the Turkish model would read English with Turkish spelling,
which must never be what the learner hears.

Which part is English:
- example lines "- I have worked here. (Burada çalıştım.) …": the sentence is English, the brackets Turkish;
- **bold** or "quoted" text without Turkish letters whose words are mostly English;
- other words without Turkish letters that the English dictionary knows and Turkish does not use
  ("since kullanılır" → since is English; "son", "her", "program" stay Turkish: they are Turkish words too).
Turkish words come from the Turkish side of the offline dictionary (dictionary.db tr_json).
"""

import json
import re
import threading

from . import dictionary
from .config import APP_DIR

TURKISH_LETTERS = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
EXAMPLE = re.compile(r"^(.*?)\s*\(([^()]*)\)\s*(?:[-–—:]\s*)?(.*)$")
QUOTED = re.compile(r"\*\*(.+?)\*\*|\"([^\"]+)\"|“([^”]+)”")
TOKEN = re.compile(r"([^\W\d_]+(?:['’][^\W\d_]+)*)|([^\w]+|\d+)")
PREFIX = re.compile(r"^(?:[-*•]\s+|>\s*|💡\s*|✏️\s*)")

_turkish: set[str] | None = None
_english_lists: set[str] | None = None
_lock = threading.Lock()


def _list_words() -> set[str]:
    """The level word lists (app/content/vocab): English words the dictionary may miss ("homework")."""
    global _english_lists
    with _lock:
        if _english_lists is None:
            words = set()
            for path in (APP_DIR / "content" / "vocab").glob("*.json"):
                words.update(w["w"].lower() for w in json.loads(path.read_text(encoding="utf-8"))["words"])
            _english_lists = words
    return _english_lists


def _turkish_words() -> set[str]:
    """Words of the Turkish translations in the dictionary (built once, ~a second)."""
    global _turkish
    with _lock:
        if _turkish is None:
            words = set()
            if dictionary.available():
                for (tr_json,) in dictionary._conn().execute("SELECT tr_json FROM entries"):
                    for t in json.loads(tr_json):
                        words.update(w.lower() for w in re.findall(r"[^\W\d_]+", t.get("word", "")))
            _turkish = words
    return _turkish


def _word_kind(word: str) -> str:
    """"en": English only; "amb": both languages have it ("do", "a", "for", "son"); "tr": everything else —
    Turkish letters, Turkish words, and words neither side knows (mostly inflected Turkish: "demelisin")."""
    w = word.lower().replace("’", "'")
    if TURKISH_LETTERS.search(word):
        return "tr"
    english = dictionary.is_english_word(w) or w in _list_words()
    turkish = w in _turkish_words() or w.split("'")[0] in _turkish_words()
    if english:
        return "amb" if turkish else "en"
    return "tr"


def _english_text(text: str) -> bool:
    if TURKISH_LETTERS.search(text):
        return False
    share = dictionary.english_share(text)
    return share is not None and share >= 0.5


def _plain(text: str, out: list) -> None:
    """Unquoted text, word by word (an English base with a Turkish suffix: "since'den" → since + den)."""
    for word, other in TOKEN.findall(text):
        if not word:
            out.append([None, other])  # spaces / punctuation / digits: go with the part before them
            continue
        base, apostrophe, suffix = word.replace("’", "'").partition("'")
        kind = _word_kind(word)
        if kind != "en" and apostrophe and _word_kind(base) == "en":
            out += [["en", base], ["tr", suffix]]
        else:
            out.append([kind, word])


def _resolve(items: list) -> None:
    """A word of both languages takes its neighbours' language: English when the nearest decided words on
    both sides are English (or one side is English and the other is the end of the line)."""
    words = [i for i, (kind, _) in enumerate(items) if kind is not None]
    decided = [items[i][0] if items[i][0] != "amb" else None for i in range(len(items))]
    for n, i in enumerate(words):
        if items[i][0] != "amb":
            continue
        left = next((decided[j] for j in reversed(words[:n]) if decided[j]), None)
        right = next((decided[j] for j in words[n + 1:] if decided[j]), None)
        items[i][0] = "en" if {left, right} <= {"en", None} and "en" in (left, right) else "tr"


def _inline(text: str, out: list) -> None:
    items, pos = [], 0
    for m in QUOTED.finditer(text):
        _plain(text[pos:m.start()], items)
        inner = next(g for g in m.groups() if g is not None)
        if _english_text(inner):
            items.append(["en", inner])
        else:
            _plain(inner, items)
        pos = m.end()
    _plain(text[pos:], items)
    _resolve(items)
    out += items


def segments(reply: str) -> list[dict]:
    """[{"lang": "tr" | "en", "text"}] in reading order."""
    out: list = []
    for raw in reply.split("\n"):
        line = PREFIX.sub("", raw.strip()).strip()
        if not line:
            continue
        m = EXAMPLE.match(line.replace("**", ""))
        bullet = re.match(r"^[-*•]\s+", raw.strip())
        if bullet and m and m.group(1).strip() and _english_text(m.group(1)):
            out.append(["en", m.group(1).strip().strip("\"“”")])
            out.append([None, " "])
            out.append(["tr", m.group(2)])
            if m.group(3):
                out.append([None, " "])
                _inline(m.group(3), out)
        else:
            _inline(line, out)
        out.append([None, "\n"])
    # Join: spaces/punctuation stay with the part before them; neighbours of one language merge.
    merged: list[list] = []
    for lang, text in out:
        if lang is None:
            if merged:
                merged[-1][1] += " " if text == "\n" else text
            continue
        if merged and merged[-1][0] == lang:
            merged[-1][1] += text
        else:
            merged.append([lang, text])
    result = []
    for lang, text in merged:
        text = re.sub(r"\s+", " ", text.replace("**", "")).strip()
        # a bracket cut off from its other half by a change of voice ("çıktı (" / "output)") is not read
        if text.count("(") != text.count(")"):
            text = text.replace("(", " ").replace(")", " ").strip()
        if re.search(r"[^\W\d_]|\d", text):  # something to read
            result.append({"lang": lang, "text": text})
    return result
