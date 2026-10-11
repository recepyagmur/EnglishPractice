"""he/she reference errors (the most common Turkish-learner mistake) through /api/correct.
Usage: python pronoun_correction_test.py [app url, default http://127.0.0.1:8000]"""

import json
import sys
import time
import urllib.request
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ✓ on a Windows (cp1254) console

APP = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

CASES = [  # (sentence, should be flagged)
    ("Yes, I have a sister. He is a teacher and his school is near our house.", True),
    ("My mother is a nurse. He works at night.", True),
    ("My father is very busy, she works every day.", True),
    ("Ayşe is my friend and his brother is a doctor.", True),
    ("I called my brother and talked to her for an hour.", True),
    ("My sister is a teacher. She loves her job.", False),
    ("My brother lives in Izmir with his wife.", False),
    ("I met Can yesterday. He told me about his new job.", False),
]

ok = 0
for text, should in CASES:
    t0 = time.perf_counter()
    req = urllib.request.Request(f"{APP}/api/correct", data=json.dumps({"text": text, "source": "text"}).encode(),
                                 headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=120))
    flagged = any(e["category"] == "pronoun" for e in r["errors"])
    good = flagged == should
    ok += good
    print(f"{'✓' if good else '✗'} {time.perf_counter() - t0:4.1f}s  {text}\n     → {r['corrected']}"
          + "".join(f"\n       [{e['category']}] {e['wrong']} → {e['right']}" for e in r["errors"]))
print(f"\n{ok}/{len(CASES)} doğru")
