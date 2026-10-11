"""The learner's data on two computers (desktop + laptop) through a cloud folder (Google Drive).

The live database never sits in the cloud folder (a sync tool copying a file SQLite is writing can break it).
Instead each computer keeps its own data/app.db and exchanges a consistent copy:
- in the cloud folder: app.db (a snapshot), sync.json (who saved it when, its sha256, its schema version),
  lock.json (which computer has the app open, refreshed every few minutes);
- in data/sync.json (this computer only): the cloud folder, and "base" — the cloud version this computer last
  had — with the hash of the data at that moment, to tell whether it changed here since.
On opening: if the cloud has a newer version and nothing changed here → take it. If both changed (the app was
used on both computers without closing one) → the newer one wins, the other is saved to data/backups
("cakisma-…db") and a notice is shown; nothing is lost, nothing is merged (the learner chose this).
While open and on closing: a new snapshot is sent when the data changed. A local backup is taken before
the data here is ever replaced.
"""

import hashlib
import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import machine
from .backup import backup_now, backup_to
from .config import BACKUP_DIR, DATA_DIR, DB_PATH, script

log = logging.getLogger(__name__)

LOCAL = DATA_DIR / "sync.json"
CLOUD_DB, CLOUD_META, CLOUD_LOCK = "app.db", "sync.json", "lock.json"
PUSH_EVERY = 120      # seconds between checks while the app is open
LOCK_FRESH = 600      # a lock refreshed within this many seconds means "open there now"
FOLDER_NAME = "EnglishPractice"
_lock = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _age(iso: str | None) -> float:
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()
    except (TypeError, ValueError):
        return float("inf")


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local() -> dict:
    return _read(LOCAL) or {}


def _save_local(**changes) -> dict:
    data = {**local(), **changes}
    _write(LOCAL, data)
    return data


def folder() -> Path | None:
    d = local().get("dir")
    return Path(d) if d else None


def enabled() -> bool:
    d = folder()
    return bool(d and d.exists())


def suggest_folder() -> str | None:
    """Google Drive's folder on this computer, if it is installed (G:\\My Drive\\EnglishPractice …).
    Linux has no Google Drive program: a folder kept in sync by another tool (rclone, Insync, google-drive-ocamlfuse)
    under a usual name is suggested; otherwise the learner types the folder."""
    if os.name != "nt":
        home = Path.home()
        for name in ("Google Drive", "GoogleDrive", "google-drive", "gdrive", "Insync"):
            root = home / name
            if root.is_dir():
                drive = root / "My Drive" if (root / "My Drive").is_dir() else root
                return str(drive / FOLDER_NAME)
        return None
    for letter in "GHIJKLMNOPQRSTUVWXYZDEF":
        for name in ("My Drive", "Drive'ım", "Meine Ablage"):
            root = Path(f"{letter}:\\{name}")
            if root.exists():
                return str(root / FOLDER_NAME)
    home = Path.home() / "Google Drive"
    return str(home / FOLDER_NAME) if home.exists() else None


# ------------------------------------------------------------------ snapshots

def _snapshot() -> tuple[Path, str]:
    """A consistent copy of the live database (SQLite's backup) and its hash. The copy is a single file
    (rollback journal, not WAL): reading a WAL file creates -wal/-shm files next to it, which must never
    appear in the cloud folder."""
    path = DATA_DIR / "sync-snapshot.db"
    for p in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        p.unlink(missing_ok=True)
    backup_to(path, DB_PATH)
    con = sqlite3.connect(path)
    try:
        con.execute("PRAGMA journal_mode = DELETE")
    finally:
        con.close()
    return path, _sha(path)


def _open_cloud(path: Path) -> sqlite3.Connection:
    """Read a file in the cloud folder without writing anything next to it."""
    return sqlite3.connect(f"{path.as_uri()}?mode=ro&immutable=1", uri=True)


def _schema(path: Path) -> int:
    con = _open_cloud(path)
    try:
        return con.execute("PRAGMA user_version").fetchone()[0]
    finally:
        con.close()


def local_changed() -> bool:
    if not DB_PATH.exists():
        return False
    snap, sha = _snapshot()
    snap.unlink(missing_ok=True)
    return sha != local().get("base_hash")


def cloud_meta() -> dict | None:
    d = folder()
    return _read(d / CLOUD_META) if d else None


# ----------------------------------------------------------------- push / pull

def push(force: bool = False) -> bool:
    """Send this computer's data to the cloud folder when it changed (or `force`). True when sent."""
    with _lock:
        d = folder()
        if not (d and d.exists() and DB_PATH.exists()):
            return False
        snap, sha = _snapshot()
        try:
            meta = _read(d / CLOUD_META) or {}
            if not force and sha == local().get("base_hash") and meta.get("gen") == local().get("base"):
                return False  # nothing new here, and the cloud has what this computer last had
            tmp = d / (CLOUD_DB + ".tmp")
            tmp.write_bytes(snap.read_bytes())
            os.replace(tmp, d / CLOUD_DB)
            for leftover in (d / f"{CLOUD_DB}-wal", d / f"{CLOUD_DB}-shm"):  # from an older version
                leftover.unlink(missing_ok=True)
            gen = uuid.uuid4().hex
            _write(d / CLOUD_META, {"gen": gen, "saved_at": _now(), "machine": machine.machine_name(),
                                    "sha256": sha, "schema": _schema(snap)})
            _save_local(base=gen, base_hash=sha, last_sync=_now())
            log.info("Eşitleme: veriler buluta gönderildi")
            return True
        finally:
            snap.unlink(missing_ok=True)


class SyncError(Exception):
    pass


def pull() -> None:
    """Replace this computer's data with the cloud's (a backup is taken first)."""
    from .db import MIGRATIONS

    with _lock:
        d = folder()
        meta = cloud_meta()
        if not (d and meta and (d / CLOUD_DB).exists()):
            raise SyncError("Bulut klasöründe veri yok.")
        if _sha(d / CLOUD_DB) != meta.get("sha256"):
            raise SyncError("Google Drive dosyayı henüz tam indirmedi; biraz sonra tekrar dene.")
        if meta.get("schema", 0) > len(MIGRATIONS):
            raise SyncError(f"Buluttaki veri uygulamanın daha yeni bir sürümüyle kaydedilmiş ({meta.get('machine')}). "
                            f"Önce bu bilgisayarda {script('update')} ile güncelle.")
        if DB_PATH.exists():
            backup_now("pre-sync")
        src = _open_cloud(d / CLOUD_DB)
        dst = sqlite3.connect(DB_PATH)
        try:
            src.backup(dst)  # SQLite replaces the pages itself: safe even while the app has the file open
        finally:
            dst.close()
            src.close()
        snap, sha = _snapshot()
        snap.unlink(missing_ok=True)
        _save_local(base=meta["gen"], base_hash=sha, last_sync=_now())
        log.info("Eşitleme: %s bilgisayarının verileri alındı", meta.get("machine"))


def _keep_conflict(path: Path, who: str) -> Path:
    """A copy of the version that did not win, in data/backups."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUP_DIR / f"cakisma-{who}-{stamp}.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(path.read_bytes())
    return target


def sync_on_open() -> list[str]:
    """Bring this computer up to date when the app opens. Returns messages for the learner."""
    msgs = []
    if not enabled():
        return msgs
    with _lock:
        meta = cloud_meta()
        if not meta:
            push(force=True)
            return ["Eşitleme: veriler buluta ilk kez gönderildi."]
        if meta.get("gen") == local().get("base"):
            return msgs  # the cloud has nothing newer than what this computer had
        if not local_changed() or not DB_PATH.exists():
            pull()
            return [f"Eşitleme: {meta.get('machine')} bilgisayarındaki son çalışman alındı ✓"]
        # Changed on both computers: the newer wins, the other is kept as a backup.
        mine = datetime.fromtimestamp(DB_PATH.stat().st_mtime, timezone.utc)
        theirs = datetime.fromisoformat(meta["saved_at"])
        if theirs >= mine:
            snap, _ = _snapshot()
            kept = _keep_conflict(snap, machine.machine_name())
            snap.unlink(missing_ok=True)
            pull()
            msg = (f"⚠ Eşitleme: iki bilgisayarda da kapatılmadan çalışılmış. {meta.get('machine')} bilgisayarındaki "
                   f"daha yeni veri alındı; bu bilgisayardaki önceki hali yedekte: {kept.name}")
        else:
            kept = _keep_conflict(folder() / CLOUD_DB, meta.get("machine") or "bulut")
            push(force=True)
            msg = (f"⚠ Eşitleme: iki bilgisayarda da kapatılmadan çalışılmış. Bu bilgisayardaki daha yeni veri "
                   f"gönderildi; {meta.get('machine')} bilgisayarındaki hali yedekte: {kept.name}")
        _save_local(notice=msg, notice_at=_now())
        return [msg]


# ------------------------------------------------------------------ open / close

def other_computer_open() -> dict | None:
    """The lock of another computer that has the app open now (refreshed recently), else None."""
    d = folder()
    lock = _read(d / CLOUD_LOCK) if d else None
    if lock and lock.get("machine") != machine.machine_name() and _age(lock.get("at")) < LOCK_FRESH:
        return lock
    return None


def touch_lock() -> None:
    d = folder()
    if d and d.exists():
        _write(d / CLOUD_LOCK, {"machine": machine.machine_name(), "at": _now()})


def release() -> None:
    """On closing: send the latest data and say the app is no longer open here."""
    if not enabled():
        return
    try:
        push()
    except Exception:
        log.exception("Eşitleme: kapanışta gönderilemedi")
    d = folder()
    lock = _read(d / CLOUD_LOCK)
    if lock and lock.get("machine") == machine.machine_name():
        (d / CLOUD_LOCK).unlink(missing_ok=True)


def start_background() -> None:
    """While the app is open: refresh the lock and send changes every PUSH_EVERY seconds."""
    def loop():
        stop = threading.Event()
        while not stop.wait(PUSH_EVERY):
            if not enabled():
                continue
            try:
                touch_lock()
                push()
            except Exception:
                log.exception("Eşitleme: arka planda gönderilemedi")

    threading.Thread(target=loop, daemon=True, name="sync").start()


# ---------------------------------------------------------------- settings page

def status() -> dict:
    d = folder()
    meta = cloud_meta() if enabled() else None
    loc = local()
    other = other_computer_open() if enabled() else None
    return {
        "enabled": enabled(), "dir": str(d) if d else None, "dir_missing": bool(d) and not enabled(),
        "suggested": suggest_folder(), "machine": machine.machine_name(),
        "cloud": {k: meta.get(k) for k in ("machine", "saved_at")} if meta else None,
        "last_sync": loc.get("last_sync"), "notice": loc.get("notice"), "notice_at": loc.get("notice_at"),
        "other_open": other.get("machine") if other else None,
    }


def setup(path: str) -> dict:
    """Turn on with this cloud folder. When the folder already has data from another computer and this one has
    data too, the learner chooses (choose()); otherwise this computer's data is sent."""
    p = Path(path.strip().strip('"'))
    if not p.parent.exists():
        raise SyncError(f"Klasör bulunamadı: {p.parent}. Google Drive bu bilgisayarda açık mı?")
    p.mkdir(parents=True, exist_ok=True)
    with _lock:
        _save_local(dir=str(p), base=None, base_hash=None, notice=None)
        meta = cloud_meta()
        if meta and meta.get("machine") != machine.machine_name():
            return {"choose": True, "cloud": {k: meta.get(k) for k in ("machine", "saved_at")}}
        push(force=True)
        touch_lock()
        return {"choose": False}


def choose(action: str) -> None:
    """First setup on a second computer: take the cloud's data ("pull") or send this one's ("push")."""
    with _lock:
        if action == "pull":
            pull()
        elif action == "push":
            d = folder()
            if (d / CLOUD_DB).exists():
                _keep_conflict(d / CLOUD_DB, (cloud_meta() or {}).get("machine") or "bulut")
            push(force=True)
        else:
            raise SyncError("Geçersiz seçim.")
        touch_lock()


def turn_off() -> None:
    with _lock:
        release()
        _save_local(dir=None)
