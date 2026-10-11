"""Start the app: bundled Ollama (child process) + FastAPI, then open the browser.

Run via Baslat.bat (Windows):  runtime\\python\\python.exe app\\launcher.py [--no-browser]
     or baslat.sh (Linux):      runtime/python/bin/python3 app/launcher.py [--no-browser]
"""

import argparse
import json
import logging
import logging.handlers
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime

from backend import backup, machine, sync
from backend.config import IS_WINDOWS, LOCK_PATH, LOGS_DIR, OLLAMA_EXE, ROOT_DIR, script
from ollama_runtime import OllamaProcess, env_for, http_ok, pick_port, pid_alive, prune_gpu_libs

APP_PORTS = (8000, 8080, 8765, 18000, 28000)

log = logging.getLogger("launcher")


def setup_logging() -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    # Rotated, so the log never grows without limit.
    handler = logging.handlers.RotatingFileHandler(LOGS_DIR / "launcher.log", maxBytes=2_000_000, backupCount=2,
                                                   encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[handler])
    # httpx logs every request at INFO (the status pill asks Ollama every few seconds).
    logging.getLogger("httpx").setLevel(logging.WARNING)


def say(msg: str) -> None:
    log.info(msg)
    try:
        print(msg, flush=True)
    except OSError:  # the terminal is gone (closed window on Linux): the log still has it
        pass


# --------------------------------------------------------------- lock file

def acquire_lock(app_port: int) -> bool:
    """Warn when the folder (e.g. on OneDrive) is already open on another computer."""
    me = machine.machine_name()
    if LOCK_PATH.exists():
        try:
            lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            lock = {}
        other = lock.get("machine")
        if other == me and pid_alive(int(lock.get("pid", 0))):
            url = f"http://localhost:{lock.get('port')}"
            if http_ok(f"{url}/api/health"):
                say(f"Uygulama zaten açık: {url}")
                open_app_window(url)
                return False
        elif other and other != me:
            say(f"\n⚠ Uygulama şu anda '{other}' bilgisayarında açık görünüyor "
                f"(başlangıç: {lock.get('started_at', '?')}).")
            say("  Klasör senkronize ediliyorsa (OneDrive vb.) iki bilgisayarda aynı anda açmak verileri bozabilir.")
            if input("  Yine de devam edilsin mi? [e/H] ").strip().lower() not in ("e", "evet"):
                return False

    LOCK_PATH.write_text(json.dumps({
        "machine": me,
        "pid": os.getpid(),
        "port": app_port,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }), encoding="utf-8")
    return True


def release_lock() -> None:
    try:
        lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        if lock.get("pid") == os.getpid() and lock.get("machine") == machine.machine_name():
            LOCK_PATH.unlink()
    except (OSError, json.JSONDecodeError):
        pass


# -------------------------------------------------------------------- main

def check_installation() -> bool:
    missing = []
    if not OLLAMA_EXE.exists():
        missing.append("Ollama (runtime/ollama)")
    try:
        import fastapi, uvicorn  # noqa: F401, E401
    except ImportError:
        missing.append("Python paketleri")
    if missing:
        say("Kurulum eksik: " + ", ".join(missing))
        say(f"Önce {script('setup')} dosyasını çalıştırın.")
        return False
    return True


def ensure_profile(open_browser: bool = True) -> dict | None:
    """This computer's profile; without one, run the setup wizard in "new computer" mode."""
    if machine.profile_exists():
        return machine.load_profile()
    say(f"'{machine.machine_name()}' bu klasörde ilk kez açılıyor — kurulum sihirbazı açılıyor…")
    from setup import wizard

    wizard.run(mode="new_machine", open_browser=open_browser)
    return machine.load_profile() if machine.profile_exists() else None


def _app_browser() -> str | None:
    """Edge (on every Windows 10/11) or Chrome: they can show a page as an app window.
    Linux: Chrome, Chromium, Edge or Brave from the PATH (all Chromium based: the same --app window)."""
    if not IS_WINDOWS:
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge",
                     "microsoft-edge-stable", "brave-browser"):
            exe = shutil.which(name)
            if exe:
                return exe
        return None
    roots = [os.environ.get(v) for v in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    for rel in (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"):
        for root in filter(None, roots):
            exe = os.path.join(root, rel)
            if os.path.exists(exe):
                return exe
    return None


def open_app_window(url: str) -> None:
    """The app in its own window, like a desktop program (no tabs or address bar); the same page as in a
    browser. Without Edge or Chrome: the default browser."""
    exe = _app_browser()
    if exe:
        args = [exe, f"--app={url}", "--window-size=1280,880"]
        if not IS_WINDOWS:
            args.append("--class=EnglishPractice")  # its own window group / dock icon (the .desktop file)
        try:
            # Linux: its own session, so the browser does not close with the terminal (as on Windows).
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                             **({} if IS_WINDOWS else {"start_new_session": True}))
        except OSError:
            webbrowser.open(url)
            return
        if not IS_WINDOWS:
            return
        # Its own taskbar button and pin (our logo, Baslat.bat) instead of Edge's: app_window.py.
        try:
            import app_window
            app_window.claim_app_windows(f'"{ROOT_DIR / "Baslat.bat"}"',
                                         str(ROOT_DIR / "app" / "frontend" / "icon.ico"))
        except Exception as e:  # cosmetic: the app works without it
            logging.getLogger("launcher").warning("Pencere kimliği ayarlanamadı: %s", e)
        return
    webbrowser.open(url)


def open_browser_when_ready(url: str) -> None:
    for _ in range(120):
        if http_ok(f"{url}/api/health", timeout=1):
            open_app_window(url)
            return
        time.sleep(0.5)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    setup_logging()
    if not IS_WINDOWS:  # closing the terminal: stop like Ctrl+C (send the data, stop Ollama, free the lock)
        signal.signal(signal.SIGHUP, lambda *_: os.kill(os.getpid(), signal.SIGTERM))
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # runs the cleanup below (uvicorn has its own)
    say("English Practice başlatılıyor…")
    if not check_installation():
        return 1
    profile = ensure_profile(open_browser=not args.no_browser)
    if profile is None:
        say(f"Bilgisayar profili oluşturulmadı; uygulama açılmıyor. {script('start')} ile tekrar deneyin.")
        return 1

    app_port = pick_port(APP_PORTS)
    if not acquire_lock(app_port):
        return 0
    if not sync_on_open():
        release_lock()
        return 0

    ollama = OllamaProcess(env=env_for(profile))
    try:
        saved = backup.daily_backup()
        if saved:
            say(f"Günlük yedek alındı: {saved.relative_to(ROOT_DIR) if saved.is_relative_to(ROOT_DIR) else saved}")

        freed = prune_gpu_libs([(profile.get("detected") or {}).get("gpu") or ""])
        if freed:
            say(f"Kullanılmayan AMD ekran kartı kitaplıkları kaldırıldı ({freed / 1e9:.1f} GB yer açıldı).")
        say("Ollama başlatılıyor…")
        if ollama.start():
            say(f"Ollama hazır ✓ (port {ollama.port})")
        else:
            say("⚠ Ollama başlatılamadı. Ayrıntılar: logs/ollama.log — uygulama yine de açılıyor.")

        # backend.config reads this when the app is imported below.
        os.environ["OLLAMA_HOST"] = ollama.host
        import uvicorn

        url = f"http://localhost:{app_port}"
        say(f"Uygulama: {url}   (kapatmak için bu pencerede Ctrl+C)")
        if not args.no_browser:
            threading.Thread(target=open_browser_when_ready, args=(url,), daemon=True).start()
        uvicorn.run("backend.main:app", host="127.0.0.1", port=app_port, log_level="warning")
    finally:
        say("Kapatılıyor…")
        sync_on_close()
        ollama.stop()
        release_lock()
    return 0


# ------------------------------------------------- two computers (backend/sync.py)

def sync_on_open() -> bool:
    """Take the other computer's newer work before the app opens the data. False: the learner stopped."""
    if not sync.enabled():
        if sync.folder():
            say(f"⚠ Eşitleme klasörü bulunamadı ({sync.folder()}); Google Drive açık mı? Eşitlemeden açılıyor.")
        return True
    other = sync.other_computer_open()
    if other:
        say(f"\n⚠ Uygulama şu anda '{other['machine']}' bilgisayarında da açık görünüyor.")
        say("  Orada çalışırken burada da açarsan iki taraftaki çalışma birleşmez (yenisi alınır, öbürü yedeğe).")
        say("  Önce orada kapat (Ctrl+C) ve Google Drive'ın eşitlemesini bekle.")
        if input("  Yine de açılsın mı? [e/H] ").strip().lower() not in ("e", "evet"):
            return False
    try:
        for msg in sync.sync_on_open():
            say(msg)
    except sync.SyncError as e:
        say(f"⚠ Eşitleme yapılamadı: {e}")
    except Exception as e:
        logging.getLogger("launcher").exception("sync on open")
        say(f"⚠ Eşitleme yapılamadı: {e}")
    sync.touch_lock()
    _on_console_close(sync_on_close)
    return True


def sync_on_close() -> None:
    try:
        if sync.enabled():
            sync.release()
            say("Eşitleme: son çalışman buluta gönderildi ✓")
    except Exception:
        logging.getLogger("launcher").exception("sync on close")


def _on_console_close(callback) -> None:
    """Closing the black window (X), logging off or shutting down still sends the data (Windows gives ~5 s).
    Linux: closing the terminal (SIGHUP) ends the app like Ctrl+C, so the launcher's cleanup runs (send the
    data, stop Ollama); uvicorn stops on SIGTERM."""
    if not IS_WINDOWS:
        signal.signal(signal.SIGHUP, lambda *_: os.kill(os.getpid(), signal.SIGTERM))
        return
    import ctypes

    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)
    def handler(event):
        if event in (2, 5, 6):  # CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, CTRL_SHUTDOWN_EVENT
            callback()
        return 0  # let the default handling (and Ctrl+C) go on

    _on_console_close.handler = handler  # keep a reference
    ctypes.windll.kernel32.SetConsoleCtrlHandler(handler, True)


if __name__ == "__main__":
    sys.exit(main())
