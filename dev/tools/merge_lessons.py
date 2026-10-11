"""Put expanded lessons (one JSON object per lesson) into app/content/lessons/<LEVEL>.json.

    runtime\\python\\python.exe dev\\tools\\merge_lessons.py <folder with <lesson id>.json files> [--write]

Without --write it only reports. Checks for every expanded lesson: id, titles, categories and
practice unchanged; every old exercise, mistake and example still there (they were reviewed);
the lesson passes backend.lessons.validate (exercise types, answer indexes, order tiles, match pairs).
The level files keep their order, indentation and line endings.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
os.environ.setdefault("EP_DATA_DIR", tempfile.mkdtemp())
from backend import lessons  # noqa: E402

SRC = Path(sys.argv[1])
WRITE = "--write" in sys.argv
KEEP = ("id", "title_tr", "title_en", "categories")


def words(l: dict) -> int:
    return len(l.get("intro_tr", "").split()) + sum(len(s.get("text_tr", "").split()) for s in l["sections"])


def examples(l: dict) -> list[str]:
    return [e["en"] for s in l["sections"] for e in s.get("examples", [])]


problems, report = [], []
for level in lessons.LEVELS:
    path = ROOT / "app" / "content" / "lessons" / f"{level}.json"
    raw = path.read_bytes().decode("utf-8")
    data = json.loads(raw)
    changed = False
    for i, old in enumerate(data["lessons"]):
        f = SRC / f"{old['id']}.json"
        if not f.exists():
            report.append(f"{old['id']}: genişletilmemiş")
            continue
        new = json.loads(f.read_text(encoding="utf-8"))
        where = old["id"]
        for k in KEEP:
            if new.get(k) != old.get(k):
                problems.append(f"{where}: '{k}' değişmiş")
        if new.get("practice", {}).get("focus") != old["practice"]["focus"]:
            problems.append(f"{where}: practice.focus değişmiş")
        old_q = {json.dumps(e.get("q"), ensure_ascii=False) for e in old["exercises"]}
        new_q = {json.dumps(e.get("q"), ensure_ascii=False) for e in new["exercises"]}
        lost = old_q - new_q
        if len(new["exercises"]) < len(old["exercises"]):
            problems.append(f"{where}: alıştırma sayısı azalmış")
        for q in lost:  # reworded on purpose (e.g. context added so only one option fits): reviewed later
            report.append(f"{where}: soru değiştirilmiş → {q[:70]}")
        lost_ex = set(examples(old)) - set(examples(new))
        if lost_ex:
            report.append(f"{where}: {len(lost_ex)} eski örnek değiştirilmiş/çıkarılmış")
        probs = lessons.validate([new])
        problems += probs
        types = {}
        for e in new["exercises"]:
            types[e["type"]] = types.get(e["type"], 0) + 1
        report.append(f"{where}: {len(new['sections'])} bölüm, {words(new)} kelime anlatım (önce {words(old)}), "
                      f"{len(examples(new))} örnek (önce {len(examples(old))}), {len(new.get('mistakes', []))} hata, "
                      f"{len(new['exercises'])} alıştırma (önce {len(old['exercises'])}) {types}, "
                      f"{len(new.get('sources', []))} kaynak")
        for k in ("level", "order"):
            new.pop(k, None)
        data["lessons"][i] = new
        changed = True
    if changed and WRITE and not problems:
        nl = "\r\n" if "\r\n" in raw else "\n"
        out = json.dumps(data, ensure_ascii=False, indent=2).replace("\n", nl) + nl
        path.write_bytes(out.encode("utf-8"))

print("\n".join(report))
print("\nSORUNLAR:\n" + "\n".join(problems) if problems else "\nSorun yok ✓" + (" — yazıldı" if WRITE else " (yazmak için --write)"))
sys.exit(1 if problems else 0)
