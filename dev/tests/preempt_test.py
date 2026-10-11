"""A chat turn arriving while a correction is being generated must not wait for it."""
import asyncio
import json
import time

import websockets


async def turn(ws, cid, text, sid, log):
    t = time.perf_counter()
    await ws.send(json.dumps({"type": "text", "text": text, "session_id": sid, "client_id": cid, "speak": False}))
    while True:
        ev = json.loads(await ws.recv())
        if ev["type"] == "correction":
            log.append(ev)
        elif ev.get("client_id") == cid and ev["type"] == "meta":
            sid = ev["session_id"]
        elif ev.get("client_id") == cid and ev["type"] == "done":
            return sid, round((time.perf_counter() - t) * 1000)


async def main():
    got = []
    async with websockets.connect("ws://127.0.0.1:8100/ws/voice") as ws:
        sid, ms = await turn(ws, "p1", "Yesterday I go to school and I meet my friends", None, got)
        print(f"turn 1 reply: {ms} ms")
        await asyncio.sleep(1.0)  # correction of turn 1 is now running
        sid, ms = await turn(ws, "p2", "We eat lunch together in the garden", sid, got)
        print(f"turn 2 reply (sent during correction 1): {ms} ms")
        while len(got) < 2:
            ev = json.loads(await ws.recv())
            if ev["type"] == "correction":
                got.append(ev)
        for c in got:
            print(f"correction #{c['message_id']}: {c['corrected']!r} {[(e['category'], e['wrong'], e['right']) for e in c['errors']]}")
    print("SESSION", sid)


asyncio.run(main())
