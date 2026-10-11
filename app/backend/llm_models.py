"""The chat LLM on this computer: which model is active, switching models, downloads,
speed tests and removal (settings page "Modeller" + the model picker above the chat).

Every LLM call of the app asks `current()` for its model: the session model picked
above the chat (kept in memory only) or this computer's default (machine profile).

VRAM: an 8 GB card holds one 8B model next to Whisper, never two. So before a model
is loaded every other loaded model is unloaded (keep_alive 0). While a model is being
loaded or speed-tested, LLM requests wait (`wait_idle()`, used by chat_priority) and
background corrections pause.
"""

import asyncio
import logging
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path

from setup import benchmark, hardware, installer, ollama_models

from . import machine, ollama_client
from .config import OLLAMA_MODELS_DIR, ROOT_DIR, ollama_url
from .ollama_client import OllamaError
from .settings_store import get_settings

log = logging.getLogger("app")

CATALOG = installer.CATALOG
CATALOG_BY_ID = {m["id"]: m for m in CATALOG["models"]}
TRANSLATION_MODEL = CATALOG["translation_model"]["id"]

PULL_STATUS = (  # Ollama's /api/pull status → what the learner sees
    ("pulling manifest", "Model bilgisi alınıyor…"),
    ("pulling", "İndiriliyor…"),
    ("verifying", "Doğrulanıyor…"),
    ("writing", "Kaydediliyor…"),
    ("removing", "Temizleniyor…"),
    ("success", "Tamamlandı ✓"),
)


class ModelError(Exception):
    """A request that cannot be done (user-facing Turkish message)."""


def default_model() -> str:
    return get_settings()["llm_model"]


def display_name(model: str) -> str:
    if model == TRANSLATION_MODEL:
        return CATALOG["translation_model"]["name"]
    return CATALOG_BY_ID.get(model, {}).get("name", model)


class ModelManager:
    def __init__(self) -> None:
        self.override: str | None = None   # session model chosen above the chat
        self.busy: str | None = None       # None | "loading" | "benchmark"
        self.busy_model: str | None = None
        self.load_error: str | None = None
        self.pull: dict | None = None
        self.bench: dict | None = None
        self._lock = asyncio.Lock()
        self._idle = asyncio.Event()
        self._idle.set()
        self._pending = 0
        self._tasks: set[asyncio.Task] = set()
        self._pull_task: asyncio.Task | None = None
        self._hardware: dict | None = None
        self._sizes: dict[str, int | None] = {}

    # ------------------------------------------------------------ active model

    def current(self) -> str:
        return self.override or default_model()

    async def wait_idle(self) -> None:
        await self._idle.wait()

    def wait_message(self) -> str | None:
        """Why an LLM request would wait right now (None: it would not)."""
        if self._idle.is_set():
            return None
        if self.busy == "benchmark":
            return "Hız testi sürüyor, bitince cevap verilecek…"
        return "Model hazırlanıyor…"

    def _run(self, coro) -> asyncio.Task:
        """Start an exclusive job; LLM requests wait from now until it is done."""
        self._pending += 1
        self._idle.clear()

        async def job():
            try:
                await coro
            finally:
                self._pending -= 1
                if not self._pending:
                    self._idle.set()

        task = asyncio.create_task(job())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    @asynccontextmanager
    async def _exclusive(self, kind: str, model: str | None):
        from .corrections import worker  # imports this module

        async with self._lock, worker.pause():
            self.busy, self.busy_model = kind, model
            try:
                yield
            finally:
                self.busy = self.busy_model = None

    async def _load(self, model: str) -> None:
        """Unload every other model, then load this one (call inside _exclusive)."""
        self.busy, self.busy_model = "loading", model
        self.load_error = None
        for other in await ollama_client.loaded_models():
            if other != model:
                await ollama_client.unload(other)
        try:
            await ollama_client.load(model)
        except OllamaError as e:
            self.load_error = str(e)
            log.warning("loading %s failed: %s", model, e)

    def activate(self) -> asyncio.Task:
        """Make the current model the one in memory (in the background)."""
        async def run():
            async with self._exclusive("loading", None):
                await self._load(self.current())  # read inside: the choice may change while queued
        return self._run(run())

    @staticmethod
    def _chat_models() -> list[str]:
        # Read from disk, not from Ollama: no await before activate(), so a message sent
        # right after a switch already waits for the new model.
        return [m for m in ollama_models.list_models(OLLAMA_MODELS_DIR) if m != TRANSLATION_MODEL]

    async def set_session_model(self, model: str | None) -> None:
        if model and model not in self._chat_models():
            raise ModelError("Bu model kurulu değil.")
        new = None if model in (None, default_model()) else model
        changed = (new or default_model()) != self.current()
        self.override = new
        if changed:
            self.activate()

    async def set_default(self, model: str) -> None:
        if model not in self._chat_models():
            raise ModelError("Bu model kurulu değil.")
        before = self.current()
        machine.update_profile({"default_model": model})
        if self.override == model:
            self.override = None
        if self.current() != before:
            self.activate()

    async def remove(self, model: str) -> None:
        if model == default_model():
            raise ModelError("Varsayılan model silinemez. Önce başka bir modeli varsayılan yap.")
        if self.bench and self.bench["running"]:
            raise ModelError("Hız testi sürerken model silinemez.")
        if self.pull and self.pull["running"] and self.pull["model"] == model:
            raise ModelError("Bu model şu an indiriliyor.")
        if model not in await ollama_client.list_models():
            raise ModelError("Bu model kurulu değil.")
        was_current = model == self.current()
        if self.override == model:
            self.override = None
        # A loaded model's files are in use (Windows cannot delete them): unload first.
        await ollama_client.unload(model)
        await ollama_client.delete(model)
        machine.update_profile({"installed_models_seen": await ollama_client.list_models()})
        if was_current:
            self.activate()

    # ------------------------------------------------------------ lists

    async def installed(self) -> list[dict]:
        bench = machine.load_profile().get("benchmarks", {})
        out = []
        for m in await ollama_client.installed_models():
            name = m["name"]
            details = m.get("details") or {}
            out.append({
                "id": name,
                "name": display_name(name),
                "size_bytes": m.get("size", 0),
                "parameter_size": details.get("parameter_size"),
                "quantization": details.get("quantization_level"),
                "translation": name == TRANSLATION_MODEL,
                "benchmark": bench.get(name),
            })
        return out

    async def state(self) -> dict:
        try:
            models, error = await self.installed(), None
        except OllamaError as e:
            models, error = [], str(e)
        return {
            "default": default_model(), "active": self.current(), "override": self.override,
            "busy": self.busy or (None if self._idle.is_set() else "loading"),
            "busy_model": self.busy_model, "load_error": self.load_error,
            "models": models, "ollama_error": error, "pull": self.pull, "benchmark": self.bench,
        }

    def _hardware_info(self) -> dict:
        if self._hardware is None:
            self._hardware = hardware.scan(ROOT_DIR)
        return self._hardware

    async def catalog(self) -> list[dict]:
        """The setup wizard's model cards (same fit badges) for this computer."""
        hw = await asyncio.to_thread(self._hardware_info)
        missing = [m["id"] for m in CATALOG["models"] if m["id"] not in self._sizes]
        if missing:
            # Real sizes from the Ollama registry (catalog numbers are only a fallback).
            async def size(model: str) -> None:
                self._sizes[model] = await asyncio.to_thread(installer.registry_size, model)
            try:
                await asyncio.wait_for(asyncio.gather(*(size(m) for m in missing)), timeout=15)
            except asyncio.TimeoutError:
                pass
        whisper_on_gpu = machine.load_profile().get("whisper_device") == "cuda" and hw.get("accel") == "cuda"
        return await asyncio.to_thread(installer.catalog_for, hw, whisper_on_gpu, self._sizes)

    # ------------------------------------------------------------ download

    def start_pull(self, model: str, copy_from: str | None = None) -> None:
        if self.pull and self.pull["running"]:
            raise ModelError(f"Şu an {self.pull['model']} indiriliyor; bitmesini bekleyin.")
        entry = CATALOG_BY_ID.get(model)
        if entry is None:
            raise ModelError("Bu model katalogda yok.")
        size = self._sizes.get(model) or int(entry["download_gb"] * 1e9)
        free = shutil.disk_usage(OLLAMA_MODELS_DIR).free
        if not copy_from and free < size * 1.1 + 1e9:
            raise ModelError(f"Disk alanı yetersiz: {size / 1e9:.1f} GB gerekiyor, {free / 1e9:.1f} GB boş.")
        if copy_from and not ollama_models.has_model(Path(copy_from), model):
            raise ModelError("Kopyalanacak model bulunamadı.")
        self.pull = {"model": model, "name": display_name(model), "running": True, "done": False,
                     "error": None, "status": "Başlıyor…", "completed": 0, "total": size,
                     "speed": 0.0, "eta": None, "copy": bool(copy_from)}
        self._pull_task = asyncio.create_task(self._pull(model, copy_from))

    async def _pull(self, model: str, copy_from: str | None) -> None:
        p = self.pull
        start, first = time.monotonic(), [None]

        def progress(done: int, total: int) -> None:
            if first[0] is None:
                first[0] = done  # resumed downloads start above zero: not part of the speed
            p["completed"], p["total"] = done, max(total, 1)
            elapsed = max(time.monotonic() - start, 1e-3)
            p["speed"] = (done - first[0]) / elapsed
            p["eta"] = (total - done) / p["speed"] if p["speed"] > 0 else None

        try:
            if copy_from:
                p["status"] = "Bilgisayarındaki kopyadan alınıyor…"
                await asyncio.to_thread(ollama_models.copy_model, model, Path(copy_from), OLLAMA_MODELS_DIR, progress)
            else:
                layers: dict[str, tuple[int, int]] = {}
                async for ev in ollama_client.pull(model):
                    status = ev.get("status", "")
                    p["status"] = next((tr for prefix, tr in PULL_STATUS if status.startswith(prefix)), status)
                    if ev.get("digest") and ev.get("total"):
                        # Layers download side by side: sum them for one overall bar.
                        layers[ev["digest"]] = (ev.get("completed", 0), ev["total"])
                        progress(sum(c for c, _ in layers.values()),
                                 max(sum(t for _, t in layers.values()), p["total"]))
            if model not in await ollama_client.list_models():
                raise OllamaError("İndirme bitti ama model listede görünmüyor.")
            p.update(done=True, status="Tamamlandı ✓", completed=p["total"], eta=None)
            machine.update_profile({"installed_models_seen": await ollama_client.list_models()})
        except asyncio.CancelledError:
            p.update(error="İptal edildi. Tekrar başlatırsan kaldığı yerden devam eder.", status="İptal edildi")
        except (OllamaError, OSError, ValueError) as e:
            p.update(error=str(e)[:400], status="Hata")
        finally:
            p["running"] = False

    def cancel_pull(self) -> None:
        if self.pull and self.pull["running"] and not self.pull["copy"] and self._pull_task:
            self._pull_task.cancel()

    # ------------------------------------------------------------ speed test

    async def start_benchmark(self, models: list[str] | None) -> None:
        if self.bench and self.bench["running"]:
            raise ModelError("Hız testi zaten sürüyor.")
        chat_models = self._chat_models()
        models = [m for m in (models or chat_models) if m in chat_models]
        if not models:
            raise ModelError("Test edilecek kurulu model yok.")
        self.bench = {"running": True, "models": models, "current": None, "results": {}, "warnings": []}
        self._run(self._benchmark(models))

    async def _benchmark(self, models: list[str]) -> None:
        b = self.bench
        try:
            async with self._exclusive("benchmark", models[0]):
                for model in models:
                    b["current"] = self.busy_model = model
                    for loaded in await ollama_client.loaded_models():
                        await ollama_client.unload(loaded)
                    try:
                        # The setup wizard's test: warm-up, then first-token time and tokens/s.
                        r = await asyncio.to_thread(benchmark.run_llm, ollama_url(), model,
                                                    ollama_client.has_thinking(model))
                    except Exception as e:  # report it, go on with the next model
                        r = {"ok": False, "error": str(e)[:300]}
                    b["results"][model] = r
                    if r.get("ok"):
                        profile = machine.load_profile()
                        profile["benchmarks"] = {**profile.get("benchmarks", {}), model: r}
                        machine.save_profile(profile)
                b["current"] = None
                b["warnings"] = benchmark.advice({"llm": b["results"]}, CATALOG["models"])
                await self._load(self.current())  # back to the model the learner uses
        finally:
            b["running"] = False
            b["current"] = None


manager = ModelManager()


def current() -> str:
    """The model every LLM call should use now."""
    return manager.current()
