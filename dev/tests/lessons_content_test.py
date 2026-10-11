"""Check the lesson content files (app/content/lessons/*.json): structure, category ids,
answer indexes, and that every 'fix' exercise's wrong sentence is not itself accepted."""

import os
import re
import sys
import tempfile
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ✓ on a Windows (cp1254) console

os.environ.setdefault("EP_DATA_DIR", tempfile.mkdtemp())  # importing the backend creates folders

from backend import lessons  # noqa: E402


def norm(s: str) -> str:
    """Same rules as the UI (lessons.js normalizeAnswer), roughly."""
    s = s.lower().replace("’", "'").strip()
    s = re.sub(r"\s+", " ", s)
    return re.sub(r"[.!?,]+$", "", s)


problems = lessons.validate(lessons.LESSONS)
for l in lessons.LESSONS:
    for i, ex in enumerate(l["exercises"], 1):
        if ex["type"] == "fix" and norm(ex["q"]) in {norm(a) for a in ex["answer"]}:
            problems.append(f"{l['id']} #{i}: the wrong sentence is an accepted answer")
        if i == 1 and len(l.get("sources", [])) < 2:
            problems.append(f"{l['id']}: needs at least 2 sources (verified links)")
        if not ex.get("explain_tr"):
            problems.append(f"{l['id']} #{i}: missing explain_tr")
    for s in l["sections"]:
        if s.get("table") and any(len(r) != len(s["table"]["head"]) for r in s["table"]["rows"]):
            problems.append(f"{l['id']}: table row length differs from head")

# Level exams (app/content/exams/*.json)
from backend import exams  # noqa: E402

for level, ex in exams.EXAMS.items():
    where = f"exam {level}"
    ids = [q["id"] for q in ex["grammar"]]
    if len(ids) != len(set(ids)):
        problems.append(f"{where}: duplicate grammar ids")
    if len(ids) < ex["grammar_count"]:
        problems.append(f"{where}: fewer questions than grammar_count")
    for q in ex["grammar"]:
        w = f"{where} {q['id']}"
        if q["lesson"] not in lessons.BY_ID:
            problems.append(f"{w}: unknown lesson {q['lesson']}")
        if q["type"] not in ("choice", "fill", "fix", "transform", "order"):
            problems.append(f"{w}: unknown type {q['type']}")
        elif q["type"] == "choice":
            if not 0 <= q["answer"] < len(q["options"]):
                problems.append(f"{w}: answer index out of range")
        elif not (isinstance(q.get("answer"), list) and q["answer"] and all(q["answer"])):
            problems.append(f"{w}: answer must be a non-empty list")
            continue
        if not q.get("explain_tr"):
            problems.append(f"{w}: missing explain_tr")
        if q["type"] == "fill" and "___" not in q["q"]:
            problems.append(f"{w}: fill question without ___")
        if q["type"] in ("fix", "transform") and exams.answer_ok({**q, "type": "fix"}, q["q"]):
            problems.append(f"{w}: the question sentence itself is accepted")
        if q["type"] == "transform" and not q.get("instruction_tr"):
            problems.append(f"{w}: transform needs instruction_tr")
        if q["type"] == "order":
            tiles = q.get("words") or []
            if len(tiles) < 3:
                problems.append(f"{w}: order needs at least 3 tiles")
            elif lessons._tokens(" ".join(tiles)) != lessons._tokens(q["answer"][0]):
                problems.append(f"{w}: the tiles do not make the first answer")
    level_lessons = {l["id"] for l in lessons.LESSONS if l["level"] == level}
    missing = level_lessons - {q["lesson"] for q in ex["grammar"]}
    if missing:
        problems.append(f"{where}: no questions for {sorted(missing)}")
    if ex["grammar_count"] < len(level_lessons):
        problems.append(f"{where}: grammar_count smaller than the number of lessons")
    # Pools: enough items for one attempt, unique ids across the parts.
    li = ex["listening"]
    for name, pool, count in (("dictation", li["dictation"], li["dictation_count"]),
                              ("comprehension", li["comprehension"], li["comprehension_count"]),
                              ("speaking", ex["speaking"], ex["speaking_count"])):
        if not 1 <= count <= len(pool):
            problems.append(f"{where}: {name}_count {count} but {len(pool)} items")
    other_ids = ([d["id"] for d in li["dictation"]] + [c["id"] for c in li["comprehension"]]
                 + [q["id"] for c in li["comprehension"] for q in c["questions"]]
                 + [s["id"] for s in ex["speaking"]] + [t["id"] for t in ex["writing"]])
    if len(other_ids) != len(set(other_ids)):
        problems.append(f"{where}: duplicate listening/speaking/writing ids")
    for d in li["dictation"]:
        if not d.get("text") or re.search(r"\d", d["text"]):
            problems.append(f"{where} {d['id']}: dictation text missing or contains digits")
    for c in li["comprehension"]:
        for q in c["questions"]:
            if not 0 <= q["answer"] < len(q["options"]):
                problems.append(f"{where} {q['id']}: answer index out of range")
    for s in ex["speaking"]:
        if not all(s.get(k) for k in ("question_en", "instruction_tr", "focus")):
            problems.append(f"{where} {s['id']}: speaking item incomplete")
    for t in ex["writing"]:
        if not all(t.get(k) for k in ("instruction_tr", "prompt_en", "focus", "min_words")):
            problems.append(f"{where} {t['id']}: writing task incomplete")
    types = {t: sum(q["type"] == t for q in ex["grammar"]) for t in ("choice", "fill", "fix", "transform", "order")}
    print(f"Sınav {level}: {len(ids)} dilbilgisi sorusu {types}, {len(li['dictation'])} dikte, "
          f"{len(li['comprehension'])} dinleme metni, {len(ex['speaking'])} konuşma, {len(ex['writing'])} yazma")

# Term markup ([en:…] [tr:…] [key:…], rendered by text.js): well-formed and only in Turkish text fields —
# never in answers, options, examples, titles or anything compared, spoken or sent to the LLM as is.
MARK_FIELDS = {"intro_tr", "text_tr", "note_tr", "explain_tr", "instruction_tr", "q_tr"}


def markup_ok(path: tuple, parent: dict) -> bool:
    key = path[-1]
    if isinstance(key, int):
        return "comprehension" in path and path[-2] == "options"
    if key in MARK_FIELDS:
        return True
    if key == "title_tr":
        return "sections" in path
    return key == "q" and parent.get("type") in ("choice", "order", "match")


def check_markup(where: str, node, path=(), parent=None):
    if isinstance(node, dict):
        for k, v in node.items():
            check_markup(where, v, path + (k,), node)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            check_markup(where, v, path + (i,), parent)
    elif isinstance(node, str) and "[" in node:
        if lessons.TERM_MARK.search(node) and not markup_ok(path, parent or {}):
            problems.append(f"{where} {'/'.join(map(str, path))}: term markup not allowed here: {node[:80]}")
        if re.search(r"\[[a-z]+:", lessons.TERM_MARK.sub("", node)):
            problems.append(f"{where} {'/'.join(map(str, path))}: malformed term markup: {node[:80]}")


for l in lessons.LESSONS:
    check_markup(l["id"], {k: v for k, v in l.items() if k not in ("level", "order")})
for level, ex in exams.EXAMS.items():
    check_markup(f"exam {level}", ex)

by_level = {}
for l in lessons.LESSONS:
    by_level.setdefault(l["level"], []).append(l["id"])
for level, ids in by_level.items():
    print(f"{level}: {len(ids)} ders — {', '.join(ids)}")
print("Sorun yok ✓" if not problems else "\n".join(problems))
sys.exit(1 if problems else 0)
