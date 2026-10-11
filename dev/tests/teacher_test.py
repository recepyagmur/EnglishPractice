"""Turkish teacher through the API: a plain question, a quoted sentence to check, "Neden yanlış?"
from a correction, a lesson context and practice mode with a wrong and a right answer.
Usage: python teacher_test.py [app url, default http://127.0.0.1:8000]  (use a test data copy)"""

import json
import sys
import time
import urllib.request

APP = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def ask(text="", session_id=None, context=None):
    req = urllib.request.Request(APP + "/api/teacher/chat", headers={"Content-Type": "application/json"},
                                 data=json.dumps({"session_id": session_id, "text": text, "context": context}).encode())
    t0, first, out = time.perf_counter(), None, {"reply": ""}
    with urllib.request.urlopen(req, timeout=300) as resp:
        event = None
        for raw in resp:
            line = raw.decode("utf-8").rstrip("\n")
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
                if event == "meta":
                    out.update(session_id=data["session_id"], user_text=data["user_text"])
                elif event == "correction":
                    out["correction"] = data
                elif event == "delta" and first is None:
                    first = time.perf_counter() - t0
                elif event == "done":
                    out["reply"] = data["text"]
                elif event == "error":
                    out["error"] = data["message"]
    out["time"] = f"ilk kelime {first or 0:.1f}s, toplam {time.perf_counter() - t0:.1f}s"
    return out


def show(title, r):
    print(f"\n=== {title}  ({r['time']})")
    if r.get("user_text"):
        print("SORU:", r["user_text"])
    if c := r.get("correction"):
        print("KONTROL:", c["corrected"], [(e["wrong"], e["right"]) for e in c["errors"]])
    print(r.get("error") or r["reply"])


show("Serbest soru", ask("'used to' ile 'be used to' farkı ne?"))
show("Alıntılanan cümle (yanlış)", ask("'I am working here since 2020' doğru mu?"))
show("Alıntılanan cümle (doğru)", ask("\"She doesn't like long meetings\" doğru mu?"))
r = ask(context={"type": "error", "sentence": "My sister is doctor and he works in hospital",
                 "corrected": "My sister is a doctor and she works in hospital", "wrong": "he", "right": "she",
                 "category": "pronoun", "explanation": "Kız kardeş için 'she' kullanılır."})
show("Neden yanlış?", r)
print("\nboş soru reddedilir:", ask(context={"type": "lesson", "lesson_id": "a2-articles"}).get("error"))
show("Ders: soru", ask("Bu konuyu kısaca özetler misin?", context={"type": "lesson", "lesson_id": "a2-articles"}))
p = ask(context={"type": "practice", "category": "article"})
show("Alıştırma: ilk soru", p)
show("Alıştırma: yanlış cevap", ask("I bought new car and the car is red.", p["session_id"]))
show("Alıştırma: sonraki cevap", ask("She is an engineer at a big company.", p["session_id"]))
hist = json.load(urllib.request.urlopen(APP + "/api/teacher/sessions"))
print("\nGEÇMİŞ:", [(h["id"], h["title"], h["message_count"]) for h in hist])
print("pratik listesinde öğretmen yok:",
      all(s["mode"] != "teacher" for s in json.load(urllib.request.urlopen(APP + "/api/sessions"))))
