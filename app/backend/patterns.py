"""Patterns (🧩 Kalıplar): fixed expressions for work and everyday English, grammar frames, idioms and
phrasal verbs, A1–C1, studied like the level word lists (cards, quizzes, spaced repetition).

The content (app/content/patterns/<LEVEL>.json) is written by hand and audited independently; the
format and rules are in app/content/patterns/README.md. Learning progress lives in its own table
(pattern_progress, SM-2 as in vocab.py) — the vocabulary notebook stays for words.
"""

import json
import logging
import re
from datetime import date, timedelta

from . import llm_models, ollama_client, vocab
from .config import APP_DIR
from .corrections import analyze, not_english
from .corrections import worker as correction_worker
from .db import get_conn, log_practice, now_iso, rows_to_dicts
from .vocab import today
from .settings_store import get_level

CONTENT_DIR = APP_DIR / "content" / "patterns"
LEVELS = ["A1", "A2", "B1", "B2", "C1"]
LEARNED_INTERVAL = 21  # days, as in the notebook ("öğrenildi")

CATS_TR = {"business": "İş", "daily": "Günlük", "grammar": "Dilbilgisi", "idiom": "Deyim & phrasal"}
REGISTERS_TR = {"formal": "resmi", "neutral": "nötr", "informal": "samimi"}
TOPICS_TR = {
    "business": {
        "meetings": "toplantı", "email": "e-posta", "phone": "telefon", "requests": "rica",
        "opinions": "fikir belirtme", "agreeing": "katılma / katılmama", "presentations": "sunum",
        "negotiation": "pazarlık", "scheduling": "zaman planı", "problems": "sorun bildirme",
        "smalltalk_work": "iş yerinde sohbet", "clarifying": "netleştirme",
    },
    "daily": {
        "greetings": "selamlaşma", "shopping": "alışveriş", "directions": "yol tarifi", "restaurant": "restoran",
        "travel": "seyahat", "appointments": "randevu", "feelings": "duygular", "invitations": "davet",
        "apologies": "özür / teşekkür", "help": "yardım", "phone_daily": "telefon", "health": "sağlık",
    },
    "grammar": {
        "conditionals": "koşul", "wishes": "dilek / pişmanlık", "preferences": "tercih", "habits": "alışkanlık",
        "comparison": "karşılaştırma", "suggestions": "öneri", "obligation": "zorunluluk / izin",
        "reported": "aktarma", "passive": "edilgen", "questions": "soru", "time": "zaman", "purpose": "amaç / sebep",
    },
    "idiom": {"idioms": "deyim", "phrasal_verbs": "phrasal verb"},
}
# Patterns per category in each level file (content test).
DISTRIBUTION = {
    "A1": {"business": 10, "daily": 28, "grammar": 14, "idiom": 8},
    "A2": {"business": 14, "daily": 22, "grammar": 14, "idiom": 10},
    "B1": {"business": 20, "daily": 14, "grammar": 14, "idiom": 12},
    "B2": {"business": 22, "daily": 10, "grammar": 14, "idiom": 14},
    "C1": {"business": 22, "daily": 8, "grammar": 14, "idiom": 16},
}
CAT_CODE = {"business": "biz", "daily": "day", "grammar": "gra", "idiom": "idi"}
TERM_MARK = re.compile(r"\[(en|tr|key):([^\[\]]+)\]")
ID_RE = re.compile(r"^[abc][12]-(biz|day|gra|idi)-\d{3}$")
FIELDS = {"id", "p", "tr", "cat", "topic", "register", "note_tr", "examples"}
MAX_EXAMPLE_WORDS = 16


# ------------------------------------------------------------------ content

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().replace("’", "'")).strip()


def fixed_parts(p: str) -> list[str]:
    """The pattern's words around its ___ slots, without punctuation at their ends
    ("Could you ___, please?" → ["could you", "please"])."""
    parts = (norm(x).strip(" ,.;:!?…") for x in p.split("___"))
    return [x for x in parts if x]


def contains_pattern(sentence: str, p: str) -> bool:
    """Do the fixed parts of the pattern occur in the sentence, in order (case-insensitive)?"""
    s, at = norm(sentence), 0
    for part in fixed_parts(p):
        i = s.find(part, at)
        if i < 0:
            return False
        at = i + len(part)
    return True


def uses_pattern(sentence: str, p: str) -> bool:
    """The learner's sentence uses the pattern: the fixed parts in order, where a word may be an inflected
    form of the pattern's word ("moves the goalposts", "put it off" → "put ___ off") and contractions count
    as their long forms ("I am afraid" = "I'm afraid"). Punctuation is ignored."""
    from .exams import _words
    from .words import word_forms

    tokens = _words(sentence)
    at = 0
    for part in fixed_parts(p):
        want = _words(part)
        if not want:
            continue
        end = _match(tokens, want, at, word_forms)
        if end is None:
            return False
        at = end
    return True


def _match(tokens: list[str], want: list[str], start: int, forms) -> int | None:
    """Where `want` ends in `tokens` (from `start`): each word may be an inflected form, and up to two other
    words may come between consecutive words ("put the project off", "not only did we finish but we also")."""
    same = lambda tok, w: tok == w or tok in forms(w)  # noqa: E731
    for i in range(start, len(tokens)):
        if not same(tokens[i], want[0]):
            continue
        pos, ok = i + 1, True
        for w in want[1:]:
            nxt = next((k for k in range(pos, min(pos + 3, len(tokens))) if same(tokens[k], w)), None)
            if nxt is None:
                ok = False
                break
            pos = nxt + 1
        if ok:
            return pos
    return None


def plain(text: str) -> str:
    """Turkish note for the LLM / speech: the term markup as quotes."""
    return TERM_MARK.sub(lambda m: f'"{m.group(2)}"', text)


def validate(files: dict[str, dict]) -> list[str]:
    """Content mistakes in {level: file dict} (content test; logged at start-up)."""
    problems, seen_ids, seen_p = [], set(), {}
    for level, data in files.items():
        where = f"{level}.json"
        if data.get("level") != level:
            problems.append(f"{where}: level must be {level}")
        pats = data.get("patterns")
        if not isinstance(pats, list):
            problems.append(f"{where}: patterns must be a list")
            continue
        if data.get("count") != len(pats):
            problems.append(f"{where}: count {data.get('count')} ≠ {len(pats)} patterns")
        sources = data.get("sources") or []
        if len(sources) < 3 or not all(isinstance(s, dict) and str(s.get("url", "")).startswith("http") and s.get("title")
                                        for s in sources):
            problems.append(f"{where}: needs at least 3 sources with title + url")
        counts = {c: 0 for c in CATS_TR}
        for i, x in enumerate(pats, 1):
            w = f"{where} #{i} ({x.get('id', '?')})"
            if not isinstance(x, dict):
                problems.append(f"{w}: not an object")
                continue
            missing, extra = FIELDS - x.keys(), x.keys() - FIELDS
            if missing or extra:
                problems.append(f"{w}: fields missing {sorted(missing)} / unknown {sorted(extra)}")
                continue
            pid, p, cat = x["id"], x["p"], x["cat"]
            if not ID_RE.match(str(pid)) or not str(pid).startswith(f"{level.lower()}-{CAT_CODE.get(cat, '???')}-"):
                problems.append(f"{w}: id must look like {level.lower()}-{CAT_CODE.get(cat, 'xxx')}-001")
            if pid in seen_ids:
                problems.append(f"{w}: duplicate id")
            seen_ids.add(pid)
            if cat not in CATS_TR:
                problems.append(f"{w}: unknown cat {cat!r}")
            else:
                counts[cat] += 1
                if x["topic"] not in TOPICS_TR[cat]:
                    problems.append(f"{w}: unknown topic {x['topic']!r} for {cat}")
            if x["register"] not in REGISTERS_TR:
                problems.append(f"{w}: unknown register {x['register']!r}")
            if not isinstance(p, str) or not fixed_parts(p):
                problems.append(f"{w}: p must have words")
                continue
            if p.count("___") > 2 or re.search(r"(?<!_)_{1,2}(?!_)|_{4,}|\.\.\.|…", p):
                problems.append(f"{w}: slots are ___ (at most 2), no … in p")
            if re.search(r"\w___|___\w", p):
                problems.append(f"{w}: a slot must stand for a whole word (space around ___)")
            key = norm(p)
            if key in seen_p:
                problems.append(f"{w}: same pattern as {seen_p[key]}")
            seen_p[key] = pid
            for field in ("p", "tr"):
                if not str(x[field]).strip():
                    problems.append(f"{w}: empty {field}")
                if TERM_MARK.search(str(x[field])):
                    problems.append(f"{w}: no [en:] markup in {field}")
            if "___" in p and "…" not in x["tr"] and "..." not in x["tr"]:
                problems.append(f"{w}: tr should mark the slot with …")
            note = str(x["note_tr"])
            if not note.strip() or len(note) > 300:
                problems.append(f"{w}: note_tr must be 1–300 characters")
            if note.count("[") != note.count("]") or re.search(r"\[(?!en:|tr:|key:)", note):
                problems.append(f"{w}: note_tr markup must be [en:…]/[tr:…]/[key:…] and balanced")
            exs = x["examples"]
            if not isinstance(exs, list) or len(exs) != 2:
                problems.append(f"{w}: exactly 2 examples")
                continue
            for j, ex in enumerate(exs, 1):
                if not isinstance(ex, dict) or not str(ex.get("en", "")).strip() or not str(ex.get("tr", "")).strip():
                    problems.append(f"{w} example {j}: needs en and tr")
                    continue
                en = ex["en"].strip()
                if "\n" in en or not re.search(r"[.?!]$", en):
                    problems.append(f"{w} example {j}: one sentence ending with . ? or !")
                if len(re.findall(r"[A-Za-z0-9'’-]+", en)) > MAX_EXAMPLE_WORDS:
                    problems.append(f"{w} example {j}: more than {MAX_EXAMPLE_WORDS} words")
                if not contains_pattern(en, p):
                    problems.append(f"{w} example {j}: does not contain the pattern's fixed parts in order")
                if TERM_MARK.search(en) or TERM_MARK.search(ex["tr"]):
                    problems.append(f"{w} example {j}: no markup in examples")
        want = DISTRIBUTION.get(level, {})
        if want and counts != want:
            problems.append(f"{where}: category counts {counts} ≠ {want}")
    return problems


def _load() -> dict[str, dict]:
    out = {}
    for level in LEVELS:
        path = CONTENT_DIR / f"{level}.json"
        if path.exists():
            out[level] = json.loads(path.read_text(encoding="utf-8"))
    return out


log = logging.getLogger("patterns")
FILES = _load()
for _problem in validate(FILES):
    log.warning("pattern content: %s", _problem)
PATTERNS = {lv: f["patterns"] for lv, f in FILES.items()}
BY_ID = {x["id"]: {**x, "level": lv} for lv, xs in PATTERNS.items() for x in xs}


def _public(x: dict) -> dict:
    return {**x, "cat_tr": CATS_TR.get(x["cat"], x["cat"]), "topic_tr": TOPICS_TR.get(x["cat"], {}).get(x["topic"], x["topic"]),
            "register_tr": REGISTERS_TR.get(x["register"], x["register"])}


# ----------------------------------------------------------------- progress

def _progress() -> dict[str, dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM pattern_progress").fetchall()
    return {r["pattern_id"]: dict(r) for r in rows}


def _status(prog: dict, pid: str) -> dict:
    r = prog.get(pid)
    if r is None:
        return {"status": "new"}
    return {"status": "learned" if r["interval"] >= LEARNED_INTERVAL else "learning", "due": r["due_date"]}


def stats() -> dict:
    with get_conn() as conn:
        due = conn.execute("SELECT COUNT(*) FROM pattern_progress WHERE due_date <= ?", (today(),)).fetchone()[0]
        learning = conn.execute("SELECT COUNT(*) FROM pattern_progress").fetchone()[0]
        learned = conn.execute("SELECT COUNT(*) FROM pattern_progress WHERE interval >= ?", (LEARNED_INTERVAL,)).fetchone()[0]
    return {"due": due, "learning": learning, "learned": learned}


def overview() -> dict:
    prog = _progress()
    levels = []
    for level in LEVELS:
        xs = PATTERNS.get(level, [])
        st = [_status(prog, x["id"])["status"] for x in xs]
        levels.append({"level": level, "total": len(xs), "learning": st.count("learning"), "learned": st.count("learned")})
    return {"levels": levels, "my_level": get_level(), "cats": CATS_TR, **stats()}


def level_patterns(level: str) -> list[dict]:
    prog = _progress()
    return [{**_public(x), "level": level, **_status(prog, x["id"])} for x in PATTERNS.get(level, [])]


def learn(ids: list[str]) -> list[dict]:
    """Start learning patterns (due today: the study session quizzes them right away)."""
    out = []
    with get_conn() as conn:
        for pid in ids:
            if pid not in BY_ID:
                continue
            conn.execute("INSERT OR IGNORE INTO pattern_progress (pattern_id, due_date, created_at) VALUES (?, ?, ?)",
                         (pid, today(), now_iso()))
            row = conn.execute("SELECT * FROM pattern_progress WHERE pattern_id = ?", (pid,)).fetchone()
            out.append({**_public(BY_ID[pid]), **_status({pid: dict(row)}, pid)})
    return out


def due(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM pattern_progress WHERE due_date <= ? ORDER BY due_date, created_at LIMIT ?",
                            (today(), limit)).fetchall()
    out = []
    for r in rows_to_dicts(rows):
        x = BY_ID.get(r["pattern_id"])
        if x:
            out.append({**_public(x), **_status({x["id"]: r}, x["id"])})
    return out


def review(pid: str, grade: str) -> dict | None:
    with get_conn() as conn:
        card = conn.execute("SELECT * FROM pattern_progress WHERE pattern_id = ?", (pid,)).fetchone()
        if card is None:
            return None
        nxt = vocab.schedule(dict(card), grade)
        due_date = (date.today() + timedelta(days=nxt["interval"])).isoformat()
        conn.execute(
            "UPDATE pattern_progress SET ease = ?, interval = ?, repetitions = ?, due_date = ?, last_reviewed_at = ?,"
            " review_count = review_count + 1, lapses = lapses + ? WHERE pattern_id = ?",
            (nxt["ease"], nxt["interval"], nxt["repetitions"], due_date, now_iso(), nxt["lapse"], pid))
        row = conn.execute("SELECT * FROM pattern_progress WHERE pattern_id = ?", (pid,)).fetchone()
    log_practice("vocab", 0.5)
    return {**_public(BY_ID[pid]), **_status({pid: dict(row)}, pid)} if pid in BY_ID else dict(row)


def forget(pid: str) -> bool:
    """Take a pattern out of the learning list (its progress is deleted)."""
    with get_conn() as conn:
        return conn.execute("DELETE FROM pattern_progress WHERE pattern_id = ?", (pid,)).rowcount > 0


# --------------------------------------------------------- own sentence

JUDGE = """A learner practises the English expression "{p}" (meaning in Turkish: "{tr}"). Example of correct use: "{example}"
The learner wrote: "{text}"
Answer with JSON: "uses_pattern": does the sentence use this expression (the slot ___ may be filled with anything)?
"meaning_fits": is the expression used naturally, with its usual meaning, and does the sentence make sense?"""
JUDGE_SCHEMA = {"type": "object", "properties": {"uses_pattern": {"type": "boolean"}, "meaning_fits": {"type": "boolean"}},
                "required": ["uses_pattern", "meaning_fits"]}


async def check_sentence(pid: str, text: str) -> dict:
    """The learner's own sentence with the pattern: grammar (correction engine) + is the pattern used
    naturally. The Turkish verdict is written here, not by the LLM."""
    x = BY_ID.get(pid)
    if x is None:
        raise KeyError(pid)
    text = text.strip()
    if not_english(text):
        return {"verdict": "wrong", "message_tr": "Bu İngilizce bir cümle gibi görünmüyor.", "correction": None}
    if len(re.findall(r"[A-Za-z']+", text)) < 3:
        return {"verdict": "wrong", "message_tr": "Çok kısa. Kalıpla tam bir cümle kur.", "correction": None}
    if not uses_pattern(text, x["p"]):
        return {"verdict": "wrong", "message_tr": f"Cümlende “{x['p']}” kalıbı yok. Onu kullanarak bir cümle kur.",
                "correction": None}
    async with correction_worker.chat_priority():
        correction = await analyze(text, "text")
        judged = await ollama_client.chat_json(
            llm_models.current(),
            [{"role": "user", "content": JUDGE.format(p=x["p"], tr=x["tr"], example=x["examples"][0]["en"],
                                                      text=text.replace('"', "'"))}],
            JUDGE_SCHEMA, options={"temperature": 0, "num_predict": 40})
    n = len(correction["errors"])
    if n:
        verdict, msg = "wrong", f"Cümlende {n} hata var — kırmızı kısımlar yanlış, yeşiller doğrusu."
    elif not judged.get("meaning_fits", True):
        verdict, msg = "warn", "Cümle hatasız ama kalıp burada doğal durmuyor. Örneklere bir daha bak."
    else:
        verdict, msg = "ok", "Güzel — kalıbı doğru kullandın ✓"
    return {"verdict": verdict, "message_tr": msg, "correction": correction}
