"""Check the YDS-style question files (app/content/yds/*.json): structure, ids, 5 options, answer index, blanks,
passage lengths, pool sizes, and that correct answers are spread over A–E.
Usage: python yds_content_test.py [one file …]   (no file: all types; each pool must be complete)"""

import json
import os
import sys
import tempfile
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ✓ on a Windows (cp1254) console

os.environ.setdefault("EP_DATA_DIR", tempfile.mkdtemp())  # importing the backend creates folders

from backend import selftest  # noqa: E402

paths = [Path(a) for a in sys.argv[1:]] or sorted(selftest.CONTENT_DIR.glob("*.json"))
files, problems = {}, []
for path in paths:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # A part file (e.g. parts/reading-01-10.json with "type": "reading") is checked without the pool size.
        files[path.stem if path.stem in selftest.TYPES else f"{data.get('type')}@{path.stem}"] = data
    except Exception as e:  # noqa: BLE001
        problems.append(f"{path.name}: not valid JSON ({e})")
problems += selftest.validate(files)
for p in problems:
    print("✗", p)
n = 0
for t, f in files.items():
    for it in f.get("items", []):
        n += len(it.get("questions", [])) if isinstance(it, dict) and "questions" in it else 1
print(f"{len(files)} dosya, {n} soru — {'sorun yok ✓' if not problems else f'{len(problems)} sorun'}")
sys.exit(1 if problems else 0)
