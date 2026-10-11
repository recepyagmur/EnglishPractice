"""Two computers through a cloud folder (backend/sync.py), offline: two data folders, two computer names and a
temporary folder standing for Google Drive. Never touches the real data. Usage: python sync_test.py"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ✓ on a Windows (cp1254) console

APP = str(Path(__file__).resolve().parents[2] / "app")
TMP = Path(tempfile.mkdtemp())
CLOUD = TMP / "drive" / "EnglishPractice"
(TMP / "drive").mkdir()
PCS = {"MASAUSTU": TMP / "desk", "LAPTOP": TMP / "lap"}
PRE = (f"import sys, json; sys.path.insert(0, {APP!r}); sys.stdout.reconfigure(encoding='utf-8')\n"
       "from backend import db, sync, vocab\nfrom backend.db import get_conn\ndb.init_db()\n"
       "def words():\n    with get_conn() as c: return sorted(r[0] for r in c.execute('SELECT word FROM vocab'))\n")
problems = []


def run(pc: str, code: str) -> str:
    env = {**os.environ, "EP_DATA_DIR": str(PCS[pc]), "COMPUTERNAME": pc}
    out = subprocess.run([sys.executable, "-c", PRE + code], env=env, capture_output=True, text=True, encoding="utf-8")
    if out.returncode:
        raise RuntimeError(f"{pc}: {out.stderr[-1500:]}")
    return out.stdout.strip()


def add(pc: str, word: str) -> None:
    run(pc, f"vocab.add({word!r})")


def words(pc: str) -> list:
    return json.loads(run(pc, "print(json.dumps(words()))"))


def check(ok, what):
    print(("✓ " if ok else "✗ ") + what)
    if not ok:
        problems.append(what)


# 1. Desktop turns it on (its data goes up); the laptop turns it on and takes the desktop's data.
add("MASAUSTU", "meeting")
add("LAPTOP", "laptop-only")
r = run("MASAUSTU", f"print(json.dumps(sync.setup({str(CLOUD)!r})))")
check(json.loads(r) == {"choose": False} and (CLOUD / "app.db").exists(), "masaüstü açtı: veri buluta gitti")
r = json.loads(run("LAPTOP", f"print(json.dumps(sync.setup({str(CLOUD)!r})))"))
check(r.get("choose") and r["cloud"]["machine"] == "MASAUSTU", "laptop açtı: buluttaki masaüstü verisi soruldu")
run("LAPTOP", "sync.choose('pull')")
check(words("LAPTOP") == ["meeting"], "laptop buluttakini aldı (kendi eski verisi yedekte)")
check(any(p.name.startswith("pre-sync") for p in (PCS["LAPTOP"] / "backups").iterdir()), "almadan önce yedek alındı")

# 2. Normal use: work on the laptop, close it; the desktop opens and gets it.
run("LAPTOP", "print(sync.sync_on_open())")
add("LAPTOP", "deadline")
run("LAPTOP", "sync.release()")
out = run("MASAUSTU", "print(sync.sync_on_open())")
check(words("MASAUSTU") == ["deadline", "meeting"] and "LAPTOP" in out, "masaüstü açılışta laptoptaki çalışmayı aldı")
out = run("MASAUSTU", "print(sync.sync_on_open())")
check(out == "[]", "değişiklik yoksa tekrar almaz")

# 3. Lock: open on the desktop → the laptop sees it; closed → gone.
run("MASAUSTU", "sync.touch_lock()")
check(run("LAPTOP", "print((sync.other_computer_open() or {}).get('machine'))") == "MASAUSTU", "öbür bilgisayarda açık uyarısı")
add("MASAUSTU", "invoice")
run("MASAUSTU", "sync.release()")
check(run("LAPTOP", "print(sync.other_computer_open())") == "None", "kapanınca uyarı kalkar")
run("LAPTOP", "print(sync.sync_on_open())")
check(words("LAPTOP") == ["deadline", "invoice", "meeting"], "laptop masaüstünün son halini aldı")

# 4. Worked on both without closing: the newer wins, the other is kept in backups.
add("MASAUSTU", "desk-change")
run("MASAUSTU", "sync.push()")
import time
time.sleep(1.2)
add("LAPTOP", "lap-change")  # newer
out = run("LAPTOP", "print(sync.sync_on_open())")
check("daha yeni veri gönderildi" in out and "lap-change" in words("LAPTOP"), "çakışma: daha yeni olan (laptop) kaldı")
kept = [p for p in (PCS["LAPTOP"] / "backups").iterdir() if p.name.startswith("cakisma-MASAUSTU")]
check(len(kept) == 1, "çakışma: masaüstünün hali yedeğe kondu (cakisma-MASAUSTU-…)")
run("MASAUSTU", "print(sync.sync_on_open())")
check("lap-change" in words("MASAUSTU"), "masaüstü sonra laptopun halini aldı")

# 5. Google Drive has not finished downloading (hash differs): nothing is replaced.
add("LAPTOP", "fresh")
run("LAPTOP", "sync.release()")
good = (CLOUD / "app.db").read_bytes()
(CLOUD / "app.db").write_bytes(good[: len(good) // 2])
before = words("MASAUSTU")
out = run("MASAUSTU", "\ntry:\n    sync.sync_on_open(); print('pulled')\nexcept sync.SyncError as e:\n    print('error', e)")
check(out.startswith("error") and words("MASAUSTU") == before, "yarım indirilmiş dosya alınmaz, yerel veri korunur")
(CLOUD / "app.db").write_bytes(good)

# 6. Data saved by a newer app version (higher schema): not taken.
meta = json.loads((CLOUD / "sync.json").read_text(encoding="utf-8"))
(CLOUD / "sync.json").write_text(json.dumps({**meta, "schema": 999}), encoding="utf-8")
out = run("MASAUSTU", "\ntry:\n    sync.sync_on_open(); print('pulled')\nexcept sync.SyncError as e:\n    print('error', e)")
check("güncelle" in out.lower(), "daha yeni sürümün verisi alınmaz (önce güncelle)")
(CLOUD / "sync.json").write_text(json.dumps(meta), encoding="utf-8")
run("MASAUSTU", "print(sync.sync_on_open())")
check("fresh" in words("MASAUSTU"), "sonra normal alınır")

leftovers = [p.name for p in CLOUD.iterdir() if p.name.endswith(("-wal", "-shm", ".tmp"))]
check(not leftovers, f"bulut klasöründe yalnız app.db / sync.json / lock.json (artık dosya yok: {leftovers})")

# 7. Off: nothing is exchanged any more.
run("MASAUSTU", "sync.turn_off()")
check(run("MASAUSTU", "print(sync.enabled())") == "False", "kapatılınca eşitleme yapılmaz")

print("Sorun yok ✓" if not problems else f"{len(problems)} sorun")
sys.exit(1 if problems else 0)
