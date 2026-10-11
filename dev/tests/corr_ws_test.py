"""Chat turns over /ws/voice on the test server: correction events arrive after the reply;
a new turn pauses a running correction without delaying the chat."""
import asyncio
import json
import sys
import time

import websockets

PORT = sys.argv[1] if len(sys.argv) > 1 else "8100"
TEXTS = ["My sister is doctor and he works in hospital", "I very happy today", "I went to the park with my dog."]


async def main():
    sid = None
    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws/voice", max_size=None) as ws:
        t0 = time.perf_counter()
        ms = lambda: round((time.perf_counter() - t0) * 1000)
        pending = set()
        for i, text in enumerate(TEXTS):
            cid = f"c{i}"
            sent = ms()
            await ws.send(json.dumps({"type": "text", "text": text, "session_id": sid, "client_id": cid, "speak": False}))
            while True:
                ev = json.loads(await ws.recv())
                if ev["type"] == "meta" and ev["client_id"] == cid:
                    sid = ev["session_id"]
                    pending.add(ev["user_message_id"])
                elif ev["type"] == "delta" and ev["client_id"] == cid and "first" not in locals().get("flags", {}):
                    pass
                elif ev["type"] == "correction":
                    pending.discard(ev["message_id"])
                    print(f"  @{ms()}ms correction #{ev['message_id']}: {ev['corrected']!r} "
                          f"{[(e['category'], e['wrong'], e['right']) for e in ev['errors']]}")
                elif ev["type"] == "done" and ev["client_id"] == cid:
                    print(f"@{ms()}ms reply to {text!r} done in {ms() - sent}ms: {ev['text'][:60]!r}")
                    break
            # Send the next message right away: it must not wait for the correction.
        while pending:
            ev = json.loads(await ws.recv())
            if ev["type"] == "correction":
                pending.discard(ev["message_id"])
                print(f"  @{ms()}ms correction #{ev['message_id']}: {ev['corrected']!r} "
                      f"{[(e['category'], e['wrong'], e['right']) for e in ev['errors']]}")
    print("SESSION", sid)


asyncio.run(main())
