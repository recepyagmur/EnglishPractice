"""A level exam through the API with (mostly) correct answers: it should pass; an unrelated
speaking answer must score 0. Each attempt draws its own items, so the answers are looked up by id
(speaking/writing answers are written for A1). Usage: python exam_test.py [app url] [level]"""

import json
import re
import sys
import time
import urllib.request
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ✓ on a Windows (cp1254) console

APP = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8100"
LEVEL = sys.argv[2] if len(sys.argv) > 2 else "A1"
CONTENT = json.loads((Path(__file__).parents[2] / "app" / "content" / "exams" / f"{LEVEL}.json").read_text(encoding="utf-8"))

SPEAKING_A1 = {
    "s1": "My name is Ali. I am from Izmir and I am a teacher.",
    "s2": "My mother is a teacher. She gets up at six and she goes to school by bus.",
    "s3": "I can cook very well and I can speak Turkish. I can't swim and I can't play the piano.",
    "s4": "There is a desk in my office. There are two chairs next to the desk and there is a computer on it.",
    "s5": "I am an engineer and I work for a big company in Bursa. I start work at nine and I finish at six.",
    "s6": "Where do you work? What do you do in your job? What time do you start work?",
}
WRITING_A1 = {
    "w1": ("Hi Ali! My flat is small but it is nice. There is a big park near my house and there are two cafes "
           "in my street. There isn't a cinema, so I go to the city centre for films. At the weekend I usually "
           "get up late. On Saturdays I meet my friends in the park, and on Sundays I cook for my family."),
    "w2": ("Hello Ayşe, my name is Ali and I am the new engineer in the IT department. I check the computers "
           "every morning and I answer emails from my colleagues. I help people with their problems every day. "
           "I have lunch at one o'clock. See you soon!"),
    "w3": ("Dear Mr Smith, I would like to invite you to a meeting at our office on Monday at ten o'clock. "
           "The meeting room is on the second floor, next to the kitchen. My phone number is 0532 111 22 33. "
           "Please call me if you have any questions. Best regards, Ali"),
}
UNRELATED = "The weather is very nice and the sky is blue today."


def post(path, body=None):
    req = urllib.request.Request(APP + path, data=json.dumps(body or {}).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=300))


def tiles_in_order(q):
    """The order tiles arranged as the first answer (what the page sends)."""
    words = lambda s: re.findall(r"[a-z0-9']+", s.lower())
    target, left, out = words(q["answer"][0]), list(q["words"]), []
    while target:
        tile = next(t for t in left if words(t) == target[:len(words(t))])
        left.remove(tile)
        out.append(tile)
        target = target[len(words(tile)):]
    return " ".join(out)


exam = post(f"/api/exams/{LEVEL}/start")
bank = {q["id"]: q for q in CONTENT["grammar"]}
grammar = {q["id"]: (bank[q["id"]]["answer"] if q["type"] == "choice" else tiles_in_order(bank[q["id"]])
                     if q["type"] == "order" else bank[q["id"]]["answer"][0]) for q in exam["grammar"]}
listening = {d["id"]: d["text"] for d in exam["listening"]["dictation"]}
full = {c["id"]: c for c in CONTENT["listening"]["comprehension"]}
for c in exam["listening"]["comprehension"]:
    listening.update({q["id"]: q["answer"] for q in full[c["id"]]["questions"]})
asked = [s["id"] for s in exam["speaking"]]
speaking = {sid: {"text": SPEAKING_A1.get(sid, UNRELATED), "typed": False} for sid in asked}
speaking[asked[-1]] = {"text": UNRELATED, "typed": False}  # unrelated on purpose
task = next(w for w in CONTENT["writing"] if w["prompt_en"] == exam["writing"]["prompt_en"])
writing = WRITING_A1.get(task["id"], "")
print(f"asked: speaking {asked}, writing {task['id']}, grammar types "
      f"{sorted({q['type'] for q in exam['grammar']})}")
t0 = time.perf_counter()
r = post(f"/api/exams/attempts/{exam['attempt_id']}/submit",
         {"grammar": grammar, "listening": listening, "speaking": speaking, "writing": writing})
print(f"graded in {time.perf_counter() - t0:.1f}s → score {r['score']:.2f}, passed={r['passed']}, next={r['next_level']}")
for s in r["sections"]:
    print(f"  {s['name']:<10} {s['score']:.2f}")
for s in r["speaking"]:
    print(f"  speaking {s['score']:.2f}  {s['message_tr']}  | {s['text']}")
print("  writing:", r["writing"]["message_tr"])
wrong = [g for g in r["grammar"] if not g["ok"]]
print("  grammar wrong:", [(g["q"], g["your"]) for g in wrong])
ok = r["passed"] and r["speaking"][-1]["score"] == 0 and not wrong and r["sections"][1]["score"] == 1
print("\n✓ beklenen sonuç" if ok else "\n✗ beklenmeyen sonuç")
