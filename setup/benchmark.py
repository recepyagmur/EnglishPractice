"""Setup step 8: a short real-world test of the installed components.

LLMs: first-token time and tokens/second (Ollama's own counters). Whisper: the
sample recording. Kokoro: a sample sentence. If a model cannot run with Vulkan
(integrated GPUs), it is retried with OLLAMA_VULKAN=0 and that is remembered in
the computer profile.
"""

import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from backend.config import ROOT_DIR

SAMPLE_WAV = ROOT_DIR / "setup" / "assets" / "sample.wav"
SAMPLE_SENTENCE = "Hi! I'm your English practice partner. Shall we talk about your day?"
PROMPT = ("You are an English teacher. In two short sentences of simple English, tell a learner how to "
          "use the past simple. Then give one example sentence with its Turkish translation.")
SLOW_TOKENS_PER_SEC = 8   # below this, conversations feel sluggish
MIN_TOKENS_PER_SEC_OK = 8  # = installer.TARGET_TOKENS_PER_SEC: fast enough to be the default


def _post(url: str, body: dict, timeout: float = 600):
    req = urllib.request.Request(url, method="POST", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


def run_llm(ollama_url: str, model: str, thinking: bool) -> dict:
    t0 = time.perf_counter()
    # Same num_ctx as the chat below: a different context size would make Ollama load the model again.
    with _post(f"{ollama_url}/api/generate", {"model": model, "keep_alive": "5m", "options": {"num_ctx": 4096}}) as r:
        r.read()
    # Warm-up: right after an install the first GPU computation compiles kernels (~15 s once,
    # then cached by the driver). Doing it here also spares the learner's first message.
    with _post(f"{ollama_url}/api/generate", {"model": model, "prompt": "Hi", "stream": False,
                                              "options": {"num_ctx": 4096, "num_predict": 1},
                                              **({"think": False} if thinking else {})}) as r:
        r.read()
    load_s = time.perf_counter() - t0

    body = {"model": model, "messages": [{"role": "user", "content": PROMPT}], "stream": True,
            "options": {"num_ctx": 4096, "temperature": 0.3, "num_predict": 160}}
    if thinking:
        body["think"] = False
    t0 = time.perf_counter()
    first_token = None
    text, final = "", {}
    with _post(f"{ollama_url}/api/chat", body) as r:
        for line in r:
            ev = json.loads(line)
            if ev.get("error"):
                raise RuntimeError(ev["error"])
            chunk = ev.get("message", {}).get("content", "")
            if chunk and first_token is None:
                first_token = time.perf_counter() - t0
            text += chunk
            if ev.get("done"):
                final = ev
    tps = final.get("eval_count", 0) / (final.get("eval_duration", 1) / 1e9) if final.get("eval_duration") else 0
    # Free the VRAM before the next model.
    with _post(f"{ollama_url}/api/generate", {"model": model, "keep_alive": 0}) as r:
        r.read()
    return {"ok": True, "load_s": round(load_s, 1), "first_token_ms": round((first_token or 0) * 1000),
            "tokens_per_sec": round(tps, 1), "sample": text.strip()[:400],
            "measured_at": datetime.now().isoformat(timespec="seconds")}


def run_whisper(model_name: str, device: str) -> dict:
    from backend.stt import SpeechToText

    stt = SpeechToText()
    t0 = time.perf_counter()
    stt.load(model_name, device)
    if stt.state != "ready":
        return {"ok": False, "error": stt.message}
    load_s = time.perf_counter() - t0
    result = stt.transcribe(SAMPLE_WAV.read_bytes())
    result = stt.transcribe(SAMPLE_WAV.read_bytes())  # second run: warm
    return {"ok": True, "device": stt.device, "load_s": round(load_s, 1), "elapsed_ms": result["elapsed_ms"],
            "audio_seconds": result["audio_seconds"], "text": result["text"],
            "gpu_fallback": device == "cuda" and stt.device != "cuda"}


def run_kokoro(accent: str, voice: str) -> tuple[dict, bytes | None]:
    from backend.tts import TextToSpeech

    tts = TextToSpeech()
    tts.load()
    if tts.state != "ready":
        return {"ok": False, "error": tts.message}, None
    t0 = time.perf_counter()
    wav = tts.synthesize(SAMPLE_SENTENCE, accent, voice, 1.0)
    return {"ok": True, "elapsed_ms": round((time.perf_counter() - t0) * 1000)}, wav


def advice(results: dict, catalog: list[dict]) -> list[str]:
    """Plain-language warnings from the measurements."""
    out = []
    llm = results.get("llm", {})
    ok = {m: r for m, r in llm.items() if r.get("ok")}
    for model, r in ok.items():
        if r["tokens_per_sec"] < SLOW_TOKENS_PER_SEC:
            # Only models verified to be correct are suggested (a fast but wrong teacher is no help).
            faster = [c["id"] for c in sorted(catalog, key=lambda c: -c["speed"])
                      if c["id"] != model and c.get("verified") and c["speed"] > _speed(catalog, model)]
            hint = f" Daha hızlı bir model önerilir: {faster[0]}." if faster else ""
            out.append(f"{model} bu bilgisayarda yavaş ({r['tokens_per_sec']} token/sn).{hint}")
    for model, r in llm.items():
        if not r.get("ok"):
            out.append(f"{model} çalıştırılamadı: {r.get('error', '')[:120]}")
    w = results.get("whisper") or {}
    if w.get("gpu_fallback"):
        out.append("Whisper ekran kartında çalışamadı, işlemcide çalışıyor (biraz daha yavaş).")
    if w.get("ok") and w["elapsed_ms"] > 2500:
        out.append(f"Konuşma tanıma yavaş ({w['elapsed_ms']} ms). Ayarlar'dan 'base.en' modelini deneyebilirsin.")
    return out


def _speed(catalog: list[dict], model: str) -> int:
    return next((c["speed"] for c in catalog if c["id"] == model), 0)


def best_default(results: dict, catalog: list[dict], current: str | None) -> str | None:
    """Keep the current default if it is fast enough, else the best-quality model that is.
    Verified models (correct Turkish and corrections) come before unverified ones."""
    ok = {m: r for m, r in results.get("llm", {}).items() if r.get("ok")}
    if current in ok and ok[current]["tokens_per_sec"] >= MIN_TOKENS_PER_SEC_OK:
        return current
    quality = {c["id"]: c["quality"] for c in catalog}
    verified = {c["id"] for c in catalog if c.get("verified")}
    fast = [m for m, r in ok.items() if r["tokens_per_sec"] >= MIN_TOKENS_PER_SEC_OK]
    pool = [m for m in fast if m in verified] or [m for m in ok if m in verified] or fast or list(ok)
    if not pool:
        return current
    if any(m in fast for m in pool):
        return max(pool, key=lambda m: (quality.get(m, 0), ok[m]["tokens_per_sec"]))
    return max(pool, key=lambda m: ok[m]["tokens_per_sec"])  # none is fast enough: the fastest


__all__ = ["run_llm", "run_whisper", "run_kokoro", "advice", "best_default", "Path"]
