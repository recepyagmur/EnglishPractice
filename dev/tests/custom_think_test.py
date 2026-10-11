"""Compare custom-scenario structuring with and without the model's thinking mode."""
import asyncio
import os
import time

os.environ["OLLAMA_HOST"] = "127.0.0.1:11635"
os.environ["EP_DATA_DIR"] = os.path.join(os.path.dirname(__file__), "testdata")
from backend import ollama_client, scenarios  # noqa: E402
from backend.settings_store import get_settings  # noqa: E402

CASES = [
    "Komşumla gece geç saatteki gürültü hakkında konuşuyorum",
    "Patronumdan maaş zammı istiyorum",
    "Kiraladığım arabanın lastiği patladı, kiralama şirketini arıyorum",
]


async def run(desc, think):
    t = time.perf_counter()
    raw = await ollama_client.chat_json(
        get_settings()["llm_model"],
        [{"role": "user", "content": scenarios.CUSTOM_PROMPT.format(description=desc)}],
        scenarios.CUSTOM_SCHEMA, think=think, options={"temperature": 0.3},
    )
    ms = (time.perf_counter() - t) * 1000
    print(f"  think={think} {ms:5.0f} ms | AI: {raw['role']} | learner: {raw['learner_role']} | tasks: {[x['en'] for x in raw['tasks']]}")


async def main():
    for d in CASES:
        print(d)
        await run(d, False)
        await run(d, True)


asyncio.run(main())
