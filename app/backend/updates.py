"""A newer version of the app on GitHub: checked when the app opens, applied from the app (Ayarlar → Güncelleme).

The check runs in the background once per opening (never delays it; skipped silently offline) and asks GitHub's
public API for the latest commit of the repository; nothing about the learner is sent. A copy made from a package
or an update knows its commit (config/package-version.txt); a development copy (git repository) is never updated
this way (git pull).

Applying: the zip is downloaded and checked here (setup/updater.read_archive), recorded as pending, then the app
closes itself as on Ctrl+C (data sent to the cloud folder, Ollama stopped). The launcher applies the pending update
with setup/updater.py — data/, runtime/, models/ are never touched, the data is backed up first — and opens the
app again with the new code (launcher.apply_pending_update / relaunch). A pending update left behind (e.g. the
computer was switched off) is applied the next time the app opens.
"""

import json
import logging
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone

from . import machine
from .config import DATA_DIR, ROOT_DIR

log = logging.getLogger(__name__)

UPDATE_DIR = DATA_DIR / "updates"
PENDING = UPDATE_DIR / "pending.json"
MAX_ZIP = 500_000_000      # bytes; the archive is ~40 MB
CHANGES_SHOWN = 15
TIMEOUT = 15               # seconds per request

_state: dict = {"state": "idle"}
_lock = threading.Lock()
restart_hook = None        # set by the launcher: closes the app so the update can be applied
restart_requested = False  # the launcher applies the pending update and opens the app again only then


def _updater():
    from setup import updater  # the folder above app/ is on the path (python312._pth / englishpractice.pth)
    return updater


def is_dev() -> bool:
    return (ROOT_DIR / ".git").exists()


def current_version() -> str | None:
    try:
        return _updater().VERSION_FILE.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def enabled() -> bool:
    """Checking on opening can be turned off per computer (Ayarlar → Güncelleme)."""
    return machine.load_profile().get("update_check", "1") != "0"


def set_enabled(on: bool) -> None:
    machine.update_profile({"update_check": "1" if on else "0"})


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "EnglishPractice-app"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _commit(c: dict) -> dict:
    """A commit for the page: its title and the description under it (attribution lines left out)."""
    title, _, body = c["commit"]["message"].partition("\n")
    paragraphs = []  # commit messages are wrapped at ~110 characters: join the lines back, keep "- " items
    for line in body.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("Co-Authored-By:"):
            paragraphs.append("")
        elif line.startswith("- ") or not paragraphs or not paragraphs[-1]:
            paragraphs.append(line)
        else:
            paragraphs[-1] += " " + line
    body = "\n".join(p for p in paragraphs if p)
    return {"sha": c["sha"], "date": c["commit"]["committer"]["date"], "title": title.strip(), "body": body}


def _set(**state) -> dict:
    with _lock:
        _state.clear()
        _state.update(state, checked_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        return dict(_state)


def status() -> dict:
    with _lock:
        out = dict(_state)
    return {**out, "current": current_version(), "dev": is_dev(), "enabled": enabled()}


def check() -> dict:
    """Ask GitHub for the latest version. States: dev | current | available | error."""
    if is_dev():
        return _set(state="dev")
    up = _updater()
    api = f"https://api.github.com/repos/{up.REPO}"
    _set(state="checking")
    try:
        latest = _commit(_get(f"{api}/commits/{up.BRANCH}"))
    except (OSError, ValueError, KeyError) as e:  # offline, GitHub unreachable or limited
        log.info("Güncelleme denetlenemedi: %s", e)
        return _set(state="error", message="GitHub'a ulaşılamadı (internet bağlantısı yok olabilir).")
    current = current_version()
    if latest["sha"] == current:
        return _set(state="current", latest=latest)
    changes = []
    if current:
        try:
            diff = _get(f"{api}/compare/{current}...{latest['sha']}")
            if diff.get("status") in ("identical", "behind"):
                return _set(state="current", latest=latest)
            changes = [_commit(c) for c in reversed(diff.get("commits", []))][:CHANGES_SHOWN]  # newest first
        except (OSError, ValueError, KeyError):
            pass  # e.g. a copy made from another repository: its commit is unknown here
    return _set(state="available", latest=latest, changes=changes or [latest])


def check_in_background() -> None:
    if is_dev() or not enabled():
        return
    threading.Thread(target=check, daemon=True, name="update-check").start()


# ------------------------------------------------------------------ applying

def start_update() -> dict:
    """Download the latest version in the background, then close the app to apply it."""
    with _lock:
        if _state.get("state") in ("downloading", "restarting"):
            return dict(_state)
    if is_dev():
        raise UpdateError("Bu klasör geliştirme kopyası (git deposu): güncellemek için git pull.")
    _set(state="downloading", received=0)
    threading.Thread(target=_download_and_restart, daemon=True, name="update").start()
    return status()


class UpdateError(Exception):
    pass


def _download_and_restart() -> None:
    up = _updater()
    UPDATE_DIR.mkdir(parents=True, exist_ok=True)
    part = UPDATE_DIR / f"{up.ZIP_PREFIX}.zip.part"
    target = UPDATE_DIR / f"{up.ZIP_PREFIX}.zip"
    try:
        req = urllib.request.Request(up.ARCHIVE_URL, headers={"User-Agent": "EnglishPractice-app"})
        received = 0
        with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
            while chunk := r.read(1 << 20):
                received += len(chunk)
                if received > MAX_ZIP:
                    raise UpdateError("İndirilen dosya beklenenden çok büyük.")
                f.write(chunk)
                with _lock:
                    _state["received"] = received
        part.replace(target)
        _files, commit = up.read_archive(target)  # a real English Practice archive (raises otherwise)
        if commit and commit == current_version():
            target.unlink(missing_ok=True)
            _set(state="current")
            return
        PENDING.write_text(json.dumps({"zip": target.name, "commit": commit,
                                       "at": datetime.now().isoformat(timespec="seconds")}), encoding="utf-8")
    except Exception as e:  # network, disk, a broken zip: nothing was changed
        part.unlink(missing_ok=True)
        log.exception("Güncelleme indirilemedi")
        _set(state="error", message=f"Güncelleme indirilemedi: {e}")
        return
    log.info("Güncelleme indirildi (%s); uygulama yeniden açılıyor", (commit or "?")[:7])
    if restart_hook is None:  # not started by the launcher (a test server): applied on the next opening
        _set(state="ready", commit=commit)
        return
    global restart_requested
    restart_requested = True
    _set(state="restarting", commit=commit)
    threading.Timer(1.0, restart_hook).start()  # let the page get its answer first


def pending() -> dict | None:
    """The downloaded update waiting to be applied (its zip exists), else None."""
    try:
        info = json.loads(PENDING.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    zip_path = UPDATE_DIR / str(info.get("zip", ""))
    return {**info, "path": zip_path} if info.get("zip") and zip_path.is_file() else None


def apply_pending(say=print) -> bool:
    """Apply the pending update (launcher, with the app closed). True when files were updated."""
    info = pending()
    PENDING.unlink(missing_ok=True)  # once: a failing update must not stop the app from opening every time
    if not info:
        return False
    up = _updater()
    if is_dev():
        info["path"].unlink(missing_ok=True)
        say("Bu klasör geliştirme kopyası (git deposu); güncelleme uygulanmadı (git pull).")
        return False
    old = current_version() or "?"
    try:
        files, commit = up.read_archive(info["path"])
        from .backup import backup_now
        if (saved := backup_now("pre-update")):
            say(f"Verilerin yedeklendi: {saved.name}")
        changed, removed, reqs = up.apply(files)
        if commit:
            up.VERSION_FILE.write_text(commit, encoding="utf-8")
        if reqs:
            up.reinstall_packages(reqs)
    except Exception as e:
        log.exception("Güncelleme uygulanamadı")
        say(f"⚠ Güncelleme uygulanamadı: {e}. Verilerin yedekte; {up.script('update')} ile tekrar deneyebilirsin.")
        return False
    finally:
        info["path"].unlink(missing_ok=True)
    say(f"✓ Güncellendi ({old[:7]} → {(commit or '?')[:7]}): {changed} dosya değişti, {removed} dosya silindi.")
    return True
