"""Patterns (🧩 Kalıplar) through the API: overview, a level list, learning, review (SM-2), forgetting and the
own-sentence check. Usage: python patterns_test.py [app url, default http://127.0.0.1:8100]  (use a test data copy)"""

import json
import sys
import urllib.error
import urllib.request
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ✓ on a Windows (cp1254) console

APP = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8100"


def call(method, path, body=None):
    req = urllib.request.Request(APP + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


ok = total = 0


def check(name, cond, detail=""):
    global ok, total
    total += 1
    ok += bool(cond)
    print(("✓" if cond else "✗"), name, detail if not cond else "")


o = call("GET", "/api/patterns")
levels = {l["level"]: l for l in o["levels"]}
check("overview has 5 levels", len(levels) == 5, o)
check("every level has 60 patterns", all(l["total"] == 60 for l in levels.values()), {k: v["total"] for k, v in levels.items()})
lv = call("GET", "/api/patterns/level/B1")["patterns"]
check("B1 list", len(lv) == 60 and all(x["status"] in ("new", "learning", "learned") for x in lv))
check("Turkish labels", all(x["cat_tr"] and x["topic_tr"] and x["register_tr"] for x in lv), lv[0])
x = next(p for p in lv if p["status"] == "new")
before = call("GET", "/api/patterns")
learned = call("POST", "/api/patterns/learn", {"ids": [x["id"], "nope-000"]})
check("learn: known id only", [e["id"] for e in learned] == [x["id"]] and learned[0]["status"] == "learning", learned)
due = call("GET", "/api/patterns/due")
check("learned pattern is due today", any(e["id"] == x["id"] for e in due))
after = call("GET", "/api/patterns")
check("overview counts it", after["learning"] == before["learning"] + 1 and after["due"] == before["due"] + 1)
r = call("POST", f"/api/patterns/{x['id']}/review", {"grade": "good"})
check("review good → due later", r["status"] == "learning" and r["due"] > due[0]["due"], r)
r = call("POST", f"/api/patterns/{x['id']}/review", {"grade": "again"})
check("review again → due today", r["due"] == max(e["due"] for e in due), r)
try:
    call("POST", "/api/patterns/zzz-000/review", {"grade": "good"})
    check("review unknown → 404", False)
except urllib.error.HTTPError as e:
    check("review unknown → 404", e.code == 404, e.code)
# own sentence: one of the pattern's own examples must pass, a sentence without the pattern must not
r = call("POST", "/api/patterns/check", {"id": x["id"], "text": "Merhaba nasılsın bugün"})
check("check: Turkish text rejected", r["verdict"] == "wrong", r)
r = call("POST", "/api/patterns/check", {"id": x["id"], "text": "The weather is nice today and I am happy."})
check("check: pattern missing → wrong", r["verdict"] == "wrong" and "kalıbı yok" in r["message_tr"], r)
r = call("POST", "/api/patterns/check", {"id": x["id"], "text": x["examples"][0]["en"]})
check("check: the pattern's own example passes (LLM)", r["verdict"] == "ok", r)
check("forget", call("DELETE", f"/api/patterns/{x['id']}/progress")["ok"] is True)
final = call("GET", "/api/patterns")
check("counts back", final["learning"] == before["learning"] and final["due"] == before["due"])
print(f"\n{ok}/{total} ✓")
sys.exit(0 if ok == total else 1)
