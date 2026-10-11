"""Run analyze() on typical Turkish-learner sentences against the running Ollama."""
import asyncio
import json
import os
import time

os.environ["OLLAMA_HOST"] = "127.0.0.1:11635"
from backend import corrections  # noqa: E402

CASES = [
    ("voice", "Yesterday I go to the market and I buy some apples for my family"),
    ("voice", "My sister is doctor and he works in hospital"),
    ("voice", "I am agree with you about this topic"),
    ("voice", "Where you are going this weekend"),
    ("voice", "I have been to London last year"),
    ("voice", "I enjoy to play football with my friends"),
    ("voice", "I very happy because I passed the exam"),
    ("voice", "I went to the cinema with my friends last night and we watched a great movie"),
    ("text", "She dont like coffee, she prefer tea."),
    ("text", "I am living in Istanbul since five years."),
]


async def main():
    for source, text in CASES:
        t = time.perf_counter()
        r = await corrections.analyze(text, source)
        ms = (time.perf_counter() - t) * 1000
        print(f"\n[{ms:5.0f} ms] {text}")
        print(f"   → {r['corrected']}")
        for e in r["errors"]:
            print(f"     · {e['category']:<24} {e['wrong']!r} → {e['right']!r}: {e['explanation']}")
        if r["more_natural"]:
            print(f"     ~ {r['more_natural']}")


asyncio.run(main())
