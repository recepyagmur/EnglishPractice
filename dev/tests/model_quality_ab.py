"""Run the app's LLM tasks with several models and save every output side by side.

Switches the session model through the API (the default model is not changed), then runs
corrections, he/she, lesson answer checks, a level exam, writing review, a scenario with
its report, free chat, word explanation and translation.

    runtime\\python\\python.exe dev\\tests\\model_quality_ab.py <out dir> [app url] [model ...]

Run it against a test data copy (EP_DATA_DIR): exams, writings and sessions are saved.
"""
import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request

import websockets

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1]
APP = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000"
MODELS = sys.argv[3:] or ["qwen3:8b", "gemma4:e4b"]
PY = sys.executable

CORRECTIONS = [
    "Yesterday I go to the market and I buy some apples for my family",
    "My sister is doctor and he works in hospital",
    "I am agree with you about this topic",
    "Where you are going this weekend",
    "I have been to London last year",
    "I enjoy to play football with my friends",
    "I very happy because I passed the exam",
    "I went to the cinema with my friends last night and we watched a great movie",
    "She dont like coffee, she prefer tea.",
    "I am living in Istanbul since five years.",
    "Please find attached the report which you asked yesterday.",
    "We need to discuss about the budget in the meeting.",
    "Could you send me the informations until Friday?",
    "I look forward to hear from you.",
]
CHAT = [
    "Hi! I just finished work. It was a long day.",
    "We had three meetings and my boss was angry because the project is late.",
    "I think we need more people in the team but the company don't want to hire.",
    "What do you think, should I talk to my boss about it?",
]
EXPLAIN = [("run", "She runs a small company in Izmir."), ("deadline", "The deadline for the report is Friday."),
           ("put off", "We had to put off the meeting until next week.")]
TRANSLATE = ["Could we move the meeting to tomorrow afternoon?",
             "I'm afraid we won't be able to meet the deadline.",
             "Thanks for getting back to me so quickly."]


def call(method, path, body=None, timeout=300):
    req = urllib.request.Request(APP + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def switch(model):
    call("PUT", "/api/llm/active", {"model": model})
    while call("GET", "/api/llm")["busy"]:
        time.sleep(0.5)


async def chat(log):
    async with websockets.connect(APP.replace("http", "ws") + "/ws/voice") as ws:
        sid = None
        for i, text in enumerate(CHAT):
            cid = f"ab{i}"
            await ws.send(json.dumps({"type": "text", "text": text, "session_id": sid, "client_id": cid, "speak": False}))
            t0 = time.perf_counter()
            while True:
                ev = json.loads(await ws.recv())
                if ev.get("client_id") not in (None, cid):
                    continue
                if ev["type"] == "meta":
                    sid = ev["session_id"]
                elif ev["type"] == "correction":
                    log(f"     düzeltme: {json.dumps(ev.get('result', ev), ensure_ascii=False)[:400]}")
                elif ev["type"] == "done":
                    log(f"  me: {text}\n  AI ({(time.perf_counter() - t0):.1f}s): {ev['text']}")
                    break
                elif ev["type"] == "error":
                    log(f"  ERROR {ev}")
                    break


def run_model(model):
    path = os.path.join(OUT, model.replace(":", "_") + ".txt")
    f = open(path, "w", encoding="utf-8")

    def log(s=""):
        f.write(s + "\n")
        f.flush()

    t = time.perf_counter()
    switch(model)
    log(f"# {model} (geçiş {time.perf_counter() - t:.1f}s)")

    log("\n## Düzeltmeler (/api/correct)")
    for text in CORRECTIONS:
        t = time.perf_counter()
        r = call("POST", "/api/correct", {"text": text, "source": "text"})
        log(f"\n[{time.perf_counter() - t:.1f}s] {text}\n   → {r.get('corrected')}")
        for e in r.get("errors", []):
            log(f"     · {e['category']:<22} {e['wrong']!r} → {e['right']!r}: {e.get('explanation')}")
        if r.get("more_natural"):
            log(f"     ~ {r['more_natural']}")

    log("\n## Sohbet")
    asyncio.run(chat(log))

    log("\n## Kelime açıklama / çeviri")
    for word, sent in EXPLAIN:
        t = time.perf_counter()
        log(f"[{time.perf_counter() - t:.1f}s] {word}: {json.dumps(call('POST', '/api/dictionary/explain', {'word': word, 'sentence': sent}), ensure_ascii=False)}")
    for text in TRANSLATE:
        t = time.perf_counter()
        r = call("POST", "/api/translate", {"text": text})
        log(f"[{time.perf_counter() - t:.1f}s] {text}\n   → {json.dumps(r, ensure_ascii=False)}")

    for script, args in [("pronoun_correction_test.py", [APP]), ("lesson_check_test.py", [APP]),
                         ("exam_test.py", [APP, "A2"]), ("writing_test.py", [APP]), ("scenario_test.py", [APP])]:
        log(f"\n## {script}")
        t = time.perf_counter()
        p = subprocess.run([PY, os.path.join(HERE, script), *args], capture_output=True, text=True, encoding="utf-8",
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        log(p.stdout + (("\nSTDERR:\n" + p.stderr[-2000:]) if p.returncode else ""))
        log(f"({time.perf_counter() - t:.0f}s)")
    f.close()
    print("done", model, path, flush=True)


os.makedirs(OUT, exist_ok=True)
for m in MODELS:
    run_model(m)
call("PUT", "/api/llm/active", {"model": None})
