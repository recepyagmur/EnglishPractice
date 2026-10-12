"""Update a shared copy of the app from the GitHub repository (Guncelle.bat / guncelle.sh).

The app itself also updates from inside (backend/updates.py: it downloads the zip and the launcher applies it
with apply() below). By hand: the script opens the archive link in the browser, waits for the zip in the
Downloads folder (or takes one given as an argument / dropped on Guncelle.bat), then replaces the app files.
Never touched: data/ (the learner's progress), runtime/, models/, logs/, config/machines/ — they are not in the
repository. Files removed from the repository are removed here too (the list of shipped files is kept in
PACKAGE_FILES). Python packages are reinstalled only when a requirements file changed.

    runtime\\python\\python.exe -m setup.updater [path\\to\\EnglishPractice-main.zip]
"""

import json
import os
import subprocess
import sys
import time
import webbrowser
import zipfile
from pathlib import Path

REPO = "recepyagmur/EnglishPractice"
BRANCH = "main"
ARCHIVE_URL = f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip"
ZIP_PREFIX = f"{REPO.split('/')[1]}-{BRANCH}"   # GitHub names the file and its top folder like this

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from backend.config import script  # noqa: E402  (Guncelle.bat on Windows, guncelle.sh on Linux)
PACKAGE_FILES = ROOT / "config" / "package-files.txt"    # what the last package/update shipped
VERSION_FILE = ROOT / "config" / "package-version.txt"   # the commit it came from
# Development files stay out of the shared copy (also used by dev/tools/make_package.py).
EXCLUDE_PREFIXES = ("dev/", "docs/sohbet-arsivi/", ".gitignore", ".gitattributes", "DEVAM.md",
                    "ek-ozellik-kurulum-sihirbazi.md", "ingilizce-pratik-uygulamasi.md")
# Never written or deleted by an update, whatever the zip contains.
PROTECTED = ("data/", "runtime/", "models/", "logs/", "config/machines/", ".git/")
REQUIREMENTS = ("app/requirements.txt", "app/requirements-cuda.txt", "setup/requirements-wizard.txt")
WAIT_MINUTES = 15


def say(msg: str = "") -> None:
    print(msg, flush=True)


def shipped(path: str) -> bool:
    return bool(path) and not path.startswith(EXCLUDE_PREFIXES) and not path.startswith(PROTECTED)


# ------------------------------------------------------------------ download

def downloads_dir() -> Path:
    """The Downloads folder, also when the user moved it (Windows keeps the real place in the registry;
    Linux desktops name it in their language, ~/İndirilenler, and xdg-user-dir knows it)."""
    if os.name != "nt":
        try:
            out = subprocess.run(["xdg-user-dir", "DOWNLOAD"], capture_output=True, text=True, timeout=5).stdout.strip()
            if out and out != str(Path.home()) and Path(out).is_dir():
                return Path(out)
        except (OSError, subprocess.TimeoutExpired):
            pass
        return Path.home() / "Downloads"
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
            value, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
            return Path(os.path.expandvars(value))
    except OSError:
        return Path.home() / "Downloads"


def enter_pressed() -> bool:
    """Did the user press Enter in this window (without waiting)? Windows: the console; Linux: the terminal."""
    try:
        import msvcrt
        return msvcrt.kbhit() and msvcrt.getwch() in "\r\n"
    except ImportError:
        import select
        try:
            if sys.stdin.isatty() and select.select([sys.stdin], [], [], 0)[0]:
                sys.stdin.readline()
                return True
        except (OSError, ValueError):
            pass
        return False


def _candidates(folder: Path, since: float) -> list[Path]:
    return sorted((p for p in folder.glob(f"{ZIP_PREFIX}*.zip") if p.stat().st_mtime >= since),
                  key=lambda p: p.stat().st_mtime, reverse=True)


def wait_for_download() -> Path | None:
    """Open the archive link in the browser and wait for the finished zip."""
    folder = downloads_dir()
    since = time.time() - 5
    say("Tarayıcıda GitHub'dan güncelleme indiriliyor:")
    say(f"  {ARCHIVE_URL}")
    say("  • GitHub'a giriş yapmadıysan önce giriş yap (\"404\" sayfası görürsen giriş yapılmamıştır ya da")
    say("    depoya davetin henüz kabul edilmemiştir), sonra bu pencerede Enter'a bas: bağlantıyı yeniden açarım.")
    say(f"  • İndirilen dosya burada aranıyor: {folder}")
    say("    (Başka bir yere kaydettiysen zip dosyasını Guncelle.bat'ın üzerine sürükleyip bırakabilirsin.)" if os.name == "nt"
        else f"    (Başka bir yere kaydettiysen: bash {script('update')} <zip dosyasının yolu>)")
    webbrowser.open(ARCHIVE_URL)
    deadline = time.time() + WAIT_MINUTES * 60
    last_size = {}
    while time.time() < deadline:
        if enter_pressed():
            say("  Bağlantı yeniden açılıyor…")
            webbrowser.open(ARCHIVE_URL)
        for p in _candidates(folder, since):
            size = p.stat().st_size
            # A browser writes to a temporary name and renames at the end; still wait until the size settles.
            if size and last_size.get(p) == size and zipfile.is_zipfile(p):
                return p
            last_size[p] = size
        time.sleep(1)
    say(f"\n{WAIT_MINUTES} dakika içinde indirilen dosya bulunamadı.")
    return None


# --------------------------------------------------------------------- apply

def read_archive(path: Path) -> tuple[dict[str, bytes], str]:
    """Files of the GitHub archive (paths without the top folder) and the commit it was made from.
    Linux: the .sh scripts are made executable when written (apply), whatever the zip says."""
    files = {}
    with zipfile.ZipFile(path) as z:
        commit = z.comment.decode("ascii", "replace").strip()[:40]  # GitHub writes the commit id there
        names = [n for n in z.namelist() if not n.endswith("/")]
        tops = {n.split("/", 1)[0] for n in names}
        if len(tops) != 1:
            raise ValueError("Zip beklenen biçimde değil (tek bir üst klasör olmalı).")
        for name in names:
            rel = name.split("/", 1)[1] if "/" in name else ""
            if shipped(rel):
                files[rel] = z.read(name)
    for must in ("app/launcher.py", "setup/installer.py", "Baslat.bat"):
        if must not in files:
            raise ValueError(f"Bu zip English Practice'in güncellemesi gibi görünmüyor ({must} yok).")
    return files, commit


def app_running() -> bool:
    sys.path.insert(0, str(ROOT / "app"))
    from backend.config import LOCK_PATH
    from ollama_runtime import pid_alive
    try:
        lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return pid_alive(int(lock.get("pid", 0)))


def backup_data() -> None:
    if (ROOT / "data" / "app.db").exists():
        sys.path.insert(0, str(ROOT / "app"))
        from backend import backup
        say(f"Verilerin yedeklendi: {backup.backup_now('pre-update')}")


def apply(files: dict[str, bytes]) -> tuple[int, int, list[str]]:
    """Write the new files, delete the ones the repository no longer has. Returns (changed, removed, changed
    requirement files)."""
    old = set(PACKAGE_FILES.read_text(encoding="utf-8").split("\n")) if PACKAGE_FILES.exists() else set()
    changed, reqs = 0, []
    for rel, data in sorted(files.items()):
        dest = ROOT / rel
        if dest.exists() and dest.read_bytes() == data:
            continue
        if rel in REQUIREMENTS:
            reqs.append(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".update-tmp")
        tmp.write_bytes(data)
        if rel.endswith(".sh") and os.name != "nt":
            tmp.chmod(0o755)
        os.replace(tmp, dest)
        changed += 1
    removed = 0
    for rel in sorted(old - set(files)):
        dest = ROOT / rel
        if shipped(rel) and dest.is_file():
            dest.unlink()
            removed += 1
            for parent in dest.parents:  # empty folders left behind
                if parent == ROOT or any(parent.iterdir()):
                    break
                parent.rmdir()
    PACKAGE_FILES.parent.mkdir(parents=True, exist_ok=True)
    PACKAGE_FILES.write_text("\n".join(sorted(files)), encoding="utf-8")
    return changed, removed, reqs


def reinstall_packages(reqs: list[str]) -> None:
    py = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location",
          "--no-cache-dir", "-r"]
    for rel in reqs:
        if rel.endswith("requirements-cuda.txt"):
            # Only where the CUDA packages were installed (NVIDIA computers).
            has_cuda = subprocess.run([sys.executable, "-m", "pip", "show", "-q", "nvidia-cublas-cu12"],
                                      capture_output=True).returncode == 0
            if not has_cuda:
                continue
        say(f"Python paketleri güncelleniyor ({rel})…")
        if subprocess.run(py + [str(ROOT / rel)]).returncode != 0:
            say(f"⚠ Paketler güncellenemedi. {script('setup')} → bakım → güncelle ile tekrar dene.")


def main() -> int:
    say("English Practice — güncelleme\n")
    if (ROOT / ".git").exists():
        say("Bu klasör geliştirme kopyası (git deposu). Güncellemek için: git pull")
        return 1
    if app_running():
        say(f"Uygulama şu an açık. Önce uygulama penceresinde Ctrl+C ile kapat, sonra {script('update')} dosyasını "
            "yeniden çalıştır.")
        return 1
    given = [a for a in sys.argv[1:] if a.lower().endswith(".zip")]
    zip_path = Path(given[0]) if given else wait_for_download()
    if zip_path is None or not zip_path.exists():
        return 1
    say(f"\nİndirilen güncelleme: {zip_path}")
    try:
        files, commit = read_archive(zip_path)
    except (ValueError, zipfile.BadZipFile) as e:
        say(f"⚠ {e}")
        return 1
    old_commit = VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.exists() else "?"
    if commit and commit == old_commit:
        say("✓ Zaten en güncel sürümü kullanıyorsun.")
        if not given:
            zip_path.unlink(missing_ok=True)
        return 0
    backup_data()
    changed, removed, reqs = apply(files)
    if commit:
        VERSION_FILE.write_text(commit, encoding="utf-8")
    if reqs:
        reinstall_packages(reqs)
    if not given:  # the copy we asked the browser to download: no need to keep it
        try:
            zip_path.unlink()
        except OSError:
            pass
    say(f"\n✓ Güncellendi ({old_commit[:7]} → {commit[:7] or '?'}): {changed} dosya değişti, {removed} dosya silindi.")
    say(f"Uygulamayı {script('start')} ile açabilirsin.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
