"""Input checks: non-English chat messages (/api/correct) and lesson answers (/api/lessons/<id>/check).
Usage: python lesson_check_test.py [app url, default http://127.0.0.1:8100]"""

import json
import sys
import time
import urllib.request
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ✓ on a Windows (cp1254) console

APP = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8100"


def post(path, body):
    req = urllib.request.Request(APP + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))


print("— /api/correct: İngilizce değil mi?")
for text, expect in [("asdasd qwe zxc", True), ("ben dün okula gittim", True), ("Merhaba, nasılsın?", True),
                     ("I met Ayşe in Kadıköy yesterday.", False), ("Yesterday I go school", False), ("ok", False),
                     ("Yes, I can.", False)]:
    r = post("/api/correct", {"text": text, "source": "text"})
    print(f"{'✓' if r.get('not_english') == expect else '✗'} not_english={r.get('not_english')}  {text}")

CASES = [  # lesson, question, answer, expected verdict
    ("a1-pronouns", "Tell me about your mother's job.", "She is a nurse and she works at night.", "ok"),
    ("a1-pronouns", "Tell me about your mother's job.", "He is a nurse and his hospital is big.", "wrong"),
    ("a1-pronouns", "Tell me about your mother's job.", "I like playing football on Sundays.", "wrong"),
    ("a1-pronouns", "Tell me about your mother's job.", "asdf qwer", "wrong"),
    ("a1-present-simple", "What does your father do every morning?", "He drinks tea and reads the newspaper.", "ok"),
    ("a1-present-simple", "What does your father do every morning?", "He drink tea every morning.", "wrong"),
    ("a1-present-simple", "What does your father do every morning?", "The sky is blue today.", "wrong"),
    ("a1-can", "What can you do well?", "I can cook very well.", "ok"),
    ("a1-can", "What can you do well?", "Cooking is my hobby.", "warn"),
]
print("\n— /api/lessons/<id>/check")
ok = 0
for lesson, q, a, expect in CASES:
    t0 = time.perf_counter()
    r = post(f"/api/lessons/{lesson}/check", {"question": q, "answer": a})
    good = r["verdict"] == expect
    ok += good
    print(f"{'✓' if good else '✗'} {time.perf_counter() - t0:4.1f}s [{r['verdict']:5}] beklenen {expect:5} | {a}\n      {r['message_tr']}")
print(f"\n{ok}/{len(CASES)} doğru")
