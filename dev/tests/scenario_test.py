"""Scenario flow over /ws/voice: opening line, two learner turns, report; then a custom one."""
import asyncio
import json
import sys
import time
import urllib.request

import websockets

BASE = sys.argv[1].split("//")[-1] if len(sys.argv) > 1 else "127.0.0.1:8100"


async def until_done(ws, cid):
    out = {}
    t = time.perf_counter()
    while True:
        ev = json.loads(await ws.recv())
        if ev.get("client_id") != cid:
            continue
        if ev["type"] == "scenario":
            out["scenario"] = ev["scenario"]
            out["session_id"] = ev["session_id"]
            print(f"  scenario @{(time.perf_counter()-t)*1000:.0f}ms: {ev['scenario']['title_tr']} · tasks: {ev['scenario']['tasks_tr']}")
        elif ev["type"] == "meta":
            out["session_id"] = ev["session_id"]
        elif ev["type"] == "done":
            print(f"  AI @{(time.perf_counter()-t)*1000:.0f}ms: {ev['text']}")
            return out
        elif ev["type"] == "error":
            print("  ERROR", ev["message"])
            return out


def post(path):
    req = urllib.request.Request(f"http://{BASE}{path}", method="POST")
    t = time.perf_counter()
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.load(r)
    return data, (time.perf_counter() - t) * 1000


async def main():
    async with websockets.connect(f"ws://{BASE}/ws/voice") as ws:
        print("restaurant:")
        await ws.send(json.dumps({"type": "start_scenario", "scenario_id": "restaurant", "client_id": "s1", "speak": False}))
        sid = (await until_done(ws, "s1"))["session_id"]
        for i, text in enumerate(["Hello, what is in the chicken curry? It is spicy?", "My wife dont eat meat, she is vegetarian. You have vegetarian dish?",
                                  "OK, I want the curry and a orange juice please", "Can I pay with card? We are very hurry"]):
            print(f"  me: {text}")
            await ws.send(json.dumps({"type": "text", "text": text, "session_id": sid, "client_id": f"r{i}", "speak": False}))
            await until_done(ws, f"r{i}")

        report, ms = post(f"/api/sessions/{sid}/report")
        print(f"\nREPORT ({ms:.0f} ms):")
        print(json.dumps(report, ensure_ascii=False, indent=1))

        print("\ncustom:")
        await ws.send(json.dumps({"type": "start_scenario", "custom": "Komşumla gece geç saatteki gürültü hakkında konuşuyorum",
                                  "client_id": "c1", "speak": False}))
        await until_done(ws, "c1")
    print("SESSIONS", sid)


asyncio.run(main())
