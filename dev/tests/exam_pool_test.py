"""Level exams without the LLM: every attempt draws a balanced set from the pools (all lessons, mixed question
types, the right number of listening/speaking items), retakes differ, correct answers — word-order answers built
from the tiles as the page does — get full marks, wrong ones none, and attempts stored in the old format (a plain
list of grammar ids) are still graded on the items they asked. Usage: python exam_pool_test.py"""

import json
import os
import re
import sys
import tempfile
from collections import Counter
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ✓ on a Windows (cp1254) console

os.environ["EP_DATA_DIR"] = tempfile.mkdtemp()  # never the real database
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "app"))

from backend import db, exams  # noqa: E402
from backend.db import get_conn  # noqa: E402

db.init_db()
problems = []
ATTEMPTS = 60


def tiles_in_order(q: dict) -> str:
    """The tiles arranged as the first answer (what a learner who knows it clicks)."""
    target = re.findall(r"[a-z0-9']+", q["answer"][0].lower())
    left, out = list(q["words"]), []
    while target:
        tile = next(t for t in left if re.findall(r"[a-z0-9']+", t.lower()) == target[:len(re.findall(r"[a-z0-9']+", t.lower()))])
        left.remove(tile)
        out.append(tile)
        target = target[len(re.findall(r"[a-z0-9']+", tile.lower())):]
    return " ".join(out)


def right_answer(q: dict):
    return q["answer"] if q["type"] == "choice" else tiles_in_order(q) if q["type"] == "order" else q["answer"][0]


for level, exam in exams.EXAMS.items():
    bank = {q["id"]: q for q in exam["grammar"]}
    lessons_n = len({q["lesson"] for q in exam["grammar"]})
    per_lesson_max = -(-exam["grammar_count"] // lessons_n)
    seen_sets, seen_q, type_totals = set(), set(), Counter()
    for _ in range(ATTEMPTS):
        ex = exams.start(level)
        ids = [q["id"] for q in ex["grammar"]]
        if len(ids) != exam["grammar_count"] or len(set(ids)) != len(ids):
            problems.append(f"{level}: wrong/duplicate grammar selection")
        by_lesson = Counter(bank[i]["lesson"] for i in ids)
        if len(by_lesson) != lessons_n or max(by_lesson.values()) > per_lesson_max:
            problems.append(f"{level}: lessons unbalanced {dict(by_lesson)}")
        types = Counter(q["type"] for q in ex["grammar"])
        type_totals.update(types)
        if any(t not in types for t in ("transform", "order") if any(q["type"] == t for q in exam["grammar"])):
            problems.append(f"{level}: an attempt without transform/order questions {dict(types)}")
        if any(k in q for q in ex["grammar"] for k in ("answer", "explain_tr")):
            problems.append(f"{level}: answers sent to the page")
        n = exams._counts(exam)
        if (len(ex["listening"]["dictation"]), len(ex["listening"]["comprehension"]), len(ex["speaking"])) != \
                (n["dictation"], n["comprehension"], n["speaking"]):
            problems.append(f"{level}: wrong number of listening/speaking items")
        seen_sets.add(frozenset(ids))
        seen_q.update(ids)

        # Correct answers → full marks; the stored selection is what gets graded.
        with get_conn() as conn:
            sel = json.loads(conn.execute("SELECT questions_json FROM exam_attempts WHERE id = ?",
                                          (ex["attempt_id"],)).fetchone()[0])
        g_score, g_items = exams._grade_grammar(exam, sel["grammar"], {i: right_answer(bank[i]) for i in ids})
        if g_score != 1:
            problems.append(f"{level}: correct grammar answers not accepted: "
                            f"{[(i['id'], i['your']) for i in g_items if not i['ok']]}")
        answers = {d["id"]: d["text"] for d in ex["listening"]["dictation"]}
        full = {c["id"]: c for c in exam["listening"]["comprehension"]}
        for c in ex["listening"]["comprehension"]:
            answers.update({q["id"]: q["answer"] for q in full[c["id"]]["questions"]})
        l_score, _ = exams._grade_listening(exam, sel, answers)
        if l_score != 1:
            problems.append(f"{level}: correct listening answers not full marks ({l_score})")
        if exams._grade_grammar(exam, sel["grammar"], {})[0] != 0:
            problems.append(f"{level}: empty answers scored")
        w = exams._writing_task(exam, sel)
        if w["prompt_en"] != ex["writing"]["prompt_en"]:
            problems.append(f"{level}: graded writing task differs from the one shown")

    # Order questions: a wrong arrangement is wrong.
    for q in exam["grammar"]:
        if q["type"] == "order":
            backwards = " ".join(reversed(tiles_in_order(q).split(" ")))
            if exams.answer_ok(q, backwards) and backwards.lower() != tiles_in_order(q).lower():
                problems.append(f"{level} {q['id']}: a reversed sentence is accepted ({backwards})")

    # Old-format attempt: a list of grammar ids → the first items of every part (the original exam).
    legacy = exams._selection(exam, list(bank)[:3])
    if legacy["dictation"] != [d["id"] for d in exam["listening"]["dictation"][:exam["listening"]["dictation_count"]]] \
            or legacy["writing"] != exam["writing"][0]["id"]:
        problems.append(f"{level}: legacy selection wrong")

    print(f"{level}: {len(seen_sets)}/{ATTEMPTS} farklı soru seti, havuzun %{100 * len(seen_q) // len(bank)}'i soruldu, "
          f"türler {dict(type_totals)}")

print("Sorun yok ✓" if not problems else "\n".join(dict.fromkeys(problems)))
sys.exit(1 if problems else 0)
