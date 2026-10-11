"""N voice turns in one session; report end-of-speech → first audio latency."""
import asyncio
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import websockets
from ws_test import SAMPLE, wav_to_webm

N = int(sys.argv[1]) if len(sys.argv) > 1 else 5


async def main():
    webm = wav_to_webm(SAMPLE)
    results, sid = [], None
    async with websockets.connect("ws://127.0.0.1:8000/ws/voice", max_size=None) as ws:
        for i in range(N):
            cid = f"b{i}"
            t0 = time.perf_counter()
            await ws.send(json.dumps({"type": "audio", "session_id": sid, "client_id": cid, "speak": True}))
            await ws.send(webm)
            first_audio = first_text = None
            header = None
            while True:
                msg = await ws.recv()
                now = (time.perf_counter() - t0) * 1000
                if isinstance(msg, bytes):
                    if first_audio is None:
                        first_audio = now
                        first_text = header["text"]
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
            results.append(first_audio)
            print(f"#{i}: first audio {first_audio:.0f} ms  first chunk {first_text!r}\n     reply: {reply!r}")
    print(f"\nmedian {statistics.median(results):.0f} ms, max {max(results):.0f} ms, min {min(results):.0f} ms")
    print("SESSION", sid)


asyncio.run(main())
