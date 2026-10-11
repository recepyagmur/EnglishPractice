"""Typed turns with varied input: check openings vary and first chunk stays short."""
import asyncio
import json
import time

import websockets

TEXTS = [
    "Yesterday I go to the market and I buy some apples.",
    "My cat is sick and I am very worried about him.",
    "I got a new job as a software developer last week!",
    "I don't like rainy days because I can't go outside.",
    "We are planning a trip to Italy in the summer.",
    "I watched a horror movie last night and I couldn't sleep.",
]


async def main():
    sid = None
    async with websockets.connect("ws://127.0.0.1:8000/ws/voice", max_size=None) as ws:
        for i, text in enumerate(TEXTS):
            cid = f"v{i}"
            t0 = time.perf_counter()
            await ws.send(json.dumps({"type": "text", "text": text, "session_id": sid, "client_id": cid, "speak": True}))
            first, header, reply = None, None, ""
            while True:
                msg = await ws.recv()
                if isinstance(msg, bytes):
                    if first is None:
                        first = ((time.perf_counter() - t0) * 1000, header["text"])
                    continue
                ev = json.loads(msg)
                if ev.get("client_id") != cid:
                    continue
                if ev["type"] == "meta":
                    sid = ev["session_id"]
                elif ev["type"] == "audio":
                    header = ev
                elif ev["type"] == "done":
                    reply = ev["text"]
                elif ev["type"] in ("audio_end", "error"):
                    break
            print(f"{first[0]:5.0f} ms  [{first[1]}]  {reply}")
    print("SESSION", sid)


asyncio.run(main())
