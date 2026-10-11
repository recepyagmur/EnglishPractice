"""Send the sample utterance as webm/opus over /ws/voice and time each event."""
import asyncio
import io
import json
import sys
import time

from pathlib import Path

import av
import websockets

PORT = sys.argv[1] if len(sys.argv) > 1 else "8000"
SAMPLE = str(Path(__file__).resolve().parents[2] / "setup" / "assets" / "sample.wav")


def wav_to_webm(path: str) -> bytes:
    out = io.BytesIO()
    with av.open(path) as src, av.open(out, "w", format="webm") as dst:
        stream = dst.add_stream("libopus", rate=48000)
        resampler = av.AudioResampler(format="s16", layout="mono", rate=48000)
        for frame in src.decode(audio=0):
            for f in resampler.resample(frame):
                for packet in stream.encode(f):
                    dst.mux(packet)
        for packet in stream.encode(None):
            dst.mux(packet)
    return out.getvalue()


async def turn(ws, header, payload=None):
    t0 = time.perf_counter()
    await ws.send(json.dumps(header))
    if payload is not None:
        await ws.send(payload)
    first_delta = None
    while True:
        ev = json.loads(await ws.recv())
        dt = (time.perf_counter() - t0) * 1000
        if ev["type"] == "transcript":
            print(f"  transcript @{dt:.0f}ms (stt {ev['elapsed_ms']}ms): {ev['text']!r}")
        elif ev["type"] == "delta" and first_delta is None:
            first_delta = dt
            print(f"  first LLM token @{dt:.0f}ms")
        elif ev["type"] in ("done", "error"):
            print(f"  {ev['type']} @{dt:.0f}ms: {ev.get('text') or ev.get('message')}")
            return ev


async def main():
    webm = wav_to_webm(SAMPLE)
    print(f"webm/opus payload: {len(webm)} bytes")
    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws/voice", max_size=None) as ws:
        print("voice turn 1:")
        done = await turn(ws, {"type": "audio", "session_id": None, "client_id": "a1"}, webm)
        sid = None
        print("voice turn 2 (same audio):")
        await turn(ws, {"type": "audio", "session_id": sid, "client_id": "a2"}, webm)
        print("text turn:")
        await turn(ws, {"type": "text", "text": "What do you like to eat?", "session_id": sid, "client_id": "t1"})
        print("too-short audio:")
        short = wav_to_webm(SAMPLE)[:600]
        await turn(ws, {"type": "audio", "session_id": sid, "client_id": "s1"}, short)


if __name__ == "__main__":
    asyncio.run(main())
