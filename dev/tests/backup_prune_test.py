"""Old backups are deleted (backend/backup.py prune), offline in a temporary folder: before-something backups
after 30 days, conflict copies after 90 days, the newest 5 of each kind always stay, leftover -wal/-shm files go,
daily backups keep the newest 14. Never touches the real data. Usage: python backup_prune_test.py"""

import os
import sys
import tempfile
import time
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ✓ on a Windows (cp1254) console

os.environ["EP_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))
from backend import backup, db  # noqa: E402
from backend.config import BACKUP_DIR  # noqa: E402

problems = []


def check(ok, what):
    print(("✓ " if ok else "✗ ") + what)
    if not ok:
        problems.append(what)


def make(name: str, days_old: float) -> Path:
    p = BACKUP_DIR / name
    p.write_bytes(b"x")
    t = time.time() - days_old * 86400
    os.utime(p, (t, t))
    return p


BACKUP_DIR.mkdir(parents=True, exist_ok=True)
# before-something backups: 8 of them, ages 1…80 days
pre = [make(f"pre-feature{i}-2026.db", age) for i, age in enumerate((1, 5, 10, 20, 29, 31, 45, 80))]
# conflict copies: 7 of them, ages 2…200 days
conflict = [make(f"cakisma-PC-{i}.db", age) for i, age in enumerate((2, 10, 40, 85, 95, 120, 200))]
# a backup with the -wal/-shm SQLite leaves next to it when opened, and one whose backup is gone
make("pre-feature0-2026.db-wal", 2)
make("pre-feature0-2026.db-shm", 0)
make("gone-2026.db-wal", 0)

deleted = backup.prune()
left = {p.name for p in BACKUP_DIR.iterdir()}
check({p.name for p in pre[:5]} <= left, "son 5 'önce' yedeği yaşından bağımsız kalır")
check(pre[5].name not in left and pre[6].name not in left and pre[7].name not in left,
      "30 günden eski 'önce' yedekleri (en yeni 5'in dışındakiler) silindi")
check({p.name for p in conflict[:5]} <= left, "son 5 çakışma yedeği kalır (95 günlük olan dahil)")
check(conflict[5].name not in left and conflict[6].name not in left, "90 günden eski çakışma yedekleri silindi")
check("gone-2026.db-wal" not in left and "pre-feature0-2026.db-wal" not in left,
      "yedeği olmayan ya da eski -wal/-shm dosyaları silindi")
check("pre-feature0-2026.db-shm" in left, "yeni (açık olabilecek) -shm dosyasına dokunulmadı")
check(set(deleted) == ({p.name for p in pre[5:]} | {p.name for p in conflict[5:]}
                       | {"gone-2026.db-wal", "pre-feature0-2026.db-wal"}), "silinenler listelendi")

# daily backups: the newest 14 stay (prune runs with them)
for i in range(20):
    make(f"daily-202609{i + 1:02d}.db", 40 - i)
db.init_db()
backup.daily_backup()
daily = sorted(p.name for p in BACKUP_DIR.glob("daily-*.db"))
check(len(daily) == backup.KEEP_DAILY and daily[-1].startswith("daily-2026") and "daily-20260901.db" not in daily,
      f"günlük yedeklerden en yeni {backup.KEEP_DAILY} tanesi kalır")
check(any(p.name.startswith("pre-feature") for p in BACKUP_DIR.iterdir()), "açılışta temizlik 'önce' yedeklerinin hepsini silmez")

print("Sorun yok ✓" if not problems else f"{len(problems)} sorun")
sys.exit(1 if problems else 0)
