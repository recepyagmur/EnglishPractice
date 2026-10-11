"""Word study through the API: lists, learn, checked example sentences, own-sentence checks.
Usage: python words_test.py [app url, default http://127.0.0.1:8000]  (use a test data copy)"""

import json
import sys
import time
import urllib.request
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ✓ on a Windows (cp1254) console

APP = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


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
    print(f"{'✓' if cond else '✗'} {name}{' — ' + detail if detail else ''}")


o = call("GET", "/api/words")
check("5 seviye, hepsi dolu", len(o["levels"]) == 5 and all(l["total"] > 800 for l in o["levels"]),
      ", ".join(f"{l['level']} {l['total']}" for l in o["levels"]))
a1 = call("GET", "/api/words/level/A1")["words"]
check("her kelimenin Türkçe anlamı var", all(w["tr"] for w in a1))
check("kelime türü Türkçe", any(w["pos_tr"] == "fiil" for w in a1))

learned = call("POST", "/api/words/learn", {"words": ["celebrate", "colleague"]})
check("öğrenmeye eklendi (deftere)", len(learned) == 2 and learned[0]["level"] and learned[0]["meaning_tr"])
again = call("POST", "/api/words/learn", {"words": ["celebrate"]})
check("aynı kelime iki kez eklenmez", again[0]["id"] == learned[0]["id"])

t = time.perf_counter()
r = call("POST", "/api/words/examples", {"word": "colleague"})
check("örnek cümle üretildi", r["examples"], f"{len(r['examples'])} örnek, {time.perf_counter() - t:.1f} sn, elenen {r['rejected']}")
for ex in r["examples"]:
    check("  örnek kelimeyi içeriyor", "colleague" in ex["en"].lower(), f"{ex['en']} | {ex['tr']}")
check("saklanan örnek tekrar istenince gelir", call("GET", "/api/words/examples?word=colleague")["examples"] == r["examples"])

for text, expect in [
    ("My colleague helps me with the reports every week.", "ok"),
    ("My colleague help me with the reports every week.", "wrong"),     # grammar
    ("I went to the cinema with my friends.", "wrong"),                 # word not used
    ("Meslektaşım bana çok yardım ediyor.", "wrong"),                   # not English
    ("Colleague is a colour of the sky.", None),                        # nonsense meaning: warn or wrong
]:
    v = call("POST", "/api/words/check", {"word": "colleague", "text": text})
    good = v["verdict"] == expect if expect else v["verdict"] in ("warn", "wrong")
    check(f"kendi cümlen: {expect or 'warn/wrong'}", good, f"{v['verdict']} — {v['message_tr']} | {text}")

print(f"\n{ok}/{total} doğru")
