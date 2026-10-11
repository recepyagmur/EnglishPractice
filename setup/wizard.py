"""Setup wizard (runs in the browser): install, "new computer" and maintenance modes.

Started by Kurulum.bat / kurulum.sh (python -m setup.wizard) or by the launcher when this
computer has no profile yet (wizard.run(mode="new_machine")).
Needs only fastapi + uvicorn; everything else is installed by the wizard itself.
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import backup, machine
from backend.config import (APP_DIR, DB_PATH, IS_WINDOWS, LOCK_PATH, OLLAMA_EXE, OLLAMA_MODELS_DIR, ROOT_DIR, SCRIPTS,
                            script)

from . import hardware, installer as inst, ollama_models

sys.path.insert(0, str(APP_DIR))
from ollama_runtime import http_ok, pick_port, pid_alive  # noqa: E402

UI_DIR = Path(__file__).parent / "wizard_ui"
# The plan of an install in progress: lets a closed / crashed wizard continue where it stopped.
PENDING_PLAN = ROOT_DIR / "config" / "pending_setup.json"
WIZARD_PORTS = (8765, 8766, 8767, 18765)

app = FastAPI(title="English Practice — Kurulum")
state = {"mode": "install", "hardware": None, "sizes": {}, "test": None, "server": None, "launch_app": False}


# ------------------------------------------------------------------ status

def installation_status() -> dict:
    try:
        import fastapi as _f, faster_whisper as _w, kokoro_onnx as _k  # noqa: F401, E401
        import onnxruntime as _o  # noqa: F401  (its DLL loads only here)
        packages = True
    except Exception as e:  # not installed, or installed but a DLL cannot load: the python task (re)installs
        logging.getLogger(__name__).warning("Python paketleri kullanılamıyor: %s", e)
        packages = False
    return {
        "python_packages": packages,
        "ollama": OLLAMA_EXE.exists(),
        "models": ollama_models.list_models(OLLAMA_MODELS_DIR),
        "whisper": sorted(p.name for p in (ROOT_DIR / "models" / "stt").glob("*") if (p / "model.bin").exists())
                   + (["small.en"] if any((ROOT_DIR / "models" / "stt").glob("models--Systran--faster-whisper-small.en")) else []),
        "kokoro": (ROOT_DIR / "models" / "tts" / "kokoro" / "kokoro-v1.0.onnx").exists(),
        "dictionary": (ROOT_DIR / "data" / "dictionary.db").exists(),
        "user_data": DB_PATH.exists(),
    }


def detect_mode() -> str:
    s = installation_status()
    complete = s["python_packages"] and s["ollama"] and s["models"]
    if complete and machine.profile_exists():
        return "maintenance"
    if complete or machine.profile_exists():
        return "new_machine"
    return "install"


def app_running() -> bool:
    try:
        lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return lock.get("machine") == machine.machine_name() and pid_alive(int(lock.get("pid", 0)))


def get_hardware(refresh: bool = False) -> dict:
    if refresh or state["hardware"] is None:
        state["hardware"] = hardware.scan(ROOT_DIR)
    return state["hardware"]


@app.get("/api/state")
def get_state():
    profile = machine.load_profile()
    return {
        "mode": state["mode"],
        "machine_name": machine.machine_name(),
        "root": str(ROOT_DIR),
        "platform": "windows" if IS_WINDOWS else "linux",
        "scripts": SCRIPTS,
        "start_path": str(ROOT_DIR / script("start")),
        "path_problem": inst.path_problem(),
        "disk_free_gb": round(inst.free_disk_gb(), 1),
        "installed": installation_status(),
        "profile": profile,
        "app_running": app_running(),
        "installing": inst.installer.running(),
        "pending_plan": _pending_plan(),
        "settings": _current_voice_settings(),
    }


def _current_voice_settings() -> dict:
    """The learner's current voice choice, so maintenance runs do not reset it."""
    if not DB_PATH.exists():
        return {}
    import sqlite3

    try:
        conn = sqlite3.connect(DB_PATH)
        rows = dict(conn.execute("SELECT key, value FROM settings WHERE key IN ('tts_accent', 'tts_voice')"))
        conn.close()
        return rows
    except sqlite3.Error:
        return {}


def _pending_plan() -> dict | None:
    try:
        data = json.loads(PENDING_PLAN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data["plan"] if data.get("machine") == machine.machine_name() else None


def _install_finished(tasks: list) -> None:
    if not any(t.status == "failed" for t in tasks):
        PENDING_PLAN.unlink(missing_ok=True)


inst.installer.on_finish = _install_finished


@app.get("/api/hardware")
def api_hardware(refresh: bool = False):
    return get_hardware(refresh)


@app.get("/api/catalog")
def api_catalog(whisper_device: str = "cuda"):
    hw = get_hardware()
    if not state["sizes"]:
        # Real sizes from the Ollama registry (the catalog numbers are only a fallback).
        threads = []
        for m in inst.CATALOG["models"] + [inst.CATALOG["translation_model"]]:
            t = threading.Thread(target=lambda mid=m["id"]: state["sizes"].__setitem__(mid, inst.registry_size(mid)))
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=15)
    on_gpu = whisper_device == "cuda" and hw.get("accel") == "cuda"
    return {
        "models": inst.catalog_for(hw, on_gpu, state["sizes"]),
        "translation": {**inst.CATALOG["translation_model"],
                        "size_bytes": state["sizes"].get(inst.CATALOG["translation_model"]["id"])
                        or int(inst.CATALOG["translation_model"]["download_gb"] * 1e9),
                        "installed": inst.CATALOG["translation_model"]["id"] in installation_status()["models"]},
        "whisper": inst.CATALOG["whisper_models"],
        "whisper_recommendation": inst.whisper_recommendation(hw),
        "voices": inst.CATALOG["kokoro"]["voices"],
    }


# ----------------------------------------------------------------- install

class Plan(BaseModel):
    models: list[str] = []
    default_model: str | None = None
    copy_from_system: dict[str, str] = {}   # model → system Ollama models folder
    whisper_model: str = "small.en"
    whisper_device: str = "cuda"
    tts_accent: str = "a"
    tts_voice: str = "af_heart"
    dictionary: bool = True
    translation: bool = False
    shortcut: bool = False


def _ollama_env(profile: dict, hw: dict) -> dict:
    sys.path.insert(0, str(APP_DIR))
    from ollama_runtime import env_for

    return env_for(profile, hw.get("accel"))


def _gpu_names(hw: dict) -> list[str]:
    return [g.get("name") or "" for g in hw.get("gpus") or []]


def build_tasks(plan: Plan) -> list[inst.Task]:
    hw = get_hardware()
    nvidia = hw.get("accel") == "cuda"
    sizes = state["sizes"]
    env = _ollama_env(machine.load_profile(), hw)
    tasks = [inst.task_python_packages(nvidia), inst.task_ollama_runtime(gpu_names=_gpu_names(hw))]
    models = list(dict.fromkeys(plan.models + ([inst.CATALOG["translation_model"]["id"]] if plan.translation else [])))
    for m in models:
        size = sizes.get(m) or int(next((c["download_gb"] for c in inst.CATALOG["models"] if c["id"] == m), 5) * 1e9)
        tasks.append(inst.task_llm(m, size, plan.copy_from_system.get(m), env))
    tasks += [inst.task_whisper(plan.whisper_model), inst.task_kokoro()]
    if plan.dictionary:
        tasks.append(inst.task_dictionary())
    if plan.shortcut:
        tasks.append(inst.task_shortcut())
    tasks.append(task_profile(plan))
    return tasks


def task_profile(plan: Plan) -> inst.Task:
    def run(task: inst.Task):
        hw = get_hardware()
        profile = machine.load_profile()
        installed = ollama_models.list_models(OLLAMA_MODELS_DIR)
        chat_models = [m for m in installed if m != inst.CATALOG["translation_model"]["id"]]
        default = plan.default_model if plan.default_model in installed else profile.get("default_model")
        if default not in installed:
            default = chat_models[0] if chat_models else plan.default_model
        profile.update({
            "machine_name": machine.machine_name(),
            "detected": {k: hw.get(k) for k in ("cpu", "ram_gb", "gpu", "vram_gb", "accel")},
            "default_model": default,
            "installed_models_seen": installed,
            "whisper_model": plan.whisper_model,
            "whisper_device": "cuda" if plan.whisper_device == "cuda" and hw.get("accel") == "cuda" else "cpu",
        })
        profile.setdefault("benchmarks", {})
        profile.setdefault("ollama_env", {})
        machine.save_profile(profile)
        # Voice / accent are personal settings (data/app.db), shared by all computers.
        from backend.db import init_db
        from backend.settings_store import update_settings

        init_db()
        update_settings({"tts_accent": plan.tts_accent, "tts_voice": plan.tts_voice})
    return inst.Task("profile", "Bilgisayar profili ve ayarlar", _run=run)


@app.post("/api/plan")
def plan_summary(plan: Plan):
    """Step 6: what will be downloaded, disk space and a time estimate."""
    tasks = build_tasks(plan)
    status = installation_status()
    rows = []
    for t in tasks:
        already = ((t.id == "python" and status["python_packages"]) or (t.id == "ollama" and status["ollama"])
                   or (t.id.startswith("llm:") and t.id[4:] in status["models"])
                   or (t.id.startswith("whisper:") and t.id[8:] in status["whisper"])
                   or (t.id == "kokoro" and status["kokoro"]) or (t.id == "dictionary" and status["dictionary"]))
        rows.append({"id": t.id, "title": t.title, "size": 0 if already else t.size, "installed": already})
    total = sum(r["size"] for r in rows)
    return {"rows": rows, "total_bytes": total, "disk_free_gb": round(inst.free_disk_gb(), 1),
            # Disk need: downloads + unpacked Ollama/packages (~1.5x for zips) + headroom.
            "disk_needed_gb": round(total * 1.3 / 1e9 + 1, 1),
            "minutes_estimate": round(total / (8e6 * 60)) + (2 if total else 0)}  # ~8 MB/s, + unpacking


@app.post("/api/install")
def start_install(plan: Plan):
    if app_running():
        raise HTTPException(409, "Uygulama açık. Önce uygulamayı kapatın (konsol penceresinde Ctrl+C).")
    if DB_PATH.exists():
        backup.backup_now("pre-setup")
    PENDING_PLAN.parent.mkdir(parents=True, exist_ok=True)
    PENDING_PLAN.write_text(json.dumps({"machine": machine.machine_name(), "plan": plan.model_dump()},
                                       ensure_ascii=False), encoding="utf-8")
    inst.installer.start(build_tasks(plan))
    return {"ok": True}


@app.get("/api/install/status")
def install_status():
    return {"running": inst.installer.running(), "tasks": [t.public() for t in inst.installer.tasks]}


@app.post("/api/install/retry")
def install_retry():
    inst.installer.retry_failed()
    return {"ok": True}


# -------------------------------------------------------------------- test

def _run_tests(models: list[str], whisper_model: str, whisper_device: str, accent: str, voice: str) -> None:
    from . import benchmark

    t = state["test"]
    profile = machine.load_profile()
    env = _ollama_env(profile, get_hardware())
    thinking = {c["id"]: c["thinking_mode"] for c in inst.CATALOG["models"]}
    hw = get_hardware()
    try:
        for model in models:
            t["current"] = f"Dil modeli: {model}"
            try:
                ollama = inst.installer.ensure_ollama(env)
                t["llm"][model] = benchmark.run_llm(ollama.url, model, thinking.get(model, True))
            except Exception as e:
                if hw.get("accel") == "vulkan" and env.get("OLLAMA_VULKAN") != "0":
                    # Integrated GPU trouble: retry on the CPU and remember it for this computer.
                    inst.installer.stop_ollama()
                    env["OLLAMA_VULKAN"] = "0"
                    t["notes"].append("Vulkan ile çalışmadı; işlemci modu (OLLAMA_VULKAN=0) kullanılıyor.")
                    try:
                        ollama = inst.installer.ensure_ollama(env)
                        t["llm"][model] = benchmark.run_llm(ollama.url, model, thinking.get(model, True))
                        continue
                    except Exception as e2:
                        e = e2
                t["llm"][model] = {"ok": False, "error": str(e)}
        inst.installer.stop_ollama()

        t["current"] = "Konuşma tanıma (Whisper)"
        try:
            t["whisper"] = benchmark.run_whisper(whisper_model, whisper_device)
        except Exception as e:
            t["whisper"] = {"ok": False, "error": str(e)}
        t["current"] = "Ses (Kokoro)"
        try:
            t["kokoro"], state["sample_wav"] = benchmark.run_kokoro(accent, voice)
        except Exception as e:
            t["kokoro"] = {"ok": False, "error": str(e)}

        catalog = inst.CATALOG["models"]
        t["warnings"] = t["notes"] + benchmark.advice(t, catalog)
        t["suggested_default"] = benchmark.best_default(t, catalog, profile.get("default_model"))
        profile = machine.load_profile()
        profile["benchmarks"] = {**profile.get("benchmarks", {}),
                                 **{m: r for m, r in t["llm"].items() if r.get("ok")}}
        if env:
            profile["ollama_env"] = env
        machine.save_profile(profile)
    finally:
        t["running"] = False
        t["current"] = ""


class TestRequest(BaseModel):
    models: list[str] | None = None


@app.post("/api/test")
def start_test(body: TestRequest):
    if state["test"] and state["test"]["running"]:
        raise HTTPException(409, "Test zaten sürüyor.")
    profile = machine.load_profile()
    from backend.db import init_db
    from backend.settings_store import get_settings

    init_db()
    settings = get_settings()
    translation = inst.CATALOG["translation_model"]["id"]
    models = body.models or [m for m in ollama_models.list_models(OLLAMA_MODELS_DIR) if m != translation]
    state["test"] = {"running": True, "current": "", "llm": {}, "whisper": None, "kokoro": None,
                     "notes": [], "warnings": [], "suggested_default": None}
    threading.Thread(target=_run_tests, daemon=True, args=(
        models, profile.get("whisper_model", "small.en"), profile.get("whisper_device", "cpu"),
        settings["tts_accent"], settings["tts_voice"])).start()
    return {"ok": True}


@app.get("/api/test/status")
def test_status():
    return state["test"] or {"running": False}


@app.get("/api/test/sample.wav")
def test_sample():
    wav = state.get("sample_wav")
    if not wav:
        raise HTTPException(404, "Önce testi çalıştırın.")
    return Response(wav, media_type="audio/wav")


class DefaultRequest(BaseModel):
    model: str


@app.post("/api/profile/default")
def set_default(body: DefaultRequest):
    if not ollama_models.has_model(OLLAMA_MODELS_DIR, body.model):
        raise HTTPException(404, "Bu model kurulu değil.")
    machine.update_profile({"default_model": body.model})
    return machine.load_profile()


# ------------------------------------------------------------- maintenance

def _maintenance_backup() -> None:
    if DB_PATH.exists():
        backup.backup_now("pre-maintenance")


class ModelRequest(BaseModel):
    model: str


@app.post("/api/maintenance/remove-model")
def remove_model(body: ModelRequest):
    if app_running():
        raise HTTPException(409, "Önce uygulamayı kapatın.")
    _maintenance_backup()
    ollama = inst.installer.ensure_ollama(machine.load_profile().get("ollama_env"))
    try:
        req = urllib.request.Request(f"{ollama.url}/api/delete", method="DELETE",
                                     data=json.dumps({"model": body.model}).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=60).read()
    finally:
        inst.installer.stop_ollama()
    profile = machine.load_profile()
    installed = ollama_models.list_models(OLLAMA_MODELS_DIR)
    if profile.get("default_model") == body.model:
        profile["default_model"] = next((m for m in installed if m != inst.CATALOG["translation_model"]["id"]), None)
    profile["installed_models_seen"] = installed
    machine.save_profile(profile)
    return {"ok": True, "profile": profile}


@app.post("/api/maintenance/repair")
def repair():
    """Re-check everything; missing or corrupt files are downloaded again."""
    if app_running():
        raise HTTPException(409, "Önce uygulamayı kapatın.")
    _maintenance_backup()
    profile = machine.load_profile()
    # Every task skips what is present and complete, so this only fetches what is missing.
    # The dictionary is included: it is a recommended component and cheap to check.
    inst.installer.start([
        inst.task_python_packages(get_hardware().get("accel") == "cuda"),
        inst.task_ollama_runtime(gpu_names=_gpu_names(get_hardware())),
        inst.task_whisper(profile.get("whisper_model", "small.en")), inst.task_kokoro(verify=True),
        inst.task_dictionary(),
    ])
    return {"ok": True}


@app.post("/api/maintenance/update")
def update():
    """Newest Ollama + the app's pinned Python packages."""
    if app_running():
        raise HTTPException(409, "Önce uygulamayı kapatın.")
    _maintenance_backup()
    inst.installer.start([inst.task_python_packages(get_hardware().get("accel") == "cuda"),
                          inst.task_ollama_runtime(force=True, gpu_names=_gpu_names(get_hardware()))])
    return {"ok": True}


@app.post("/api/maintenance/rescan")
def rescan():
    hw = get_hardware(refresh=True)
    machine.update_profile({"detected": {k: hw.get(k) for k in ("cpu", "ram_gb", "gpu", "vram_gb", "accel")}})
    return hw


# ------------------------------------------------------------------ finish

@app.post("/api/finish")
def finish(start_app: bool = True):
    """Close the wizard; optionally start the app (Baslat.bat)."""
    inst.cleanup_downloads()
    state["launch_app"] = start_app
    if start_app and state["mode"] != "new_machine" and IS_WINDOWS:
        # In "new computer" mode the launcher is waiting and continues by itself.
        # Linux: main() starts the app in this terminal once the wizard has stopped.
        subprocess.Popen(["cmd", "/c", "start", "English Practice", str(ROOT_DIR / "Baslat.bat")],
                         cwd=ROOT_DIR, creationflags=subprocess.CREATE_NEW_CONSOLE)
    threading.Timer(0.5, lambda: setattr(state["server"], "should_exit", True)).start()
    return {"ok": True}


SHARED_FILES = {"model-cards.js": "text/javascript", "model-cards.css": "text/css"}


@app.get("/shared/{name}")
def shared_file(name: str):
    """UI components shared with the app (the same model cards and badges)."""
    if name not in SHARED_FILES:
        raise HTTPException(404)
    return Response((APP_DIR / "frontend" / name).read_bytes(), media_type=SHARED_FILES[name])


@app.middleware("http")
async def no_cache(request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/", StaticFiles(directory=UI_DIR, html=True), name="ui")


# -------------------------------------------------------------------- run

def run(mode: str | None = None, open_browser: bool = True) -> None:
    import uvicorn

    state["mode"] = mode or detect_mode()
    port = pick_port(WIZARD_PORTS)
    url = f"http://localhost:{port}"
    print(f"Kurulum sihirbazı: {url}  (tarayıcıda açılıyor; kapatmak için Ctrl+C)", flush=True)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    state["server"] = server
    if open_browser:
        def opener():
            for _ in range(60):
                if http_ok(f"{url}/api/state", timeout=1):
                    webbrowser.open(url)
                    return
                time.sleep(0.3)
        threading.Thread(target=opener, daemon=True).start()
    try:
        server.run()
    finally:
        inst.installer.stop_ollama()


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["install", "new_machine", "maintenance"])
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    run(args.mode, open_browser=not args.no_browser)
    if not IS_WINDOWS and state.get("launch_app") and state["mode"] != "new_machine":
        # "▶ Uygulamayı başlat" on Linux: the app takes over this terminal (Ctrl+C closes it), as baslat.sh does.
        launcher = [sys.executable, str(APP_DIR / "launcher.py")] + (["--no-browser"] if args.no_browser else [])
        os.chdir(ROOT_DIR)
        os.execv(sys.executable, launcher)


if __name__ == "__main__":
    main()
