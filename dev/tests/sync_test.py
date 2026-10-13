"""Two computers through a cloud folder (backend/sync.py), offline: two data folders, two computer names and a
temporary folder standing for Google Drive. Never touches the real data. Usage: python sync_test.py"""

import json
import os
import time
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
check("Bu bilgisayardaki daha yeni veri" in out and "lap-change" in words("LAPTOP"), "çakışma: daha yeni olan (laptop) kaldı")
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

# 8. The other computer sends week-old data (it had not taken the newer work first): never taken over newer work.
def cloud_meta():
    return json.loads((CLOUD / "sync.json").read_text(encoding="utf-8"))


def backups(pc, prefix):
    return [p for p in (PCS[pc] / "backups").iterdir() if p.name.startswith(prefix)]


run("LAPTOP", "print(sync.sync_on_open())")  # both have the same data now
for old_app in (True, False):  # sent by an older app version (no lineage) / by this version
    time.sleep(1.2)
    add("MASAUSTU", f"newer-{old_app}")
    run("MASAUSTU", "sync.release()")
    run("LAPTOP", "sync.push(force=True)")  # the laptop's older data replaces the cloud's
    if old_app:
        (CLOUD / "sync.json").write_text(json.dumps({k: v for k, v in cloud_meta().items()
                                                     if k not in ("lineage", "activity")}), encoding="utf-8")
    before = len(backups("MASAUSTU", "cakisma-LAPTOP"))
    out = run("MASAUSTU", "print(sync.sync_on_open())")
    what = "eski uygulamadan" if old_app else "bu sürümden"
    check("eski, alınmadı" in out and f"newer-{old_app}" in words("MASAUSTU"),
          f"eski veri ({what}) yeni çalışmanın üzerine yazılmadı, uyarı verildi")
    check(len(backups("MASAUSTU", "cakisma-LAPTOP")) == before + 1 and cloud_meta()["machine"] == "MASAUSTU",
          f"eski veri ({what}) yedekte, bulutta yine yeni veri var")
    out = run("LAPTOP", "print(sync.sync_on_open())")
    check(f"newer-{old_app}" in words("LAPTOP") and "⚠" not in out, f"laptop sonra yeni veriyi sessizce aldı ({what})")

# 9. The incident: on the computer with old data, opening a page re-saved something (ui_state, newer timestamp,
# no new work) — the cloud's newer work still wins there, the old data goes to backups.
time.sleep(1.2)
add("MASAUSTU", "real-work")
run("MASAUSTU", "sync.release()")
time.sleep(1.2)
run("LAPTOP", "from backend import lessons, ui_state\nlessons.open_lesson('a1-there-is')\n"
              "ui_state.put('lesson:a1-there-is', {'exercises': {}})")
out = run("LAPTOP", "print(sync.sync_on_open())")
check("real-work" in words("LAPTOP") and "son çalışman alındı" in out and "⚠" not in out,
      "ders açmak (lesson_progress, ui_state) eski veriyi 'yeni' yapmaz: buluttaki gerçek çalışma uyarısız alındı")

# 10. Deleting is a change too: a word deleted on one computer is deleted on the other (the cloud's data is
# "older" by its newest work, but it continues what the other computer had).
run("MASAUSTU", "print(sync.sync_on_open())")
run("MASAUSTU", "with get_conn() as c: vid = c.execute(\"SELECT id FROM vocab WHERE word = 'real-work'\").fetchone()[0]\n"
                "vocab.delete(vid)")
run("MASAUSTU", "sync.release()")
out = run("LAPTOP", "print(sync.sync_on_open())")
check("real-work" not in words("LAPTOP") and "⚠" not in out, "silinen kelime öbür bilgisayarda da silindi")

# 11. Second computer's first setup: each side's latest work is reported, the newer one marked.
run("LAPTOP", "sync.turn_off()")
time.sleep(1.2)
add("LAPTOP", "laptop-newest")
r = json.loads(run("LAPTOP", f"print(json.dumps(sync.setup({str(CLOUD)!r})))"))
check(r.get("choose") and r.get("newer") == "local" and r.get("cloud_activity") and r.get("local_activity"),
      "kurulumda iki tarafın son çalışması gösterilir (yeni olan işaretli)")
run("LAPTOP", "sync.choose('push')")
out = run("MASAUSTU", "print(sync.sync_on_open())")
check("laptop-newest" in words("MASAUSTU") and "⚠" not in out, "kurulumda 'bunu gönder' seçilince öbürü onu alır")

# 12. Google Drive brings the other computer's newer data only after the app opened here.
run("LAPTOP", "print(sync.sync_on_open())")
run("MASAUSTU", "print(sync.sync_on_open())")
time.sleep(1.2)
add("MASAUSTU", "late-arrival")
run("MASAUSTU", "sync.release()")
gen = cloud_meta()["gen"]
out = run("LAPTOP", "print(sync.push(force=False))")  # the laptop's 2-minute send, before it took the new data
check(out == "False" and cloud_meta()["gen"] == gen, "açıkken gönderim, buluta sonradan gelen yeni veriyi ezmez")
out = run("LAPTOP", "sync.CHECK_EVERY = 0.2\nsync.start_background()\nimport time\ntime.sleep(2)\n"
                    "print(sync.replaced_at is not None)")
check(out == "True" and "late-arrival" in words("LAPTOP"),
      "açıkken 20 sn'de bir bakar: sonradan gelen yeni veriyi alır (sayfa yenilenir)")

# 13. Real work here while the other computer's newer data arrives: on closing, the newer wins, nothing is lost.
time.sleep(1.2)
add("MASAUSTU", "desk-later")
run("MASAUSTU", "sync.release()")
time.sleep(1.2)
add("LAPTOP", "lap-latest")  # newer than the desktop's
before = len(backups("LAPTOP", "cakisma-MASAUSTU"))
run("LAPTOP", "sync.release()")
check("lap-latest" in words("LAPTOP") and cloud_meta()["machine"] == "LAPTOP"
      and len(backups("LAPTOP", "cakisma-MASAUSTU")) == before + 1,
      "kapanışta bulutta yeni veri varsa körlemesine ezilmez: yeni olan kalır, öbürü yedekte")

# 14. Opening right after the computer starts: wait for Google Drive (folder missing / file half downloaded).
out = run("LAPTOP", "sync._save_local(dir=r'" + str(TMP / "yok" / "EnglishPractice") + "')\nimport time\nt = time.monotonic()\n"
                    "print(sync.wait_until_ready(1.5, lambda m: None), round(time.monotonic() - t))")
check(out == "False 2" or out == "False 1", f"Drive klasörü yoksa en çok verilen süre kadar bekler ({out})")
run("LAPTOP", f"sync._save_local(dir={str(CLOUD)!r})")
good = (CLOUD / "app.db").read_bytes()
(CLOUD / "app.db").write_bytes(good[: len(good) // 2])
out = run("LAPTOP", "print(sync.wait_until_ready(1, lambda m: None))")
(CLOUD / "app.db").write_bytes(good)
out2 = run("LAPTOP", "print(sync.wait_until_ready(1, lambda m: None))")
check(out == "False" and out2 == "True", "dosya yarım indirilmişse bekler, tamamlanınca hazır")

# 7. Off: nothing is exchanged any more.
run("MASAUSTU", "sync.turn_off()")
check(run("MASAUSTU", "print(sync.enabled())") == "False", "kapatılınca eşitleme yapılmaz")

print("Sorun yok ✓" if not problems else f"{len(problems)} sorun")
sys.exit(1 if problems else 0)
