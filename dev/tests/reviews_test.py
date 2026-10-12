"""Spaced review of finished lessons (backend/reviews.py), offline on a temporary database: finished lessons get
a schedule (late ones spread out), the interval ladder, the quiz picks earlier mistakes first, frequent mistakes
in a topic bring its lessons forward, a lesson reset or a "Sıfırla" removes the schedule.
Never touches the real data. Usage: python reviews_test.py"""

import json
import os
import random
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ✓ on a Windows (cp1254) console

os.environ["EP_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))
from backend import db, lessons, reviews  # noqa: E402
from backend.db import get_conn  # noqa: E402

problems = []


def check(ok, what):
    print(("✓ " if ok else "✗ ") + what)
    if not ok:
        problems.append(what)


def iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def finish(lesson_id: str, days_ago: int) -> None:
    with get_conn() as conn:
        conn.execute("INSERT INTO lesson_progress (lesson_id, first_opened_at, last_opened_at, best_score, last_score, "
                     "attempts, completed_at) VALUES (?, ?, ?, 0.9, 0.9, 1, ?)",
                     (lesson_id, iso_days_ago(days_ago), iso_days_ago(days_ago), iso_days_ago(days_ago)))


db.init_db()
today = date.today()
A1 = [l["id"] for l in lessons.LESSONS if l["level"] == "A1"]

# 1. A lesson finished today: its first review is tomorrow (not due today).
finish(A1[0], 0)
r = reviews.overview()
check(r["count"] == 0 and r["soon"] and r["soon"][0]["due_date"] == (today + timedelta(days=1)).isoformat(),
      "bugün bitirilen dersin ilk tekrarı yarın")

# 2. Five lessons finished long ago (e.g. before this feature): spread out, 2 a day from today.
for i, lid in enumerate(A1[1:6]):
    finish(lid, 30 - i)
r = reviews.overview()
dues = sorted(x["due_date"] for x in r["due"] + r["soon"] if x["lesson_id"] in A1[1:6])
expected = sorted([today.isoformat()] * 2 + [(today + timedelta(days=1)).isoformat()] * 2
                  + [(today + timedelta(days=2)).isoformat()])
check(dues == expected and r["count"] == 2, f"eski bitirilen dersler günde 2 tane yayılır ({r['count']} bugün)")
check(reviews.due_count() == 2, "menü sayısı = bugünkü tekrar sayısı")

# 3. The quiz: 6 questions; answers wrong on the lesson page come first (at most half).
lesson = lessons.BY_ID[A1[1]]
page = {"exercises": {"2": {"type": lesson["exercises"][2]["type"], "ok": False, "given": "x"},
                      "5": {"type": lesson["exercises"][5]["type"], "ok": False, "given": "y"},
                      "1": {"type": lesson["exercises"][1]["type"], "ok": True, "given": "z"}}}
with get_conn() as conn:
    conn.execute("INSERT INTO ui_state (key, value_json, updated_at) VALUES (?, ?, ?)",
                 (f"lesson:{A1[1]}", json.dumps(page), iso_days_ago(1)))
s = reviews.start(A1[1])
check(len(s["items"]) == reviews.QUIZ_SIZE and {2, 5} <= set(s["items"]) and len(s["exercises"]) == reviews.QUIZ_SIZE,
      "mini test 6 soru, önce derste yanlış yapılanlar")
check(s["card"] is None or s["card"]["rules_tr"], "özet kartı (varsa) geliyor")

# 4. Ladder: good → next step (3 days); middling → same interval; poor → back to 1 day.
res = reviews.record(A1[1], s["items"], [])
check(res["advice"] == "good" and res["step"] == 1 and res["days"] == 3, "iyi sonuç → aralık uzar (3 gün)")
res = reviews.record(A1[1], s["items"], s["items"][:2])  # 4/6
check(res["advice"] == "again" and res["step"] == 1 and res["days"] == 3, "orta sonuç → aynı aralık tekrar")
res = reviews.record(A1[1], s["items"], s["items"][:4])  # 2/6
check(res["advice"] == "relearn" and res["step"] == 0 and res["days"] == 1, "zayıf sonuç → başa döner (1 gün), dersi öner")
row = reviews._rows()[A1[1]]
check(row["review_count"] == 3 and row["lapses"] == 1, "tekrar ve unutma sayıları tutulur")

# 5. The next quiz asks the review's wrong answers again.
wrong_before = json.loads(row["wrong_items"])
s2 = reviews.start(A1[1])
check(set(wrong_before[:3]) <= set(s2["items"]), "testte yanlış yapılanlar bir sonraki testte yine sorulur")
rng = random.Random(1)
picks = {tuple(reviews.pick_quiz(lesson, {"wrong_items": "[]", "last_items": json.dumps(s["items"])}, rng))
         for _ in range(3)}
check(all(set(p) & set(s["items"]) <= {2, 5} for p in picks),  # 2, 5: wrong on the lesson page, asked again
      "son tekrarda sorulmayanlar önce gelir (derste yanlış yapılanlar hariç)")

# 6. Frequent mistakes in a topic bring that topic's finished lesson forward.
target = next(l for l in lessons.LESSONS if l["id"] in A1[1:6] and l["categories"]
              and l["id"] not in [x["lesson_id"] for x in reviews.overview()["due"]])
cat = target["categories"][0]
with get_conn() as conn:
    for k in range(reviews.WEAK_MIN):
        conn.execute("INSERT INTO error_log (source, category, wrong, right, created_at) VALUES ('speech', ?, 'a', 'b', ?)",
                     (cat, iso_days_ago(k)))
    conn.execute("UPDATE lesson_review SET created_at = ?, last_reviewed_at = NULL WHERE lesson_id = ?",
                 (iso_days_ago(reviews.PULL_GAP + 1), target["id"]))
r = reviews.overview()
pulled = [x for x in r["due"] if x["lesson_id"] == target["id"]]
check(pulled and pulled[0].get("pulled") and "öne alındı" in pulled[0]["reason"],
      f"sık hata yapılan konunun ({cat}) dersi tekrara öne alındı")
check(any(w["category"] == cat for w in r["weak"]), "zayıf konular listelenir")
with get_conn() as conn:
    conn.execute("UPDATE lesson_review SET last_reviewed_at = ? WHERE lesson_id = ?", (iso_days_ago(1), target["id"]))
check(target["id"] not in [x["lesson_id"] for x in reviews.overview()["due"]],
      "yakında tekrar edildiyse hemen yeniden öne alınmaz")

# 7. Resetting a lesson's progress / "Sıfırla → Dersler" removes its schedule.
lessons.reset(A1[1])
check(A1[1] not in reviews._rows(), "dersin ilerlemesi sıfırlanınca tekrar takvimi de silinir")
import asyncio  # noqa: E402
from backend import reset  # noqa: E402
asyncio.run(reset.reset(["lessons"]))
check(not reviews._rows(), "Sıfırla → Dersler tekrar takvimini de siler")

print("Sorun yok ✓" if not problems else f"{len(problems)} sorun")
sys.exit(1 if problems else 0)
