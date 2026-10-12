"""Lesson summary cards (app/content/review/<LEVEL>.json) against the lessons: every lesson has one, the
fields follow the rules in app/content/review/README.md. Offline.
Usage: python review_content_test.py [LEVEL …]   (default: all levels)"""

import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ✓ on a Windows (cp1254) console
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))

from backend import lessons, reviews  # noqa: E402

levels = [a.upper() for a in sys.argv[1:]] or lessons.LEVELS
problems = []
for level in levels:
    level_lessons = [l for l in lessons.LESSONS if l["level"] == level]
    if not level_lessons:
        continue
    path = reviews.CONTENT_DIR / f"{level}.json"
    if not path.exists():
        problems.append(f"{level}: {path.name} yok")
        continue
    try:
        cards = reviews.load_content([level])
    except (ValueError, KeyError) as e:
        problems.append(f"{level}: dosya okunamadı: {e}")
        continue
    found = reviews.validate_content(cards, level_lessons)
    problems += [f"{level} {p}" for p in found]
    print(f"{level}: {len(cards)} özet, {len(found)} sorun")

for p in problems:
    print("✗", p)
print("Sorun yok ✓" if not problems else f"{len(problems)} sorun")
sys.exit(1 if problems else 0)
