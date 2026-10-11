"""Start the speed test, chat during it (must wait), print results and VRAM state."""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model_switch_test import call, loaded, turn


async def main():
    s = call("POST", "/api/llm/benchmark", {"models": None})
    print("started:", s["benchmark"]["models"], "busy", s["busy"])
    await asyncio.sleep(1)
    t0 = time.perf_counter()
    events, last = await turn("Tell me one thing about cats.")
    for e in events:
        print("  ", e)
    s = call("GET", "/api/llm")
    print("chat finished after", round(time.perf_counter() - t0, 1), "s; bench running:", s["benchmark"]["running"])
    while s["benchmark"]["running"] or s["busy"]:
        time.sleep(1)
        s = call("GET", "/api/llm")
    for m, r in s["benchmark"]["results"].items():
        print(m, {k: r.get(k) for k in ("ok", "tokens_per_sec", "first_token_ms", "load_s", "error")})
    print("warnings:", s["benchmark"]["warnings"])
    print("profile benchmarks:", [(m["id"], (m["benchmark"] or {}).get("tokens_per_sec")) for m in s["models"]])
    print("loaded now:", loaded(), "active:", s["active"])


asyncio.run(main())
