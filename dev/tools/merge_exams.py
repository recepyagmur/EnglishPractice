"""Add new exam items (written to separate files) to the level exams and turn every part into a pool.

    runtime\\python\\python.exe dev\\tools\\merge_exams.py <folder with new_<LEVEL>.json> [LEVEL ...]

new_<LEVEL>.json: {"grammar": [...], "dictation": [...], "comprehension": [...], "speaking": [...], "writing": [...]}
(new items only; ids continue the existing ones). The existing items stay first and unchanged; the counts an
attempt asks are set to the number of items the exam had before (so its length does not change), and the single
writing task becomes the first of a list ("w1"). Also used to re-format a file: with no new file it only rewrites.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXAMS = ROOT / "app" / "content" / "exams"
KEY_ORDER = ["_comment", "title_tr", "grammar_count", "tts_speed", "grammar", "listening", "speaking_count",
             "speaking", "writing"]


def dump(exam: dict) -> str:
    """Indented JSON with one grammar question per line (easy to read and diff)."""
    keys = [k for k in KEY_ORDER if k in exam] + [k for k in exam if k not in KEY_ORDER]
    parts = []
    for k in keys:
        if k == "grammar":
            body = ",\n".join("    " + json.dumps(q, ensure_ascii=False) for q in exam[k])
            parts.append(f'  "grammar": [\n{body}\n  ]')
        else:
            value = json.dumps(exam[k], ensure_ascii=False, indent=2).replace("\n", "\n  ")
            parts.append(f"  {json.dumps(k)}: {value}")
    return "{\n" + ",\n".join(parts) + "\n}\n"


def to_pools(exam: dict) -> dict:
    """The old format (fixed parts) → pools with counts."""
    listening = exam["listening"]
    if "dictation_count" not in listening:
        exam["listening"] = {"dictation_count": len(listening["dictation"]),
                             "comprehension_count": len(listening["comprehension"]), **listening}
    exam.setdefault("speaking_count", len(exam["speaking"]))
    if isinstance(exam["writing"], dict):
        exam["writing"] = [{"id": "w1", **exam["writing"]}]
    return exam


def merge(level: str, folder: Path | None) -> None:
    path = EXAMS / f"{level}.json"
    exam = to_pools(json.loads(path.read_text(encoding="utf-8")))
    new_file = folder / f"new_{level}.json" if folder else None
    if new_file and new_file.exists():
        new = json.loads(new_file.read_text(encoding="utf-8-sig"))
        ids = {q["id"] for q in exam["grammar"]}
        if ids & {q["id"] for q in new["grammar"]}:
            sys.exit(f"{level}: new grammar ids already in the exam (merged before?)")
        exam["grammar"] += new["grammar"]
        exam["listening"]["dictation"] += new["dictation"]
        exam["listening"]["comprehension"] += new["comprehension"]
        exam["speaking"] += new["speaking"]
        exam["writing"] += new["writing"]
    # Keep lesson order: questions grouped by lesson as in the lesson file, new ones after the old ones.
    lesson_order = [l["id"] for l in json.loads((ROOT / "app/content/lessons" / f"{level}.json")
                                                  .read_text(encoding="utf-8"))["lessons"]]
    exam["grammar"].sort(key=lambda q: lesson_order.index(q["lesson"]) if q["lesson"] in lesson_order else 999)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(dump(exam))
    print(f"{level}: {len(exam['grammar'])} grammar, {len(exam['listening']['dictation'])} dictation, "
          f"{len(exam['listening']['comprehension'])} texts, {len(exam['speaking'])} speaking, "
          f"{len(exam['writing'])} writing")


if __name__ == "__main__":
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] != "-" else None
    for lv in sys.argv[2:] or ["A1", "A2", "B1", "B2", "C1"]:
        merge(lv, folder)
