"""Switch the session model, chat right away, check events and what is in VRAM."""
import asyncio
import json
import os
import sys
import time
import urllib.request

import websockets

APP = "http://127.0.0.1:8000"
OLLAMA = os.environ["OLLAMA_URL"]


def call(method, path, body=None, base=APP):
    req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def loaded():
    return [m["name"] for m in call("GET", "/api/ps", base=OLLAMA)["models"]]


async def turn(text, session_id=None):
    async with websockets.connect("ws://127.0.0.1:8000/ws/voice") as ws:
        await ws.send(json.dumps({"type": "text", "text": text, "session_id": session_id, "client_id": "t1", "speak": False}))
        events, t0 = [], time.perf_counter()
        while True:
            ev = json.loads(await ws.recv())
            if ev["type"] != "delta":
                events.append((round(time.perf_counter() - t0, 2), ev["type"], ev.get("message") or ev.get("text", "")[:60]))
            if ev["type"] in ("done", "error"):
                return events, ev


async def main():
    target = sys.argv[1]
    print("before:", loaded())
    s = call("PUT", "/api/llm/active", {"model": target})
    print("PUT active →", s["active"], "override", s["override"], "busy", s["busy"])
    events, last = await turn("Hi! What did you do last weekend?")
    for e in events:
        print("  ", e)
    print("after:", loaded())
    s = call("GET", "/api/llm")
    print("state:", s["default"], s["active"], s["override"], s["busy"], s["load_error"])
    return last


if __name__ == "__main__":
    asyncio.run(main())
