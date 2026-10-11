"""Phase 15: compare models as a Turkish-speaking English teacher.

Starts the bundled Ollama on a free port (the app must be closed or it simply uses
another port), pulls missing models, asks every model the same teacher questions
and writes a Markdown report (answers side by side, speed, thinking leaks).

    runtime\\python\\python.exe dev\\tests\\teacher_model_compare.py <report.md> [model ...]
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "app"))

import httpx  # noqa: E402

from ollama_runtime import OllamaProcess  # noqa: E402

MODELS = sys.argv[2:] or ["qwen3:8b", "gemma4:e4b"]

SYSTEM = (
    "You are a patient English teacher for a Turkish adult who works in an office (level A2-B1). "
    "Always answer in natural, correct Turkish. Keep English examples in English and put each one "
    "on its own line starting with '- '. Be short: at most 120 words. Structure: one or two "
    "sentences of explanation, then 2-3 examples (work life where possible), then one short tip. "
    "Never invent grammar rules; if a sentence is correct, say so."
)

QUESTIONS = [
    "Present perfect ile past simple arasındaki fark ne? İş hayatından örnek ver.",
    "'I am working here since 2020' cümlesinde hata var mı? Varsa neden yanlış?",
    "'used to' ile 'be used to' farkını açıklar mısın?",
    "Müdürüme toplantıyı yarına ertelemek istediğimi kibarca nasıl yazarım?",
    "make ile do ne zaman kullanılır? Karıştırıyorum.",
    "'She doesn't like meetings' doğru mu?",
    "Deadline'ı kaçırdım, bunu müşteriye nasıl söylerim?",
    "Son derslerde en çok şu hataları yaptım: article (a/an/the) 12 kez, zaman (tense) 8 kez, "
    "edat (preposition) 5 kez. Neye ve nasıl çalışmalıyım?",
]


def pull(url: str, model: str) -> None:
    tags = httpx.get(f"{url}/api/tags").json().get("models", [])
    if any(m["name"] == model for m in tags):
        return
    print(f"pulling {model} ...", flush=True)
    last = 0.0
    with httpx.stream("POST", f"{url}/api/pull", json={"model": model, "stream": True},
                      timeout=httpx.Timeout(None, connect=5)) as resp:
        for line in resp.iter_lines():
            if not line:
                continue
            d = json.loads(line)
            if d.get("error"):
                raise SystemExit(f"pull error: {d['error']}")
            if d.get("total") and time.monotonic() - last > 15:
                last = time.monotonic()
                print(f"  {d.get('status')} {d.get('completed', 0) / 1e9:.2f}/{d['total'] / 1e9:.2f} GB", flush=True)
    print("pulled", model, flush=True)


def ask(url: str, model: str, question: str) -> dict:
    payload = {
        "model": model, "stream": False, "think": False, "keep_alive": "5m",
        "options": {"num_ctx": 4096, "temperature": 0.4},
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}],
    }
    t0 = time.perf_counter()
    resp = httpx.post(f"{url}/api/chat", json=payload, timeout=300)
    wall = time.perf_counter() - t0
    if resp.status_code != 200:
        return {"error": f"{resp.status_code}: {resp.text[:300]}", "wall": wall}
    d = resp.json()
    msg = d.get("message", {})
    content = msg.get("content", "")
    return {
        "content": content.strip(),
        "thinking_len": len(msg.get("thinking") or ""),
        "think_leak": "<think>" in content or "</think>" in content,
        "wall": wall,
        "load_s": d.get("load_duration", 0) / 1e9,
        "tok_s": d.get("eval_count", 0) / max(d.get("eval_duration", 1) / 1e9, 1e-9),
        "first_ms": (d.get("prompt_eval_duration", 0) + d.get("load_duration", 0)) / 1e6,
    }


def vram(url: str) -> str:
    ps = httpx.get(f"{url}/api/ps").json().get("models", [])
    return ", ".join(f"{m['name']} {m.get('size_vram', 0) / 1e9:.1f} GB VRAM / {m.get('size', 0) / 1e9:.1f} GB" for m in ps)


def main() -> None:
    out = sys.argv[1]
    ollama = OllamaProcess(log_name="ollama-compare.log")
    if not ollama.start():
        raise SystemExit("Ollama did not start")
    print("ollama on", ollama.url, flush=True)
    try:
        for m in MODELS:
            pull(ollama.url, m)
        results = {}
        for m in MODELS:
            for other in MODELS:  # only one model in VRAM at a time (8 GB card)
                httpx.post(f"{ollama.url}/api/generate", json={"model": other, "keep_alive": 0})
            results[m] = []
            for q in QUESTIONS:
                r = ask(ollama.url, m, q)
                results[m].append(r)
                print(f"{m}: {r.get('wall', 0):.1f}s {r.get('tok_s', 0):.0f} tok/s leak={r.get('think_leak')}", flush=True)
            results[m + "#vram"] = vram(ollama.url)
    finally:
        ollama.stop()

    lines = ["# Türkçe öğretmen — model karşılaştırması", "", f"Sistem talimatı: `{SYSTEM}`", ""]
    lines += ["| Model | Ort. hız (token/sn) | Ort. süre (sn) | İlk yükleme (sn) | Bellek | Düşünce sızıntısı |",
              "|---|---|---|---|---|---|"]
    for m in MODELS:
        rs = [r for r in results[m] if "error" not in r]
        if not rs:
            lines.append(f"| {m} | hata | | | | |")
            continue
        lines.append(f"| {m} | {sum(r['tok_s'] for r in rs) / len(rs):.0f} | {sum(r['wall'] for r in rs) / len(rs):.1f} | "
                     f"{rs[0]['load_s']:.1f} | {results[m + '#vram']} | "
                     f"{sum(r['think_leak'] or r['thinking_len'] > 0 for r in rs)}/{len(rs)} |")
    for i, q in enumerate(QUESTIONS, 1):
        lines += ["", "---", "", f"## {i}. {q}", ""]
        for m in MODELS:
            r = results[m][i - 1]
            lines += [f"### {m}  ({r.get('wall', 0):.1f} sn)", ""]
            lines += [r.get("error") or r["content"], ""]
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("report:", out)


main()
