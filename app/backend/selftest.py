"""Self-tests (🎯 Kendini Test Et). For now one category: YDS-style questions (app/content/yds/*.json,
format and rules in app/content/yds/README.md) solved against the clock: a set of one question type, or a
40-question mini exam in YDS proportions. Attempts live in selftest_attempts; a running attempt keeps its
answers on the server, so leaving the page or restarting the app loses nothing, and the deadline is kept
there too. The learner never receives answers or explanations before finishing.
"""

import json
import logging
import random
import re
from datetime import datetime, timedelta, timezone

from .config import APP_DIR
from .db import get_conn, log_practice, now_iso, rows_to_dicts

log = logging.getLogger("selftest")
CONTENT_DIR = APP_DIR / "content" / "yds"

# Question types in YDS order; label, questions per passage (0: single questions), pool size, mini-exam share.
TYPES = {
    "vocab": {"tr": "Kelime bilgisi", "per_passage": 0, "pool": 24, "mini": 3},
    "grammar": {"tr": "Dilbilgisi", "per_passage": 0, "pool": 40, "mini": 5},
    "cloze": {"tr": "Cloze test", "per_passage": 5, "pool": 40, "mini": 5},
    "sentence": {"tr": "Cümle tamamlama", "per_passage": 0, "pool": 40, "mini": 5},
    "translation": {"tr": "Çeviri", "per_passage": 0, "pool": 24, "mini": 3},
    "reading": {"tr": "Paragraf (okuma)", "per_passage": 4, "pool": 80, "mini": 8},
    "dialogue": {"tr": "Diyalog tamamlama", "per_passage": 0, "pool": 20, "mini": 3},
    "paraphrase": {"tr": "Anlamca en yakın cümle", "per_passage": 0, "pool": 16, "mini": 2},
    "paragraph": {"tr": "Paragraf tamamlama", "per_passage": 0, "pool": 16, "mini": 2},
    "irrelevant": {"tr": "Anlam bütünlüğünü bozan cümle", "per_passage": 0, "pool": 20, "mini": 4},
}
ID_PREFIX = {"vocab": "voc", "grammar": "gra", "cloze": "clz", "sentence": "sen", "translation": "tra", "reading": "rea",
             "dialogue": "dia", "paraphrase": "par", "paragraph": "pcm", "irrelevant": "irr"}
SECONDS_PER_QUESTION = 135  # YDS: 180 minutes for 80 questions
TIMINGS = {"standard": 1.0, "relaxed": 1.5, "none": None}
MINI_TOTAL = sum(t["mini"] for t in TYPES.values())  # 40
GRACE_SECONDS = 60  # answers arriving this long after the deadline are still graded (network, auto-submit)
TERM_MARK = re.compile(r"\[(en|tr|key):([^\[\]]+)\]")
BLANK = "----"


# ------------------------------------------------------------------ content

def _check_question(q: dict, where: str, problems: list[str], with_options: bool = True) -> None:
    if with_options:
        opts = q.get("options")
        if not isinstance(opts, list) or len(opts) != 5 or any(not isinstance(o, str) or not o.strip() for o in opts):
            problems.append(f"{where}: exactly 5 non-empty options")
        elif len({o.strip().lower() for o in opts}) != 5:
            problems.append(f"{where}: options must differ")
        elif any(TERM_MARK.search(o) for o in opts):
            problems.append(f"{where}: no markup in options")
    if not isinstance(q.get("answer"), int) or isinstance(q.get("answer"), bool) or not 0 <= q["answer"] <= 4:
        problems.append(f"{where}: answer must be 0–4")
    ex = q.get("explain_tr")
    if not isinstance(ex, str) or not ex.strip() or len(ex) > 600:
        problems.append(f"{where}: explain_tr must be 1–600 characters")
    elif ex.count("[") != ex.count("]") or re.search(r"\[(?!en:|tr:|key:)", ex):
        problems.append(f"{where}: explain_tr markup must be [en:…]/[tr:…]/[key:…] and balanced")
    tags = q.get("tags", [])
    if not isinstance(tags, list) or any(not isinstance(t, str) for t in tags):
        problems.append(f"{where}: tags must be a list of strings")


def _text_ok(s, where: str, problems: list[str], blanks: int | None = None) -> None:
    if not isinstance(s, str) or not s.strip():
        problems.append(f"{where}: empty text")
        return
    if TERM_MARK.search(s):
        problems.append(f"{where}: no markup in question text")
    if re.search(r"(?<!-)-{2,3}(?!-)|-{5,}", s):
        problems.append(f"{where}: the blank is exactly ---- (four hyphens)")
    if blanks is not None and s.count(BLANK) != blanks:
        problems.append(f"{where}: expected {blanks} blank(s) (----), found {s.count(BLANK)}")


def validate(files: dict[str, dict]) -> list[str]:
    """Content mistakes in {type: file dict} (content test; logged at start-up)."""
    problems, seen_ids = [], set()
    for key, data in files.items():
        qtype, _, part = key.partition("@")  # "reading@reading-01-10": a part file (no pool-size check)
        where = f"{part or qtype}.json"
        spec = TYPES.get(qtype)
        if spec is None:
            problems.append(f"{where}: unknown type")
            continue
        if data.get("type") != qtype:
            problems.append(f"{where}: type must be {qtype}")
        sources = data.get("sources") or []
        if len(sources) < 2 or not all(isinstance(s, dict) and str(s.get("url", "")).startswith("http") and s.get("title")
                                        for s in sources):
            problems.append(f"{where}: needs at least 2 sources with title + url")
        items = data.get("items")
        if not isinstance(items, list):
            problems.append(f"{where}: items must be a list")
            continue
        prefix = ID_PREFIX[qtype]
        n_questions = 0
        answers = []
        for i, it in enumerate(items, 1):
            w = f"{where} #{i} ({it.get('id', '?') if isinstance(it, dict) else '?'})"
            if not isinstance(it, dict):
                problems.append(f"{w}: not an object")
                continue
            iid = str(it.get("id", ""))
            if iid in seen_ids:
                problems.append(f"{w}: duplicate id")
            seen_ids.add(iid)
            if spec["per_passage"]:
                if not re.fullmatch(rf"{prefix}-\d{{2}}", iid):
                    problems.append(f"{w}: passage id like {prefix}-01")
                _text_ok(it.get("passage"), f"{w} passage", problems, blanks=5 if qtype == "cloze" else 0)
                words = len(re.findall(r"[A-Za-z0-9'’-]+", str(it.get("passage", ""))))
                lo, hi = (90, 140) if qtype == "cloze" else (140, 200)
                if not lo - 10 <= words <= hi + 15:
                    problems.append(f"{w}: passage has {words} words, expected {lo}–{hi}")
                if qtype == "cloze":
                    for n in range(1, 6):
                        if f"({n})----" not in str(it.get("passage", "")):
                            problems.append(f"{w}: passage must contain ({n})----")
                qs = it.get("questions")
                if not isinstance(qs, list) or len(qs) != spec["per_passage"]:
                    problems.append(f"{w}: exactly {spec['per_passage']} questions")
                    continue
                for j, q in enumerate(qs, 1):
                    qw = f"{w} q{j}"
                    if not isinstance(q, dict):
                        problems.append(f"{qw}: not an object")
                        continue
                    if q.get("id") != f"{iid}-{j}":
                        problems.append(f"{qw}: id must be {iid}-{j}")
                    if qtype == "cloze" and q.get("n") != j:
                        problems.append(f"{qw}: n must be {j}")
                    if qtype == "reading":
                        _text_ok(q.get("q"), f"{qw} q", problems, blanks=0)
                    _check_question(q, qw, problems)
                    answers.append(q.get("answer"))
                    n_questions += 1
                continue
            # single questions
            if qtype == "translation":
                d = it.get("direction")
                if d not in ("en-tr", "tr-en") or not re.fullmatch(rf"{prefix}-{d[:2]}-\d{{3}}", iid):
                    problems.append(f"{w}: direction en-tr/tr-en and id like {prefix}-en-001")
            elif not re.fullmatch(rf"{prefix}-\d{{3}}", iid):
                problems.append(f"{w}: id like {prefix}-001")
            if qtype in ("vocab", "sentence", "translation", "paraphrase"):
                blanks = {"vocab": 1, "sentence": 1, "translation": 0, "paraphrase": 0}[qtype]
                _text_ok(it.get("q"), f"{w} q", problems, blanks=blanks)
            elif qtype == "grammar":
                _text_ok(it.get("q"), f"{w} q", problems)
                nb = str(it.get("q", "")).count(BLANK)
                if nb not in (1, 2):
                    problems.append(f"{w}: 1 or 2 blanks")
                elif nb == 2 and any(o.count("/") != 1 for o in it.get("options", []) if isinstance(o, str)):
                    problems.append(f"{w}: two blanks → options like 'has been / was'")
            elif qtype == "paragraph":
                _text_ok(it.get("passage"), f"{w} passage", problems, blanks=1)
                words = len(re.findall(r"[A-Za-z0-9'’-]+", str(it.get("passage", ""))))
                if not 60 <= words <= 125:
                    problems.append(f"{w}: passage has {words} words, expected 70–110")
            elif qtype == "dialogue":
                lines = it.get("lines")
                if not isinstance(lines, list) or not 4 <= len(lines) <= 6 or any(
                        not isinstance(l, dict) or not str(l.get("speaker", "")).strip() for l in lines):
                    problems.append(f"{w}: 4–6 lines with speaker + text")
                else:
                    blanks = [l for l in lines if str(l.get("text", "")).strip() == BLANK]
                    if len(blanks) != 1:
                        problems.append(f"{w}: exactly one line is ----")
                    for l in lines:
                        if str(l.get("text", "")).strip() != BLANK:
                            _text_ok(l.get("text"), f"{w} line", problems, blanks=0)
            elif qtype == "irrelevant":
                ss = it.get("sentences")
                if not isinstance(ss, list) or len(ss) != 5 or any(not isinstance(s, str) or not s.strip() for s in ss):
                    problems.append(f"{w}: exactly 5 sentences")
                else:
                    for k, s in enumerate(ss):
                        if not s.startswith(f"({['I', 'II', 'III', 'IV', 'V'][k]}) "):
                            problems.append(f"{w}: sentence {k + 1} must start with ({['I', 'II', 'III', 'IV', 'V'][k]}) ")
                if "options" in it:
                    problems.append(f"{w}: no options for irrelevant (I–V implied)")
            _check_question(it, w, problems, with_options=qtype != "irrelevant")
            answers.append(it.get("answer"))
            n_questions += 1
        if not part and n_questions != spec["pool"]:
            problems.append(f"{where}: {n_questions} questions, expected {spec['pool']}")
        valid = [a for a in answers if isinstance(a, int)]
        if valid and max(valid.count(k) for k in range(5)) > 0.45 * len(valid):
            problems.append(f"{where}: correct answers are not spread over A–E (one position > 45%)")
    return problems


def _load() -> dict[str, dict]:
    out = {}
    for qtype in TYPES:
        path = CONTENT_DIR / f"{qtype}.json"
        if path.exists():
            out[qtype] = json.loads(path.read_text(encoding="utf-8"))
    return out


FILES = _load()
for _problem in validate(FILES):
    log.warning("yds content: %s", _problem)


def _index() -> tuple[dict[str, dict], dict[str, dict]]:
    """questions by id (with their type and passage id), passages by id."""
    qs, ps = {}, {}
    for qtype, data in FILES.items():
        for it in data.get("items", []):
            if TYPES[qtype]["per_passage"]:
                ps[it["id"]] = {"id": it["id"], "type": qtype, "passage": it.get("passage", ""), "title": it.get("title")}
                for q in it.get("questions", []):
                    qs[q["id"]] = {**q, "type": qtype, "passage_id": it["id"]}
            else:
                qs[it["id"]] = {**it, "type": qtype, "passage_id": None}
    return qs, ps


QUESTIONS, PASSAGES = _index()
POOL = {t: [q for q in QUESTIONS.values() if q["type"] == t] for t in TYPES}


def public_question(q: dict) -> dict:
    """A question as the learner sees it while solving: no answer, no explanation."""
    return {k: v for k, v in q.items() if k not in ("answer", "explain_tr", "tags")}


# ----------------------------------------------------------------- history

def _history() -> dict[str, list[bool]]:
    """Per question id: the results so far (True = right), from finished attempts."""
    out: dict[str, list[bool]] = {}
    with get_conn() as conn:
        rows = conn.execute("SELECT result_json FROM selftest_attempts WHERE finished_at IS NOT NULL").fetchall()
    for r in rows:
        for item in json.loads(r["result_json"] or "{}").get("items", []):
            out.setdefault(item["id"], []).append(bool(item["ok"]))
    return out


def _rank(hist: dict[str, list[bool]]):
    """Unseen questions first, then ones last answered wrong, then the rest; random within a group."""
    def key(q: dict):
        h = hist.get(q["id"])
        return (0 if not h else 1 if not h[-1] else 2, random.random())
    return key


def _pick(qtype: str, count: int, hist: dict[str, list[bool]]) -> list[dict]:
    spec = TYPES[qtype]
    if spec["per_passage"]:
        n = max(1, round(count / spec["per_passage"]))
        pids = [p["id"] for p in PASSAGES.values() if p["type"] == qtype]
        def pkey(pid: str):
            qs = [q for q in POOL[qtype] if q["passage_id"] == pid]
            return (min(_rank(hist)(q)[0] for q in qs), random.random())
        chosen = sorted(pids, key=pkey)[:n]
        return [q for pid in chosen for q in POOL[qtype] if q["passage_id"] == pid]
    pool = sorted(POOL[qtype], key=_rank(hist))
    if qtype == "translation":  # both directions, as in the exam
        en = [q for q in pool if q["direction"] == "en-tr"]
        tr = [q for q in pool if q["direction"] == "tr-en"]
        out = []
        for i in range(count):
            src = en if (i % 2 == 0 and en) or not tr else tr
            if src:
                out.append(src.pop(0))
        return out
    return pool[:count]


def counts_for(qtype: str) -> list[int]:
    """The set sizes offered for a type."""
    spec = TYPES[qtype]
    n = len(POOL[qtype])
    if spec["per_passage"]:
        return [k * spec["per_passage"] for k in range(1, n // spec["per_passage"] + 1) if k <= 5]
    return [c for c in (5, 10, 20) if c <= n]


def overview() -> dict:
    hist = _history()
    types = []
    for t, spec in TYPES.items():
        qs = POOL[t]
        seen = [q for q in qs if q["id"] in hist]
        right = sum(1 for q in seen if hist[q["id"]][-1])
        types.append({"type": t, "tr": spec["tr"], "pool": len(qs), "seen": len(seen), "right": right,
                      "counts": counts_for(t), "mini": spec["mini"]})
    with get_conn() as conn:
        running = conn.execute("SELECT * FROM selftest_attempts WHERE finished_at IS NULL ORDER BY id DESC LIMIT 1").fetchone()
        done = conn.execute("SELECT id, kind, qtype, started_at, finished_at, time_limit_s, time_used_s, correct, total "
                            "FROM selftest_attempts WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 30").fetchall()
    return {"types": types, "mini_total": MINI_TOTAL, "seconds_per_question": SECONDS_PER_QUESTION,
            "running": _attempt_view(dict(running)) if running else None,
            "history": [{**dict(r), "qtype_tr": TYPES.get(r["qtype"], {}).get("tr")} for r in done]}


# ---------------------------------------------------------------- attempts

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def start(kind: str, qtype: str | None, count: int | None, timing: str) -> dict:
    if timing not in TIMINGS:
        raise ValueError("Süre seçeneği geçersiz.")
    hist = _history()
    if kind == "mini":
        qs = [q for t, spec in TYPES.items() for q in _pick(t, spec["mini"], hist)]
        qtype = None
    elif kind == "type":
        if qtype not in TYPES:
            raise ValueError("Soru türü geçersiz.")
        count = count or counts_for(qtype)[0]
        if count not in counts_for(qtype):
            raise ValueError("Soru sayısı geçersiz.")
        qs = _pick(qtype, count, hist)
    else:
        raise ValueError("Test türü geçersiz.")
    if not qs:
        raise ValueError("Bu türde soru yok.")
    factor = TIMINGS[timing]
    limit = round(len(qs) * SECONDS_PER_QUESTION * factor) if factor else None
    started = _now()
    deadline = (started + timedelta(seconds=limit)).isoformat(timespec="seconds") if limit else None
    with get_conn() as conn:
        conn.execute("UPDATE selftest_attempts SET finished_at = ?, result_json = ? WHERE finished_at IS NULL",
                     (started.isoformat(timespec="seconds"), None))  # a forgotten running attempt is closed unscored
        conn.execute("DELETE FROM selftest_attempts WHERE finished_at IS NOT NULL AND result_json IS NULL")
        cur = conn.execute(
            "INSERT INTO selftest_attempts (kind, qtype, timing, started_at, deadline, time_limit_s, questions_json, answers_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, qtype, timing, started.isoformat(timespec="seconds"), deadline, limit,
             json.dumps([q["id"] for q in qs]), "{}"))
        row = conn.execute("SELECT * FROM selftest_attempts WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _attempt_view(dict(row))


def _attempt_view(row: dict) -> dict:
    """A running attempt for the page: its questions (without answers), passages, answers so far, time left."""
    ids = json.loads(row["questions_json"])
    qs = [public_question(QUESTIONS[i]) for i in ids if i in QUESTIONS]
    pids = {q["passage_id"] for q in qs if q.get("passage_id")}
    remaining = None
    if row["deadline"]:
        remaining = max(0, int((_parse(row["deadline"]) - _now()).total_seconds()))
    return {"id": row["id"], "kind": row["kind"], "qtype": row["qtype"], "qtype_tr": TYPES.get(row["qtype"], {}).get("tr"),
            "timing": row["timing"], "started_at": row["started_at"], "time_limit_s": row["time_limit_s"],
            "remaining_s": remaining, "questions": qs, "passages": {p: PASSAGES[p] for p in pids if p in PASSAGES},
            "answers": json.loads(row["answers_json"] or "{}"), "types": {t: spec["tr"] for t, spec in TYPES.items()}}


def get_attempt(attempt_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM selftest_attempts WHERE id = ? AND finished_at IS NULL", (attempt_id,)).fetchone()
    return _attempt_view(dict(row)) if row else None


def save_answers(attempt_id: int, answers: dict) -> bool:
    clean = {k: v for k, v in answers.items() if k in QUESTIONS and isinstance(v, int) and 0 <= v <= 4}
    with get_conn() as conn:
        return conn.execute("UPDATE selftest_attempts SET answers_json = ? WHERE id = ? AND finished_at IS NULL",
                            (json.dumps(clean), attempt_id)).rowcount > 0


def finish(attempt_id: int, answers: dict | None) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM selftest_attempts WHERE id = ? AND finished_at IS NULL", (attempt_id,)).fetchone()
    if row is None:
        return None
    row = dict(row)
    given = json.loads(row["answers_json"] or "{}")
    if answers:
        given.update({k: v for k, v in answers.items() if k in QUESTIONS and isinstance(v, int) and 0 <= v <= 4})
    now = _now()
    used = int((now - _parse(row["started_at"])).total_seconds())
    if row["time_limit_s"]:
        used = min(used, row["time_limit_s"])
    ids = json.loads(row["questions_json"])
    items, per_type = [], {}
    for i in ids:
        q = QUESTIONS.get(i)
        if not q:
            continue
        g = given.get(i)
        ok = g == q["answer"]
        items.append({"id": i, "type": q["type"], "given": g, "answer": q["answer"], "ok": ok, "explain_tr": q["explain_tr"]})
        pt = per_type.setdefault(q["type"], {"type": q["type"], "tr": TYPES[q["type"]]["tr"], "total": 0, "correct": 0, "blank": 0})
        pt["total"] += 1
        pt["correct"] += ok
        pt["blank"] += g is None
    correct, total = sum(it["ok"] for it in items), len(items)
    result = {"id": attempt_id, "kind": row["kind"], "qtype": row["qtype"], "qtype_tr": TYPES.get(row["qtype"], {}).get("tr"),
              "timing": row["timing"], "started_at": row["started_at"], "finished_at": now.isoformat(timespec="seconds"),
              "time_limit_s": row["time_limit_s"], "time_used_s": used, "correct": correct, "total": total,
              "blank": sum(1 for it in items if it["given"] is None),
              "score": round(100 * correct / total, 1) if total else 0.0,  # YDS: 1.25 points × 80 questions
              "per_type": [per_type[t] for t in TYPES if t in per_type], "items": items}
    with get_conn() as conn:
        conn.execute("UPDATE selftest_attempts SET finished_at = ?, answers_json = ?, time_used_s = ?, correct = ?, total = ?,"
                     " result_json = ? WHERE id = ?",
                     (result["finished_at"], json.dumps(given), used, correct, total, json.dumps(result, ensure_ascii=False),
                      attempt_id))
    log_practice("selftest", max(1, used / 60))
    return get_result(attempt_id)  # with the questions and passages, for the review


def get_result(attempt_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT result_json, questions_json FROM selftest_attempts WHERE id = ? AND result_json IS NOT NULL",
                           (attempt_id,)).fetchone()
    if row is None:
        return None
    result = json.loads(row["result_json"])
    ids = json.loads(row["questions_json"])
    qs = [QUESTIONS[i] for i in ids if i in QUESTIONS]
    pids = {q["passage_id"] for q in qs if q.get("passage_id")}
    return {**result, "questions": qs, "passages": {p: PASSAGES[p] for p in pids if p in PASSAGES},
            "types": {t: spec["tr"] for t, spec in TYPES.items()}}


def delete_attempt(attempt_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM selftest_attempts WHERE id = ?", (attempt_id,))
