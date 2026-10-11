"""The frontend scripts share one global scope (plain <script> tags): a top-level function or const with the
same name in two files silently replaces the other (words.js once broke the exam page this way).
Usage: python frontend_names_test.py"""

import re
import sys
from collections import defaultdict
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ✓ on a Windows (cp1254) console

FRONTEND = Path(__file__).resolve().parents[2] / "app" / "frontend"
TOP_LEVEL = re.compile(r"^(?:async\s+)?(?:function\s*\*?\s*|(?:const|let|var|class)\s+)([A-Za-z_$][\w$]*)", re.M)

names = defaultdict(list)
for js in sorted(FRONTEND.glob("*.js")):
    for m in TOP_LEVEL.finditer(js.read_text(encoding="utf-8")):
        line = js.read_text(encoding="utf-8")[:m.start()].count("\n") + 1
        names[m.group(1)].append(f"{js.name}:{line}")
clashes = {n: where for n, where in names.items() if len(where) > 1}
for n, where in sorted(clashes.items()):
    print(f"✗ {n}: {', '.join(where)}")
print(f"{len(names)} global ad, çakışma yok ✓" if not clashes else f"{len(clashes)} çakışma")
sys.exit(1 if clashes else 0)
