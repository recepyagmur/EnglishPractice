"""The learner's data on two computers (desktop + laptop) through a cloud folder (Google Drive).

The live database never sits in the cloud folder (a sync tool copying a file SQLite is writing can break it).
Instead each computer keeps its own data/app.db and exchanges a consistent copy:
- in the cloud folder: app.db (a snapshot), sync.json (who saved it when, its sha256, its schema version),
  lock.json (which computer has the app open, refreshed every few minutes);
- in data/sync.json (this computer only): the cloud folder, and "base" — the cloud version this computer last
  had — with the hash of the data at that moment, to tell whether it changed here since.
Every version sent carries its lineage (the versions it grew from), so a computer can tell whether the cloud's
version continued from what it had (then it is simply taken, deletions included) or came from another line —
e.g. the other computer still had week-old data and sent it. Then, and when the data changed on both computers
(the app was used on both without closing one), the version with the newer work wins (the learner's latest
activity inside the data, never a file's modification time: opening the app touches the file), the other is
saved to data/backups ("cakisma-…db") and a notice is shown; nothing is lost, nothing is merged (the learner
chose this). While open and on closing: a new snapshot is sent when the data changed. A local backup is taken
before the data here is ever replaced.
"""

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import machine
from .backup import backup_now, backup_to
from .config import BACKUP_DIR, DATA_DIR, DB_PATH, script

log = logging.getLogger(__name__)

LOCAL = DATA_DIR / "sync.json"
CLOUD_DB, CLOUD_META, CLOUD_LOCK = "app.db", "sync.json", "lock.json"
PUSH_EVERY = 120      # seconds between sends while the app is open
CHECK_EVERY = 20      # seconds between looks for a newer version from the other computer
LOCK_FRESH = 600      # a lock refreshed within this many seconds means "open there now"
FOLDER_NAME = "EnglishPractice"
LINEAGE_KEEP = 200    # versions remembered per lineage (one is sent every few minutes at most)
# When the learner last did something, per table: work, not visits (lesson_progress.*_opened_at and ui_state
# change when a page is merely opened: old data where a lesson was opened again would look "newer").
ACTIVITY = {
    "messages": ("created_at",), "sessions": ("started_at", "ended_at"), "corrections": ("created_at",),
    "error_log": ("created_at",), "writings": ("created_at",), "vocab": ("created_at", "last_reviewed_at"),
    "word_examples": ("created_at",), "lesson_progress": ("completed_at",),
    "exam_attempts": ("started_at", "finished_at"), "practice_days": ("day",),
    "pattern_progress": ("created_at", "last_reviewed_at"), "selftest_attempts": ("started_at", "finished_at"),
    "lesson_review": ("last_reviewed_at",),
}
_lock = threading.RLock()
replaced_at: str | None = None  # when this computer's data was last replaced by the cloud's (the page reloads)


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


def _write_cloud(path: Path, data: bytes | dict) -> None:
    """Write a file in the cloud folder in place. Not a temporary file renamed over it (as for local files): Google
    Drive may take that as deleting the old file, and deleted files fill its trash; a file changed in place only
    gets a new version. A half-written file is never taken: app.db is checked against sync.json's sha256, and a
    JSON file that does not parse is read as missing."""
    if isinstance(data, dict):
        data = json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")
    with open(path, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


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


def _when(value) -> datetime | None:
    """A stored time as UTC; a bare day (practice_days) is that day's start in local time."""
    try:
        t = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return t.astimezone(timezone.utc)  # naive (a bare day) → taken as local time


def _activity_of(con: sqlite3.Connection) -> datetime | None:
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    latest = []
    for table, cols in ACTIVITY.items():
        if table not in tables:
            continue
        have = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
        for col in cols:
            if col in have:
                value = con.execute(f"SELECT MAX({col}) FROM {table}").fetchone()[0]
                if value and (t := _when(value)):
                    latest.append(t)
    return max(latest, default=None)


def activity(path: Path) -> datetime | None:
    """When the learner last did something in this database (a cloud file or a snapshot), None when empty."""
    con = _open_cloud(path)
    try:
        return _activity_of(con)
    finally:
        con.close()


def local_activity() -> datetime | None:
    if not DB_PATH.exists():
        return None
    snap, _ = _snapshot()
    try:
        return activity(snap)
    finally:
        snap.unlink(missing_ok=True)


def _stamp(t: datetime | None) -> str | None:
    return t.isoformat(timespec="seconds") if t else None


def _newer(a: datetime | None, b: datetime | None) -> bool:
    """a's work is strictly newer than b's."""
    return a is not None and (b is None or a > b)


def _lineage() -> list[str]:
    """The versions this computer's data grew from (its base last)."""
    loc = local()
    return list(loc.get("lineage") or ([loc["base"]] if loc.get("base") else []))


def _continues_mine(meta: dict) -> bool | None:
    """Did the cloud's version grow from what this computer last had? None: unknown (sent by an older app)."""
    if "lineage" not in meta:
        return None
    return local().get("base") in meta["lineage"]


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
            if not force and meta.get("gen") and meta.get("gen") != local().get("base"):
                # The cloud has a version this computer has not seen (the other computer's, maybe only just
                # downloaded by Google Drive): never overwrite it blindly; sync_now() takes it or keeps the newer.
                return False
            if not force and sha == local().get("base_hash"):
                return False  # nothing new here, and the cloud has what this computer last had
            _write_cloud(d / CLOUD_DB, snap.read_bytes())
            for leftover in (d / f"{CLOUD_DB}-wal", d / f"{CLOUD_DB}-shm"):  # from an older version
                leftover.unlink(missing_ok=True)
            gen = uuid.uuid4().hex
            lineage = (_lineage() + [gen])[-LINEAGE_KEEP:]
            when = activity(snap)
            _write_cloud(d / CLOUD_META, {"gen": gen, "saved_at": _now(), "machine": machine.machine_name(),
                                    "sha256": sha, "schema": _schema(snap), "lineage": lineage,
                                    "activity": when.isoformat(timespec="seconds") if when else None})
            _save_local(base=gen, base_hash=sha, lineage=lineage, last_sync=_now(), base_activity=_stamp(when))
            log.info("Eşitleme: veriler buluta gönderildi")
            return True
        finally:
            snap.unlink(missing_ok=True)


class SyncError(Exception):
    pass


def _ready_cloud() -> tuple[Path, dict]:
    """The cloud folder and its sync.json, when its app.db is there and fully downloaded."""
    d = folder()
    meta = cloud_meta()
    if not (d and meta and (d / CLOUD_DB).exists()):
        raise SyncError("Bulut klasöründe veri yok.")
    if _sha(d / CLOUD_DB) != meta.get("sha256"):
        raise SyncError("Google Drive dosyayı henüz tam indirmedi; biraz sonra tekrar dene.")
    return d, meta


def _day(t: datetime | None) -> str:
    return t.astimezone().strftime("%d.%m.%Y %H:%M") if t else "çalışma yok"


def pull() -> None:
    """Replace this computer's data with the cloud's (a backup is taken first)."""
    from .db import MIGRATIONS

    with _lock:
        d, meta = _ready_cloud()
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
        try:
            when = activity(snap)
        finally:
            snap.unlink(missing_ok=True)
        _save_local(base=meta["gen"], base_hash=sha, lineage=meta.get("lineage") or [meta["gen"]], last_sync=_now(),
                    base_activity=_stamp(when))
        global replaced_at
        replaced_at = _now()  # the open page reloads (status → health "sync_replaced_at")
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
        if not DB_PATH.exists():
            pull()
            return [f"Eşitleme: {meta.get('machine')} bilgisayarındaki son çalışman alındı ✓"]
        d, meta = _ready_cloud()
        who = meta.get("machine") or "bulut"
        changed = local_changed()
        mine, theirs = local_activity(), activity(d / CLOUD_DB)
        # Opening a page also writes (last opened lesson, saved page state): a change without newer work is not
        # work to keep against the other computer's (it is in the pre-sync backup anyway).
        base_act = _when(local()["base_activity"]) if local().get("base_activity") else None
        if changed and "base_activity" in local() and not _newer(mine, base_act):
            changed = False
        continues = _continues_mine(meta)
        if continues is None:  # sent by an older version of the app (no lineage): judge by the work inside
            continues = not _newer(mine, theirs)
        if continues and not changed:
            pull()
            return [f"Eşitleme: {who} bilgisayarındaki son çalışman alındı ✓"]
        # Changed on both computers, or the cloud's data did not grow from this computer's: the newer work wins
        # (equal: the cloud when it continues this computer's data), the other is kept as a backup.
        if _newer(theirs, mine) or (continues and not _newer(mine, theirs)):
            snap, _ = _snapshot()
            kept = _keep_conflict(snap, machine.machine_name())
            snap.unlink(missing_ok=True)
            pull()
            why = ("iki bilgisayarda da kapatılmadan çalışılmış." if changed else
                   f"{who} bilgisayarındaki veri bu bilgisayardakinin devamı değil.")
            msg = (f"⚠ Eşitleme: {why} {who} bilgisayarındaki daha yeni veri alındı (son çalışma {_day(theirs)}); "
                   f"bu bilgisayardaki önceki hali (son çalışma {_day(mine)}) yedekte: {kept.name}")
        else:
            kept = _keep_conflict(d / CLOUD_DB, who)
            _save_local(lineage=(_lineage() + [meta["gen"]])[-LINEAGE_KEEP:])  # that version is settled now
            push(force=True)
            if changed and continues:
                msg = (f"⚠ Eşitleme: iki bilgisayarda da kapatılmadan çalışılmış. Bu bilgisayardaki daha yeni veri "
                       f"(son çalışma {_day(mine)}) gönderildi; {who} bilgisayarındaki hali yedekte: {kept.name}")
            else:
                msg = (f"⚠ Eşitleme: buluttaki veri ({who}, son çalışma {_day(theirs)}) bu bilgisayardakinden "
                       f"(son çalışma {_day(mine)}) eski, alınmadı. Bu bilgisayardaki veri gönderildi; "
                       f"buluttaki hali yedekte: {kept.name}")
        _save_local(notice=msg, notice_at=_now())
        return [msg]


# ------------------------------------------------------------------ open / close

def other_computer_open() -> dict | None:
    """The lock of another computer that has the app open now (refreshed recently), else None."""
    d = folder()
    lock = _read(d / CLOUD_LOCK) if d else None
    if (lock and lock.get("machine") != machine.machine_name() and not lock.get("closed")
            and _age(lock.get("at")) < LOCK_FRESH):
        return lock
    return None


def touch_lock() -> None:
    d = folder()
    if d and d.exists():
        _write_cloud(d / CLOUD_LOCK, {"machine": machine.machine_name(), "at": _now()})


def sync_now() -> list[str]:
    """Take the other computer's newer work if there is any (as on opening), then send this computer's changes."""
    with _lock:
        msgs = sync_on_open()
        push()
        return msgs


def release() -> None:
    """On closing: send the latest data and say the app is no longer open here."""
    if not enabled():
        return
    try:
        sync_now()
    except Exception:
        log.exception("Eşitleme: kapanışta gönderilemedi")
    d = folder()
    lock = _read(d / CLOUD_LOCK)
    if lock and lock.get("machine") == machine.machine_name():  # marked closed, not deleted (see _write_cloud)
        _write_cloud(d / CLOUD_LOCK, {**lock, "closed": True, "at": _now()})


def _cloud_consistent(d: Path) -> bool:
    """The cloud folder's app.db is the one its sync.json describes (Google Drive finished downloading both)."""
    meta = _read(d / CLOUD_META)
    if not meta:
        return True  # nothing there yet: nothing to wait for
    try:
        return (d / CLOUD_DB).exists() and _sha(d / CLOUD_DB) == meta.get("sha256")
    except OSError:
        return False


def wait_until_ready(timeout: float, say=print) -> bool:
    """On opening: Google Drive may still be starting (no folder yet) or downloading the other computer's latest
    data. Wait up to `timeout` seconds until the folder is there and consistent."""
    d = folder()
    if not d:
        return False
    deadline, told = time.monotonic() + timeout, False
    while not (d.exists() and _cloud_consistent(d)):
        if time.monotonic() >= deadline:
            return False
        if not told:
            say(f"Google Drive bekleniyor (en çok {int(timeout)} sn)…")
            told = True
        time.sleep(1)
    return True


def start_background() -> None:
    """While the app is open: every CHECK_EVERY seconds look for a newer version from the other computer (Google
    Drive may bring it only after the app opened) and take it; every PUSH_EVERY seconds refresh the lock and send
    this computer's changes."""
    def loop():
        stop, last_push = threading.Event(), time.monotonic()
        while not stop.wait(CHECK_EVERY):
            if not enabled():
                continue
            try:
                meta = cloud_meta()
                if meta and meta.get("gen") != local().get("base"):
                    for msg in sync_on_open():
                        log.info(msg)
                if time.monotonic() - last_push >= PUSH_EVERY:
                    last_push = time.monotonic()
                    touch_lock()
                    push()
            except SyncError as e:  # e.g. Google Drive still downloading: the next round tries again
                log.info("Eşitleme: %s", e)
            except Exception:
                log.exception("Eşitleme: arka planda yapılamadı")

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
        "cloud": {k: meta.get(k) for k in ("machine", "saved_at", "activity")} if meta else None,
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
        _save_local(dir=str(p), base=None, base_hash=None, lineage=[], notice=None)
        meta = cloud_meta()
        if meta and meta.get("machine") != machine.machine_name():
            # Each side's latest work, so the learner sees which one is newer before choosing.
            try:
                theirs = activity(p / CLOUD_DB) if (p / CLOUD_DB).exists() else None
            except sqlite3.Error:  # not fully downloaded yet
                theirs = None
            mine = local_activity()
            stamp = lambda t: t.isoformat(timespec="seconds") if t else None
            return {"choose": True, "cloud": {k: meta.get(k) for k in ("machine", "saved_at")},
                    "cloud_activity": stamp(theirs), "local_activity": stamp(mine),
                    "newer": "cloud" if _newer(theirs, mine) else "local" if _newer(mine, theirs) else None}
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
            meta = cloud_meta() or {}
            if (d / CLOUD_DB).exists():
                _keep_conflict(d / CLOUD_DB, meta.get("machine") or "bulut")
            if meta.get("gen"):  # the learner chose this data over the cloud's: the other computer takes it
                _save_local(lineage=(meta.get("lineage") or [meta["gen"]])[-LINEAGE_KEEP:])
            push(force=True)
        else:
            raise SyncError("Geçersiz seçim.")
        touch_lock()


def turn_off() -> None:
    with _lock:
        release()
        _save_local(dir=None)
