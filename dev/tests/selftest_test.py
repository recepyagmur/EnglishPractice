"""Self-tests (🎯 Kendini Test Et) through the API: overview, starting a typed set and a mini exam, that the
learner never receives answers, saving answers, resuming, finishing and grading, the result, history, deleting.
Usage: python selftest_test.py [app url, default http://127.0.0.1:8100]  (use a test data copy)"""

import json
import sys
import urllib.error
import urllib.request
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ✓ on a Windows (cp1254) console

APP = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8100"


def call(method, path, body=None):
    req = urllib.request.Request(APP + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


ok = total = 0


def check(name, cond, detail=""):
    global ok, total
    total += 1
    ok += bool(cond)
    print(("✓" if cond else "✗"), name, detail if not cond else "")


o = call("GET", "/api/selftest")
check("10 question types with pools", len(o["types"]) == 10 and all(t["pool"] for t in o["types"]), [(t["type"], t["pool"]) for t in o["types"]])
check("mini total 40", o["mini_total"] == 40)

# a typed set
a = call("POST", "/api/selftest/start", {"kind": "type", "qtype": "reading", "count": 8, "timing": "standard"})
check("reading set: 8 questions = 2 passages", len(a["questions"]) == 8 and len(a["passages"]) == 2, (len(a["questions"]), len(a["passages"])))
check("time limit 8 × 135 s", a["time_limit_s"] == 8 * 135 and 0 < a["remaining_s"] <= a["time_limit_s"], (a["time_limit_s"], a["remaining_s"]))
check("no answers / explanations sent", all("answer" not in q and "explain_tr" not in q for q in a["questions"]))
check("running attempt in overview", call("GET", "/api/selftest")["running"]["id"] == a["id"])
ids = [q["id"] for q in a["questions"]]
check("save answers", call("PUT", f"/api/selftest/attempts/{a['id']}/answers", {"answers": {ids[0]: 2, "bogus": 1}})["ok"])
resumed = call("GET", f"/api/selftest/attempts/{a['id']}")
check("resume keeps saved answers only", resumed["answers"] == {ids[0]: 2}, resumed["answers"])
r = call("POST", f"/api/selftest/attempts/{a['id']}/finish", {"answers": {ids[1]: 0}})
check("graded: 8 items, 6 blank", r["total"] == 8 and r["blank"] == 6 and len(r["items"]) == 8, (r["total"], r["blank"]))
check("items carry answer + explanation", all(it["answer"] in range(5) and it["explain_tr"] for it in r["items"]))
check("score = correct/total", r["score"] == round(100 * r["correct"] / r["total"], 1))
res = call("GET", f"/api/selftest/attempts/{a['id']}/result")
check("result has questions + passages", len(res["questions"]) == 8 and len(res["passages"]) == 2)
try:
    call("GET", f"/api/selftest/attempts/{a['id']}")
    check("finished attempt is no longer running", False)
except urllib.error.HTTPError as e:
    check("finished attempt is no longer running", e.code == 404, e.code)

# a mini exam without time limit
m = call("POST", "/api/selftest/start", {"kind": "mini", "timing": "none"})
types = [q["type"] for q in m["questions"]]
check("mini: 40 questions, no limit", len(m["questions"]) == 40 and m["time_limit_s"] is None and m["remaining_s"] is None)
check("mini: YDS order and shares", types == sorted(types, key=["vocab", "grammar", "cloze", "sentence", "translation", "reading",
      "dialogue", "paraphrase", "paragraph", "irrelevant"].index) and types.count("reading") == 8 and types.count("cloze") == 5, types)
tr = [q for q in m["questions"] if q["type"] == "translation"]
check("mini: both translation directions", {q["direction"] for q in tr} == {"en-tr", "tr-en"}, [q["direction"] for q in tr])
r2 = call("POST", f"/api/selftest/attempts/{m['id']}/finish", {"answers": {q["id"]: 0 for q in m["questions"]}})
check("mini graded with per-type table", len(r2["per_type"]) == 10 and sum(t["total"] for t in r2["per_type"]) == 40)

# history + the "unseen first" rule + delete
o2 = call("GET", "/api/selftest")
check("history lists both", [h["id"] for h in o2["history"][:2]] == [m["id"], a["id"]])
seen = next(t for t in o2["types"] if t["type"] == "reading")
check("seen count updated", seen["seen"] == 8 + 8, seen)
b = call("POST", "/api/selftest/start", {"kind": "type", "qtype": "reading", "count": 8, "timing": "relaxed"})
check("relaxed = 1.5×", b["time_limit_s"] == round(8 * 135 * 1.5))
check("unseen passages come first", not ({q["id"] for q in b["questions"]} & set(ids)), set(ids) & {q["id"] for q in b["questions"]})
call("DELETE", f"/api/selftest/attempts/{b['id']}")
call("DELETE", f"/api/selftest/attempts/{m['id']}")
call("DELETE", f"/api/selftest/attempts/{a['id']}")
o3 = call("GET", "/api/selftest")
check("deleted", not o3["running"] and all(h["id"] not in (a["id"], m["id"], b["id"]) for h in o3["history"]))
try:
    call("POST", "/api/selftest/start", {"kind": "type", "qtype": "reading", "count": 7, "timing": "standard"})
    check("bad count → 400", False)
except urllib.error.HTTPError as e:
    check("bad count → 400", e.code == 400, e.code)
print(f"\n{ok}/{total} ✓")
sys.exit(0 if ok == total else 1)
