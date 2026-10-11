"""Installation tasks of the setup wizard: downloads (resumable, verified), the
bundled Ollama, Python packages, models, dictionary, shortcut and the computer
profile. Every task is independent: one failing does not stop the others.

Only the standard library is imported at module level, so the wizard starts
before the app's Python packages are installed.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from backend.config import (APP_DIR, DATA_DIR, IS_WINDOWS, MODELS_DIR, OLLAMA_EXE, OLLAMA_MODELS_DIR, ROOT_DIR,
                            STT_MODELS_DIR, TTS_MODELS_DIR, script)

from . import ollama_models

CATALOG = json.loads((Path(__file__).parent / "catalog.json").read_text(encoding="utf-8"))
DOWNLOADS = MODELS_DIR / "_downloads"
USER_AGENT = "EnglishPractice-Setup/1.0"
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0  # CREATE_NO_WINDOW (Windows only)
OLLAMA_CATALOG = CATALOG["ollama"] if IS_WINDOWS else CATALOG["ollama_linux"]


class Cancelled(Exception):
    pass


# --------------------------------------------------------------- download

Progress = Callable[[int, int], None]  # (done bytes, total bytes)


def _request(url: str, headers: dict | None = None, method: str = "GET"):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT, **(headers or {})})
    return urllib.request.urlopen(req, timeout=60)


def remote_size(url: str) -> int | None:
    try:
        with _request(url, method="HEAD") as r:
            return int(r.headers.get("Content-Length") or 0) or None
    except OSError:
        return None


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 22):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, size: int | None = None, sha256: str | None = None,
             progress: Progress | None = None, should_stop: Callable[[], bool] = lambda: False) -> Path:
    """Download to dest. An interrupted download continues from a .part file
    (also after the wizard was closed). Verified with SHA256 when given."""
    if dest.exists() and (not size or dest.stat().st_size == size):
        if not sha256 or sha256_of(dest) == sha256:
            return dest
        dest.unlink()
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    total = size or remote_size(url) or 0
    for attempt in range(5):
        have = part.stat().st_size if part.exists() else 0
        if total and have >= total:
            break
        try:
            headers = {"Range": f"bytes={have}-"} if have else {}
            with _request(url, headers) as r, open(part, "ab" if have and r.status == 206 else "wb") as f:
                if r.status != 206:
                    have = 0
                total = total or have + int(r.headers.get("Content-Length") or 0)
                while chunk := r.read(1 << 20):
                    if should_stop():
                        raise Cancelled()
                    f.write(chunk)
                    have += len(chunk)
                    if progress:
                        progress(have, total)
            break
        except (OSError, TimeoutError) as e:
            if attempt == 4:
                raise RuntimeError(f"İndirme başarısız: {e}") from e
            time.sleep(2 * (attempt + 1))
    if sha256 and sha256_of(part) != sha256:
        part.unlink()
        raise RuntimeError("İndirilen dosya bozuk (SHA256 tutmadı); tekrar deneyin.")
    part.replace(dest)
    return dest


# ------------------------------------------------------- catalog + badges

def registry_size(model: str) -> int | None:
    """Real download size of an Ollama model from the registry manifest."""
    name, _, tag = model.partition(":")
    url = f"https://registry.ollama.ai/v2/library/{name}/manifests/{tag or 'latest'}"
    try:
        with _request(url, {"Accept": "application/vnd.docker.distribution.manifest.v2+json"}) as r:
            manifest = json.load(r)
        return sum(layer["size"] for layer in manifest.get("layers", []))
    except (OSError, ValueError, KeyError):
        return None


def badge(model: dict, hw: dict, whisper_on_gpu: bool) -> dict:
    """Fit estimate for this computer (a guess — the speed test in step 8 decides).

    NVIDIA:   usable = VRAM − (~1 GB if Whisper runs on the GPU) − 1 GB headroom.
              fits usable → "fit"; else fits VRAM + free RAM → "slow" (Ollama moves
              layers to the CPU); else → "no".
    Integrated GPU / CPU only: usable = total RAM × 0.5 (shared memory + the OS);
              fits → "fit", but models above ~10 GB → "slow"; beyond usable → "no".
    """
    need = model["min_memory_gb"]
    if hw.get("accel") == "cuda" and hw.get("vram_gb"):
        usable = hw["vram_gb"] - (1 if whisper_on_gpu else 0) - 1
        if need <= usable:
            return {"level": "fit", "usable_gb": usable}
        if need <= hw["vram_gb"] + (hw.get("ram_free_gb") or 0):
            return {"level": "slow", "usable_gb": usable}
        return {"level": "no", "usable_gb": usable}
    usable = (hw.get("ram_gb") or 8) * 0.5
    if need > usable:
        return {"level": "no", "usable_gb": usable}
    return {"level": "slow" if need > 10 else "fit", "usable_gb": usable}


# A reply of ~30 tokens should take at most ~4 s: the speed a model needs to be recommended.
TARGET_TOKENS_PER_SEC = 8.0


def cpu_speed_factor(hw: dict) -> float:
    """Text-generation speed of this CPU relative to the reference CPU the catalog's `cpu_tps` were
    measured on (Ryzen 5 5600, 6 cores, desktop). Generation is mostly limited by memory bandwidth:
    low-power laptop chips (U series, 15 W) reach about half, H series laptops a bit less than a desktop."""
    import re

    name = (hw.get("cpu") or "").upper()
    cores = hw.get("cpu_cores") or 4
    factor = (min(cores, 8) / 6) ** 0.3
    if re.search(r"\d{4,5}U\b|\d{4}G\d\b|ULTRA \d+ \d{3}U\b", name):  # i5-8265U, i5-1135G7, Core Ultra …U
        factor *= 0.55
    elif re.search(r"\d{4,5}H[SXK]?\b|ULTRA \d+ \d{3}H\b", name):  # Ryzen 5 4600H, i7-12700H, Core Ultra …H
        factor *= 0.85
    return round(factor, 2)


def estimated_speed(model: dict, hw: dict, fit: str) -> float | None:
    """Expected tokens/s on this computer (None: not measured for this model)."""
    if hw.get("accel") == "cuda" and fit == "fit":
        return model.get("gpu_tps")
    if model.get("cpu_tps"):
        return round(model["cpu_tps"] * cpu_speed_factor(hw), 1)
    return None


def catalog_for(hw: dict, whisper_on_gpu: bool, sizes: dict[str, int | None]) -> list[dict]:
    installed = set(ollama_models.list_models(OLLAMA_MODELS_DIR))
    system_dirs = ollama_models.system_model_dirs(exclude=OLLAMA_MODELS_DIR)
    out = []
    for m in CATALOG["models"]:
        b = badge(m, hw, whisper_on_gpu)
        out.append({
            **m,
            "badge": b["level"],
            "est_tps": estimated_speed(m, hw, b["level"]),
            "size_bytes": sizes.get(m["id"]) or int(m["download_gb"] * 1e9),
            "installed": m["id"] in installed,
            "system_copy": next((str(d) for d in system_dirs if ollama_models.has_model(d, m["id"])), None),
        })
    # "Recommended": only models verified to give correct Turkish explanations and corrections
    # (catalog "verified"). Among those that fit: the best quality that is fast enough on this
    # computer; if none is fast enough, the fastest (catalog order breaks ties).
    candidates = [m for m in out if m["badge"] == "fit" and m.get("verified")]
    fast = [m for m in candidates if (m["est_tps"] or 0) >= TARGET_TOKENS_PER_SEC]
    if fast:
        best = max(fast, key=lambda m: m["quality"])
    elif candidates:
        best = max(candidates, key=lambda m: (m["est_tps"] or 0, m["quality"]))
    else:
        best = None
    if best:
        best["badge"] = "recommended"
    return out


def whisper_recommendation(hw: dict) -> dict:
    """Speech recognition for this computer: on an NVIDIA GPU small.en is instant; on the CPU
    small.en takes ~2.5 s per sentence on a desktop (measured) — still worth it for accuracy
    (misheard words would be "corrected" as the learner's mistakes). Only weak CPUs get base.en."""
    if hw.get("accel") == "cuda":
        return {"model": "small.en", "device": "cuda", "note_tr": "Ekran kartında çalışır, anında yazıya çevirir."}
    factor = cpu_speed_factor(hw)
    if (hw.get("cpu_cores") or 4) < 4 or (hw.get("ram_gb") or 8) < 8:
        return {"model": "base.en", "device": "cpu",
                "note_tr": "Bu bilgisayar için hızlı olan base.en önerilir (cümle başına ~1–2 sn)."}
    seconds = round(2.5 / max(factor, 0.3))
    return {"model": "small.en", "device": "cpu",
            "note_tr": f"İşlemcide çalışır: bir cümleyi yazıya çevirmek ~{seconds} sn sürer. "
                       "Daha doğru olduğu için önerilir; base.en daha hızlıdır (~1 sn) ama daha çok yanlış duyar."}


# ------------------------------------------------------------------ tasks

@dataclass
class Task:
    id: str
    title: str
    size: int = 0                 # bytes to download (for the summary)
    status: str = "pending"       # pending | running | done | failed | skipped
    progress: float = 0.0
    detail: str = ""
    error: str = ""
    speed: float = 0.0            # bytes / second
    eta: float | None = None      # seconds
    _run: Callable | None = field(default=None, repr=False)

    def public(self) -> dict:
        d = asdict(self)
        d.pop("_run")
        return d


class Installer:
    """Runs the selected tasks one after another in a background thread."""

    def __init__(self) -> None:
        self.tasks: list[Task] = []
        self.thread: threading.Thread | None = None
        self.ollama = None
        self.stop_requested = False
        self.on_finish: Callable[[list["Task"]], None] | None = None

    # progress helper with speed / ETA
    def _progress(self, task: Task):
        start, last, first = time.monotonic(), [0.0], [None]

        def report(done: int, total: int) -> None:
            now = time.monotonic()
            if first[0] is None:
                first[0] = done  # a resumed download starts above zero: not part of the speed
            if now - last[0] < 0.25 and done < total:
                return
            last[0] = now
            task.progress = done / total if total else 0
            elapsed = max(now - start, 1e-3)
            task.speed = (done - first[0]) / elapsed
            task.eta = (total - done) / task.speed if task.speed and total else None
            task.detail = f"{done / 1e6:,.0f} / {total / 1e6:,.0f} MB"
        return report

    def running(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def start(self, tasks: list[Task]) -> None:
        if self.running():
            raise RuntimeError("Kurulum zaten sürüyor.")
        self.tasks = tasks
        self.stop_requested = False
        self.thread = threading.Thread(target=self._run_all, daemon=True)
        self.thread.start()

    def retry_failed(self) -> None:
        for t in self.tasks:
            if t.status == "failed":
                t.status, t.error, t.progress = "pending", "", 0.0
        self.thread = threading.Thread(target=self._run_all, daemon=True)
        self.thread.start()

    def _run_all(self) -> None:
        try:
            for task in self.tasks:
                if task.status in ("done", "skipped"):
                    continue
                task.status, task.error = "running", ""
                try:
                    result = task._run(task)
                    task.status = "skipped" if result == "skipped" else "done"
                    task.progress = 1.0
                    task.eta = None
                except Exception as e:  # keep going with the other tasks
                    task.status, task.error = "failed", str(e)[:400]
        finally:
            self.stop_ollama()
            if self.on_finish:
                self.on_finish(self.tasks)

    # -------------------------------------------------------- shared ollama
    def ensure_ollama(self, env: dict | None = None):
        sys.path.insert(0, str(APP_DIR))
        from ollama_runtime import OllamaProcess

        if self.ollama and self.ollama.running():
            return self.ollama
        self.ollama = OllamaProcess(env=env, log_name="ollama-setup.log")
        if not self.ollama.start():
            raise RuntimeError("Ollama başlatılamadı (logs/ollama-setup.log).")
        return self.ollama

    def stop_ollama(self) -> None:
        if self.ollama:
            self.ollama.stop()
            self.ollama = None


installer = Installer()


def _pip(args: list[str], task: Task, expected_lines: int = 60) -> None:
    """pip with rough progress (pip prints one line per package step)."""
    # --no-cache-dir: the packages live in this folder; a second copy in the user's pip cache is wasted space.
    cmd = [sys.executable, "-m", "pip", *args, "--disable-pip-version-check", "--no-warn-script-location",
           "--no-cache-dir"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    lines, tail = 0, []
    for line in proc.stdout:
        lines += 1
        line = line.strip()
        tail = (tail + [line])[-15:]
        if line.startswith(("Collecting", "Downloading", "Installing", "Successfully")):
            task.detail = line[:120]
        task.progress = min(0.95, lines / expected_lines)
    if proc.wait() != 0:
        raise RuntimeError("pip hatası: " + " | ".join(tail[-4:]))


def task_python_packages(nvidia: bool) -> Task:
    def run(task: Task):
        _pip(["install", "-r", str(APP_DIR / "requirements.txt")], task)
        if nvidia:  # cuBLAS for Whisper on the GPU (~900 MB); not needed elsewhere
            _pip(["install", "-r", str(APP_DIR / "requirements-cuda.txt")], task, expected_lines=10)
    return Task("python", "Python paketleri" + (" (+ NVIDIA CUDA)" if nvidia else ""),
                size=int((1.3e9 if nvidia else 0.35e9)), _run=run)


def task_ollama_runtime(force: bool = False, gpu_names: list[str] = ()) -> Task:
    sys.path.insert(0, str(APP_DIR))
    from ollama_runtime import has_amd_gpu, missing_gpu_libs, prune_gpu_libs

    # The ROCm libraries are removed on computers without an AMD GPU; an AMD one needs them back.
    force = force or missing_gpu_libs(gpu_names)

    def run(task: Task):
        if OLLAMA_EXE.exists() and not force:
            task.detail = "zaten kurulu"
            return "skipped"
        target = RUNTIME_OLLAMA
        tmp = target.with_name("ollama.new")
        shutil.rmtree(tmp, ignore_errors=True)
        if IS_WINDOWS:
            zip_path = DOWNLOADS / "ollama-windows-amd64.zip"
            download(OLLAMA_CATALOG["url"], zip_path, progress=installer._progress(task),
                     should_stop=lambda: installer.stop_requested)
            task.detail = "Açılıyor…"
            with zipfile.ZipFile(zip_path) as z:
                members = z.infolist()
                for i, m in enumerate(members, 1):
                    z.extract(m, tmp)
                    task.progress = i / len(members)
            zip_path.unlink(missing_ok=True)
        else:
            # Linux: bin/ollama + lib/ollama (CUDA/Vulkan); AMD cards need the separate ROCm archive too.
            parts = [("ollama-linux-amd64.tar.zst", OLLAMA_CATALOG["url"])]
            if has_amd_gpu(gpu_names):
                parts.append(("ollama-linux-amd64-rocm.tar.zst", OLLAMA_CATALOG["rocm_url"]))
            for name, url in parts:
                archive = DOWNLOADS / name
                task.detail = f"İndiriliyor: {name}"
                download(url, archive, progress=installer._progress(task),
                         should_stop=lambda: installer.stop_requested)
                task.detail = f"Açılıyor: {name}"
                extract_tar_zst(archive, tmp, task)
                archive.unlink(missing_ok=True)
        if target.exists():
            shutil.rmtree(target.with_name("ollama.old"), ignore_errors=True)
            target.rename(target.with_name("ollama.old"))
        tmp.rename(target)
        shutil.rmtree(target.with_name("ollama.old"), ignore_errors=True)
        prune_gpu_libs(gpu_names)
        task.detail = "kuruldu"
    return Task("ollama", "Ollama (dil modeli sunucusu)", size=int(OLLAMA_CATALOG["download_gb"] * 1e9), _run=run)


RUNTIME_OLLAMA = ROOT_DIR / "runtime" / "ollama"


def extract_tar_zst(archive: Path, dest: Path, task: "Task | None" = None) -> None:
    """Unpack a .tar.zst (Ollama's Linux archives) with the zstandard package: Linux systems do not always
    have the zstd program, and nothing is installed system-wide. Keeps the files' permissions (the ollama
    program stays executable) and the library symlinks; refuses paths outside dest (tarfile's data filter)."""
    import zstandard

    dest.mkdir(parents=True, exist_ok=True)
    total = archive.stat().st_size or 1
    with open(archive, "rb") as raw, zstandard.ZstdDecompressor().stream_reader(raw) as stream, \
            tarfile.open(fileobj=stream, mode="r|") as tar:
        for member in tar:
            tar.extract(member, dest, filter="data")
            if task:
                task.progress = min(0.99, raw.tell() / total)


def task_llm(model: str, size: int, copy_from: str | None, ollama_env: dict | None) -> Task:
    def run(task: Task):
        if ollama_models.has_model(OLLAMA_MODELS_DIR, model):
            task.detail = "zaten kurulu"
            return "skipped"
        if copy_from:  # reuse a model a system-wide Ollama already downloaded
            task.detail = "Bilgisayarındaki kopyadan alınıyor…"
            ollama_models.copy_model(model, Path(copy_from), OLLAMA_MODELS_DIR, installer._progress(task))
            return None
        ollama = installer.ensure_ollama(ollama_env)
        req = urllib.request.Request(f"{ollama.url}/api/pull", method="POST",
                                     data=json.dumps({"model": model, "stream": True}).encode(),
                                     headers={"Content-Type": "application/json"})
        report = installer._progress(task)
        with urllib.request.urlopen(req, timeout=3600) as r:
            for line in r:
                ev = json.loads(line)
                if ev.get("error"):
                    raise RuntimeError(ev["error"])
                if ev.get("total"):
                    report(ev.get("completed", 0), ev["total"])
                elif ev.get("status"):
                    task.detail = ev["status"]
                if installer.stop_requested:
                    raise Cancelled()
    return Task(f"llm:{model}", f"Dil modeli: {model}", size=0 if copy_from else size, _run=run)


def whisper_dir(name: str) -> Path:
    return STT_MODELS_DIR / name


def task_whisper(name: str) -> Task:
    info = next(w for w in CATALOG["whisper_models"] if w["id"] == name)

    def run(task: Task):
        target = whisper_dir(name)
        if (target / "model.bin").exists():
            task.detail = "zaten kurulu"
            return "skipped"
        with _request(f"https://huggingface.co/api/models/{info['repo']}/tree/main") as r:
            files = [f for f in json.load(r) if f["type"] == "file" and f["path"] not in (".gitattributes", "README.md")]
        total = sum(f["size"] for f in files)
        done = 0
        report = installer._progress(task)
        tmp = target.with_name(name + ".partial")
        for f in files:
            base = done
            download(f"https://huggingface.co/{info['repo']}/resolve/main/{f['path']}", tmp / f["path"],
                     size=f["size"], sha256=(f.get("lfs") or {}).get("oid"),
                     progress=lambda d, t, base=base: report(base + d, total),
                     should_stop=lambda: installer.stop_requested)
            done += f["size"]
        tmp.rename(target)
    return Task(f"whisper:{name}", f"Konuşma tanıma: Whisper {name}", size=info["download_mb"] * 10**6, _run=run)


def task_kokoro(verify: bool = False) -> Task:
    """verify=True (repair) also checks the SHA256 of files that look complete."""
    files = CATALOG["kokoro"]["files"]

    def run(task: Task):
        target = TTS_MODELS_DIR / "kokoro"
        total = sum(f["size"] for f in files)
        complete = all((target / f["name"]).exists() and (target / f["name"]).stat().st_size == f["size"]
                       for f in files)
        if complete and not verify:
            task.detail = "zaten kurulu"
            return "skipped"
        report, done = installer._progress(task), 0
        for f in files:
            base = done
            download(f["url"], target / f["name"], size=f["size"], sha256=f["sha256"],
                     progress=lambda d, t, base=base: report(base + d, total),
                     should_stop=lambda: installer.stop_requested)
            done += f["size"]
    return Task("kokoro", "Ses (Kokoro TTS)", size=sum(f["size"] for f in files), _run=run)


def task_dictionary() -> Task:
    def run(task: Task):
        from . import build_dictionary as bd

        if bd.DB_PATH.exists():
            task.detail = "zaten kurulu"
            return "skipped"
        report = installer._progress(task)

        def stage(name: str, fraction: float) -> None:
            # download = first 80 %, processing = last 20 %
            task.progress = fraction * 0.8 if name.startswith("İndir") else 0.8 + fraction * 0.2
            task.detail = f"{name} %{fraction * 100:.0f}"
        source = bd.download(stage)
        bd.build(source, stage)
        source.unlink(missing_ok=True)
    return Task("dictionary", "Çevrimdışı İngilizce–Türkçe sözlük", size=int(0.52e9), _run=run)


def task_shortcut() -> Task:
    if not IS_WINDOWS:
        return task_shortcut_linux()

    def run(task: Task):
        target = ROOT_DIR / "Baslat.bat"
        icon = APP_DIR / "frontend" / "icon.ico"  # the app's logo (also the app window's icon)
        script = (
            "$d=[Environment]::GetFolderPath('Desktop');"
            "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'English Practice.lnk'));"
            f"$s.TargetPath='{target}';$s.WorkingDirectory='{ROOT_DIR}';"
            f"$s.IconLocation='{icon},0';"
            "$s.Description='Yerel İngilizce pratik uygulaması';$s.Save()"
        )
        out = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True,
                             creationflags=NO_WINDOW)
        if out.returncode != 0:
            raise RuntimeError(out.stderr.strip()[:300] or "Kısayol oluşturulamadı.")
    return Task("shortcut", "Masaüstü kısayolu", _run=run)


def _xdg_dir(kind: str, fallback: str) -> Path:
    """A user folder (DESKTOP, DOWNLOAD…) in the desktop's language: ~/Masaüstü, ~/İndirilenler…"""
    try:
        out = subprocess.run(["xdg-user-dir", kind], capture_output=True, text=True, timeout=5).stdout.strip()
        if out and out != str(Path.home()):
            return Path(out)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return Path.home() / fallback


def desktop_entry() -> str:
    """The launcher entry (freedesktop .desktop): opens a terminal that runs baslat.sh, like the black window
    on Windows (Ctrl+C there closes the app). The icon is the app's logo; StartupWMClass groups the app window
    (Chromium --class=EnglishPractice) under it."""
    return "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Name=English Practice",
        "Comment=Yerel İngilizce pratik uygulaması",
        f'Exec=bash "{ROOT_DIR / script("start")}"',
        f"Path={ROOT_DIR}",
        f"Icon={APP_DIR / 'frontend' / 'icon-512.png'}",
        "Terminal=true",
        "Categories=Education;Languages;",
        "StartupWMClass=EnglishPractice",
        "",
    ])


def task_shortcut_linux() -> Task:
    def run(task: Task):
        entry = desktop_entry()
        menu = Path.home() / ".local" / "share" / "applications" / "english-practice.desktop"
        written = []
        for path in (menu, _xdg_dir("DESKTOP", "Desktop") / "english-practice.desktop"):
            if path.parent.is_dir() or path == menu:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(entry, encoding="utf-8")
                path.chmod(0o755)  # desktops only start "trusted" (executable) entries
                written.append(path)
        task.detail = ", ".join(str(p) for p in written)
    return Task("shortcut", "Uygulama menüsü ve masaüstü kısayolu", _run=run)


def free_disk_gb() -> float:
    return shutil.disk_usage(ROOT_DIR).free / 1e9


def path_problem(path: Path = ROOT_DIR) -> str | None:
    """The folder path must be ASCII without spaces (some tools break otherwise)."""
    text = str(path)
    if not text.isascii():
        return "Klasör yolunda Türkçe/özel karakter var"
    if " " in text:
        return "Klasör yolunda boşluk var"
    return None


def cleanup_downloads() -> None:
    if DOWNLOADS.exists() and not any(DOWNLOADS.glob("*.part")):
        shutil.rmtree(DOWNLOADS, ignore_errors=True)


__all__ = ["CATALOG", "DATA_DIR", "download", "installer", "catalog_for", "registry_size"]
