"""Voice turn over /ws/voice with TTS: time transcript, first token, first audio, end."""
import asyncio
import io
import json
import time
import wave

import sys
sys.path.insert(0, __import__("os").path.dirname(__file__))
import websockets
from ws_test import SAMPLE, wav_to_webm

created_sessions = []


async def turn(ws, header, payload=None, cancel_after_audio=None):
    t0 = time.perf_counter()
    await ws.send(json.dumps(header))
    if payload is not None:
        await ws.send(payload)
    ms = lambda: round((time.perf_counter() - t0) * 1000)
    first_token = first_audio = None
    chunks = []
    expecting_audio = None
    while True:
        msg = await ws.recv()
        if isinstance(msg, bytes):
            with wave.open(io.BytesIO(msg)) as w:
                secs = w.getnframes() / w.getframerate()
            if first_audio is None:
                first_audio = ms()
            chunks.append((expecting_audio["seq"], expecting_audio["text"], round(secs, 2), ms()))
            if cancel_after_audio is not None and len(chunks) == cancel_after_audio:
                await ws.send(json.dumps({"type": "cancel"}))
                print(f"  → cancel sent @{ms()}ms")
                await asyncio.sleep(1.5)
                return chunks
            continue
        ev = json.loads(msg)
        if ev.get("client_id") != header["client_id"]:
            continue
        kind = ev["type"]
        if kind == "transcript":
            print(f"  transcript @{ms()}ms: {ev['text']!r}")
        elif kind == "meta":
            created_sessions.append(ev["session_id"])
        elif kind == "delta" and first_token is None:
            first_token = ms()
        elif kind == "audio":
            expecting_audio = ev
        elif kind == "done":
            print(f"  text done @{ms()}ms: {ev['text']!r}")
        elif kind == "error":
            print(f"  ERROR @{ms()}ms: {ev['message']}")
            return chunks
        elif kind == "audio_end":
            print(f"  first token @{first_token}ms, FIRST AUDIO @{first_audio}ms, audio_end @{ms()}ms")
            for c in chunks:
                print(f"    #{c[0]} {c[2]:>5}s audio, ready @{c[3]}ms: {c[1]!r}")
            return chunks


async def main():
    webm = wav_to_webm(SAMPLE)
    async with websockets.connect("ws://127.0.0.1:8000/ws/voice", max_size=None) as ws:
        print("voice turn (cold-ish):")
        await turn(ws, {"type": "audio", "session_id": None, "client_id": "v1", "speak": True}, webm)
        sid = created_sessions[-1]
        print("voice turn (warm):")
        await turn(ws, {"type": "audio", "session_id": sid, "client_id": "v2", "speak": True}, webm)
        print("text turn, long answer, cancel after first audio chunk:")
        await turn(ws, {"type": "text", "session_id": sid, "client_id": "t1", "speak": True,
                        "text": "Can you tell me a short story about a cat who travels to London?"},
                   cancel_after_audio=1)
        print("text turn, speak=False:")
        t0 = time.perf_counter()
        await ws.send(json.dumps({"type": "text", "session_id": sid, "client_id": "t2", "speak": False,
                                  "text": "Thanks!"}))
        got_audio = False
        while True:
            msg = await ws.recv()
            if isinstance(msg, bytes):
                got_audio = True
                continue
            ev = json.loads(msg)
            if ev.get("client_id") == "t2" and ev["type"] in ("done", "error"):
                break
        await asyncio.sleep(0.5)
        print(f"  done, audio received: {got_audio}")
    print("SESSIONS", sorted(set(created_sessions)))


asyncio.run(main())
