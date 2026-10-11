"""Check the pattern content files (app/content/patterns/*.json): structure, ids, topics, slots, that every
example really contains the pattern, category counts per level, and that no pattern repeats across levels.
Usage: python patterns_content_test.py [one file …]   (no file: all levels, the distribution must be complete)"""

import json
import os
import sys
import tempfile
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ✓ on a Windows (cp1254) console

os.environ.setdefault("EP_DATA_DIR", tempfile.mkdtemp())  # importing the backend creates folders

from backend import patterns  # noqa: E402

paths = [Path(a) for a in sys.argv[1:]] or sorted(patterns.CONTENT_DIR.glob("*.json"))
files, problems = {}, []
for path in paths:
    try:
        files[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        problems.append(f"{path.name}: not valid JSON ({e})")
# A single file is also checked against the other levels' patterns (no repeats across levels).
others = {lv: f for lv, f in patterns.FILES.items() if lv not in files}
all_files = {**others, **files}
problems += [p for p in patterns.validate(all_files) if not p.startswith(tuple(f"{lv}.json" for lv in others))]
for p in problems:
    print("✗", p)
n = sum(len(f.get("patterns", [])) for f in files.values())
print(f"{len(files)} dosya, {n} kalıp — {'sorun yok ✓' if not problems else f'{len(problems)} sorun'}")
sys.exit(1 if problems else 0)
