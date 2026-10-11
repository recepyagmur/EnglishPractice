import json
from typing import AsyncIterator

import httpx

from .config import OLLAMA_KEEP_ALIVE, OLLAMA_NUM_CTX, SETUP_DIR, ollama_url, script


class OllamaError(Exception):
    """Raised with a user-facing (Turkish) message when Ollama is unusable."""


# Long read timeout: on a laptop without a GPU, loading the model plus reading a long prompt can take minutes.
_client = httpx.AsyncClient(base_url=ollama_url(), timeout=httpx.Timeout(600.0, connect=3.0))


async def close() -> None:
    await _client.aclose()


async def installed_models() -> list[dict]:
    """Installed models as Ollama reports them (name, size, details…)."""
    try:
        resp = await _client.get("/api/tags", timeout=3.0)
        resp.raise_for_status()
    except httpx.ConnectError as e:
        raise OllamaError(
            f"Ollama'ya bağlanılamadı. Uygulamayı {script('start')} ile yeniden başlatın (ayrıntılar: logs/ollama.log)."
        ) from e
    except httpx.HTTPError as e:
        raise OllamaError(f"Ollama hatası: {e}") from e
    return sorted(resp.json().get("models", []), key=lambda m: m["name"])


async def list_models() -> list[str]:
    return [m["name"] for m in await installed_models()]


async def loaded_models() -> list[str]:
    """Models currently in (V)RAM."""
    try:
        resp = await _client.get("/api/ps", timeout=3.0)
        resp.raise_for_status()
    except httpx.HTTPError:
        return []
    return [m["name"] for m in resp.json().get("models", [])]


async def load(model: str) -> None:
    """Load the model into VRAM (raises OllamaError if it cannot be loaded)."""
    try:
        # Same num_ctx as the chat requests: otherwise Ollama loads the model a second time on
        # the first message (newer Ollama versions pick a different default context size).
        resp = await _client.post("/api/generate", json={"model": model, "keep_alive": OLLAMA_KEEP_ALIVE,
                                                         "options": {"num_ctx": OLLAMA_NUM_CTX}})
    except httpx.ConnectError as e:
        raise OllamaError("Ollama'ya bağlanılamadı.") from e
    except httpx.ReadTimeout as e:
        raise OllamaError("Model yüklenirken zaman aşımı oldu.") from e
    if resp.status_code != 200:
        raise OllamaError(_explain_error(resp.status_code, resp.text, model))


async def preload(model: str) -> None:
    """Load the model ahead of the first message. Errors are ignored."""
    try:
        await load(model)
    except OllamaError:
        pass


async def unload(model: str) -> None:
    """Free the model's (V)RAM now (keep_alive 0)."""
    try:
        await _client.post("/api/generate", json={"model": model, "keep_alive": 0})
    except httpx.HTTPError:
        pass


async def delete(model: str) -> None:
    try:
        resp = await _client.request("DELETE", "/api/delete", json={"model": model})
    except httpx.HTTPError as e:
        raise OllamaError(f"Ollama hatası: {e}") from e
    if resp.status_code != 200:
        raise OllamaError(_explain_error(resp.status_code, resp.text, model))


async def pull(model: str) -> AsyncIterator[dict]:
    """Download a model; yields Ollama's progress events ({status, digest, total, completed})."""
    try:
        async with _client.stream("POST", "/api/pull", json={"model": model, "stream": True},
                                  timeout=httpx.Timeout(None, connect=3.0)) as resp:
            if resp.status_code != 200:
                body = (await resp.aread()).decode(errors="replace")
                raise OllamaError(f"İndirme başlatılamadı ({resp.status_code}): {body[:300]}")
            async for line in resp.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if data.get("error"):
                    raise OllamaError(f"İndirme hatası: {data['error']}")
                yield data
    except httpx.ConnectError as e:
        raise OllamaError("Ollama'ya bağlanılamadı.") from e
    except httpx.HTTPError as e:
        raise OllamaError(f"İndirme kesildi: {e}") from e


def _no_thinking_models() -> set[str]:
    """Catalog models without a thinking mode: they must not get a `think` field."""
    try:
        catalog = json.loads((SETUP_DIR / "catalog.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    entries = catalog.get("models", []) + [catalog.get("translation_model", {})]
    return {m["id"] for m in entries if m and m.get("thinking_mode") is False}


_NO_THINKING = _no_thinking_models()


def has_thinking(model: str) -> bool:
    """Whether requests for this model carry think=false (unknown models: yes)."""
    return model not in _NO_THINKING


def _payload(model: str, messages: list[dict], stream: bool, **extra) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"num_ctx": OLLAMA_NUM_CTX, **extra.pop("options", {})},
        **extra,
    }
    if has_thinking(model):
        # Thinking models (e.g. qwen3) add seconds of latency; we never want it.
        payload["think"] = False
    return payload


async def complete(model: str, prompt: str, **extra) -> str:
    """One non-streaming answer as plain text."""
    payload = _payload(model, [{"role": "user", "content": prompt}], stream=False, **extra)
    try:
        resp = await _client.post("/api/chat", json=payload)
    except httpx.ConnectError as e:
        raise OllamaError("Ollama'ya bağlanılamadı.") from e
    except httpx.ReadTimeout as e:
        raise OllamaError("Ollama zaman aşımına uğradı.") from e
    if resp.status_code != 200:
        raise OllamaError(_explain_error(resp.status_code, resp.text, model))
    return resp.json().get("message", {}).get("content", "").strip()


def _explain_error(status: int, body: str, model: str) -> str:
    if status == 404 or "not found" in body.lower():
        return f"'{model}' modeli bu bilgisayarda kurulu değil. Ayarlar'dan kurulu bir model seçin."
    return f"Ollama hatası ({status}): {body[:300]}"


async def chat_stream(model: str, messages: list[dict], **extra) -> AsyncIterator[str]:
    """Yield content chunks of the assistant reply as they are generated."""
    payload = _payload(model, messages, stream=True, **extra)
    try:
        async with _client.stream("POST", "/api/chat", json=payload) as resp:
            if resp.status_code != 200:
                body = (await resp.aread()).decode(errors="replace")
                raise OllamaError(_explain_error(resp.status_code, body, model))
            async for line in resp.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if "error" in data:
                    raise OllamaError(f"Ollama hatası: {data['error']}")
                chunk = data.get("message", {}).get("content", "")
                if chunk:
                    yield chunk
                if data.get("done"):
                    break
    except httpx.ConnectError as e:
        raise OllamaError(
            f"Ollama'ya bağlanılamadı. Uygulamayı {script('start')} ile yeniden başlatın."
        ) from e
    except httpx.ReadTimeout as e:
        raise OllamaError("Ollama zaman aşımına uğradı (model yükleniyor olabilir, tekrar deneyin).") from e


async def chat_json(model: str, messages: list[dict], schema: dict, **extra) -> dict:
    """Non-streaming call that forces structured JSON output matching `schema`."""
    payload = _payload(model, messages, stream=False, format=schema, **extra)
    try:
        resp = await _client.post("/api/chat", json=payload)
    except httpx.ConnectError as e:
        raise OllamaError("Ollama'ya bağlanılamadı.") from e
    except httpx.ReadTimeout as e:
        raise OllamaError("Ollama zaman aşımına uğradı.") from e
    if resp.status_code != 200:
        raise OllamaError(_explain_error(resp.status_code, resp.text, model))
    content = resp.json().get("message", {}).get("content", "")
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise OllamaError("Model geçerli JSON döndürmedi.") from e
