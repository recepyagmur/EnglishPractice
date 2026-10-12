"""In-app update (backend/updates.py), offline: a fake installation in a temporary folder, a zip made like
GitHub's archive. Never touches this repository or the real data. The download from GitHub and the launcher's
restart are tried by hand (see README "Güncelleme"). Usage: python update_test.py"""

import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ✓ on a Windows (cp1254) console

TMP = Path(tempfile.mkdtemp())
os.environ["EP_DATA_DIR"] = str(TMP / "data")
REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "app"), str(REPO)]
from backend import db, machine, updates  # noqa: E402
from setup import updater  # noqa: E402

machine.profile_path = lambda: TMP / "profile.json"  # never this computer's real profile
problems = []


def check(ok, what):
    print(("✓ " if ok else "✗ ") + what)
    if not ok:
        problems.append(what)


# A fake installation: the updater writes under ROOT only.
ROOT = TMP / "kopya"
for rel, text in {"app/launcher.py": "old", "app/old_module.py": "gone soon", "setup/installer.py": "x",
                  "Baslat.bat": "old", "data/keep.txt": "user data"}.items():
    (ROOT / rel).parent.mkdir(parents=True, exist_ok=True)
    (ROOT / rel).write_text(text, encoding="utf-8")
updater.ROOT = ROOT
updater.PACKAGE_FILES = ROOT / "config" / "package-files.txt"
updater.VERSION_FILE = ROOT / "config" / "package-version.txt"
updater.PACKAGE_FILES.parent.mkdir(parents=True)
updater.PACKAGE_FILES.write_text("app/launcher.py\napp/old_module.py\nsetup/installer.py\nBaslat.bat", encoding="utf-8")
updater.VERSION_FILE.write_text("a" * 40, encoding="utf-8")
db.init_db()


def make_zip(files: dict, commit: str) -> Path:
    updates.UPDATE_DIR.mkdir(parents=True, exist_ok=True)
    path = updates.UPDATE_DIR / "EnglishPractice-main.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.comment = commit.encode()
        for rel, text in files.items():
            z.writestr(f"EnglishPractice-main/{rel}", text)
    updates.PENDING.write_text(json.dumps({"zip": path.name, "commit": commit}), encoding="utf-8")
    return path


updates.is_dev = lambda: False  # this repository is a git checkout; the fake installation is not

# 1. The commit list on the page: wrapped lines joined again, "- " items kept, attribution left out.
c = updates._commit({"sha": "s", "commit": {"committer": {"date": "2026-10-12T19:19:49Z"}, "message":
                     "Başlık\n\nBirinci satır\nikinci satır.\n\n- madde bir\n  devamı\n- madde iki\n\n"
                     "Co-Authored-By: X <x@example.com>\n"}})
check(c["title"] == "Başlık" and c["body"] == "Birinci satır ikinci satır.\n- madde bir devamı\n- madde iki",
      "değişiklik metni: satırlar birleşir, maddeler kalır, imza satırı çıkar")

# 2. A pending update is applied: new files, removed files deleted, data untouched, version recorded, backup taken.
new = {"app/launcher.py": "new", "app/new_module.py": "added", "setup/installer.py": "x", "Baslat.bat": "new",
       "data/keep.txt": "FROM ZIP", "dev/tests/x.py": "dev only"}
zip_path = make_zip(new, "b" * 40)
said = []
ok = updates.apply_pending(said.append)
check(ok and (ROOT / "app/launcher.py").read_text(encoding="utf-8") == "new" and (ROOT / "app/new_module.py").exists(),
      "güncelleme uygulandı (değişen ve yeni dosyalar)")
check(not (ROOT / "app/old_module.py").exists(), "depodan silinen dosya silindi")
check((ROOT / "data/keep.txt").read_text(encoding="utf-8") == "user data" and not (ROOT / "dev").exists(),
      "data/ ve geliştirme dosyalarına dokunulmadı")
check(updates.current_version() == "b" * 40, "yeni sürüm kaydedildi")
check(not updates.PENDING.exists() and not zip_path.exists(), "bekleyen güncelleme ve zip silindi")
check(any(p.name.startswith("pre-update") for p in (TMP / "data" / "backups").iterdir()), "önce veri yedeği alındı")
check(any("Güncellendi" in s for s in said), f"mesaj: {said[-1] if said else '—'}")

# 3. Nothing pending: nothing happens (the app opens normally).
check(updates.apply_pending(said.append) is False, "bekleyen güncelleme yoksa bir şey yapılmaz")

# 4. A broken zip: not applied, the pending record is gone (the app still opens), files unchanged.
make_zip({"README.md": "not the app"}, "c" * 40)
check(updates.apply_pending(said.append) is False and updates.current_version() == "b" * 40
      and not updates.PENDING.exists(), "bozuk/yabancı zip uygulanmaz, uygulama yine açılır")

# 5. A development copy (git repository) is never updated this way.
updates.is_dev = lambda: True
make_zip(new, "d" * 40)
check(updates.apply_pending(said.append) is False and updates.current_version() == "b" * 40,
      "geliştirme kopyasında (git) güncelleme uygulanmaz")
try:
    updates.start_update()
    check(False, "geliştirme kopyasında 'Güncelle' reddedilir")
except updates.UpdateError:
    check(True, "geliştirme kopyasında 'Güncelle' reddedilir")
check(updates.status()["dev"] is True, "durum: geliştirme kopyası")

# 6. Checking on opening can be turned off per computer.
updates.is_dev = lambda: False
updates.set_enabled(False)
check(updates.enabled() is False, "açılışta denetleme kapatılabilir")
updates.set_enabled(True)
check(updates.enabled() is True, "yeniden açılabilir")

print("Sorun yok ✓" if not problems else f"{len(problems)} sorun")
sys.exit(1 if problems else 0)
