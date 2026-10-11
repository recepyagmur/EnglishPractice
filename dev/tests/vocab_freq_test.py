"""Check the "⭐ En sık 3000" list (app/content/vocab/top3000.json, built by dev/tools/build_freq_list.py) as the app
loads it, and the notebook's no-duplicates rule. Usage: python vocab_freq_test.py"""

import os
import re
import sys
import tempfile
from collections import Counter
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ✓ on a Windows (cp1254) console

os.environ.setdefault("EP_DATA_DIR", tempfile.mkdtemp())  # importing the backend creates folders

from backend import db, vocab, words  # noqa: E402

db.init_db()

problems = []
F = words.FREQ
if len(F) != 3000:
    problems.append(f"{len(F)} kelime, 3000 olmalı")
keys = [vocab.word_key(w["w"]) for w in F]
for k, n in Counter(keys).items():
    if n > 1:
        problems.append(f"iki kez: {k}")
if [w["rank"] for w in F] != list(range(1, len(F) + 1)):
    problems.append("sıra numaraları 1…N ve artan olmalı")
POS = set(words.POS_TR)
NOT_WANTED = re.compile(r"^(monday|tuesday|wednesday|thursday|friday|saturday|sunday|january|february|april|june|july|"
                        r"august|september|october|november|december|two|three|four|five|six|seven|eight|nine|ten|"
                        r"eleven|twelve|twenty|thirty|forty|fifty|hundred|thousand|million|billion|zero)$")
for w in F:
    where = f"#{w['rank']} {w['w']}"
    if not w.get("tr", "").strip():
        problems.append(f"{where}: Türkçe anlam yok")
    # (level-list words keep CEFR-J's own names, e.g. "infinitive-to"; the list's own words use the app's names)
    if not w.get("pos") or (w["cefr"] is None and any(p not in POS for p in w["pos"])):
        problems.append(f"{where}: kelime türü geçersiz {w.get('pos')}")
    if NOT_WANTED.match(w["w"].lower()):
        problems.append(f"{where}: sayı/gün/ay listeye alınmıyor")
    if w["w"].lower() in {"ph", "en", "mid", "par", "ex", "fuck", "rape", "oocyte", "amongst"}:
        problems.append(f"{where}: dışarıda bırakılması gereken kelime")
    if len(w["pos"]) > 1 and w.get("cefr") is None and ";" not in w["tr"]:
        problems.append(f"{where}: birden fazla tür → \"isim: …; fiil: …\" biçimi")
# One entry per word across the level lists, whatever the case: "it" (pronoun) and "IT" (information technology)
# were once one mixed entry, and the notebook treats them as the same word.
seen = {}
for level, ws in words.WORDS.items():
    for w in ws:
        k = vocab.word_key(w["w"])
        if k in seen:
            problems.append(f"seviye listelerinde iki kez: {seen[k]} / {level} {w['w']}")
        seen[k] = f"{level} {w['w']}"
own = [w for w in F if w["cefr"] is None]
print(f"{len(F)} kelime · seviye listesinden: {len(F) - len(own)} · kendi anlamıyla: {len(own)} · "
      f"seviyeler: {dict(sorted(Counter(w['cefr'] or '—' for w in F).items()))}")
# Every list word can be learned (the notebook gets its meaning and a level).
for w in F:
    if w["w"].lower() not in words.BY_WORD:
        problems.append(f"#{w['rank']} {w['w']}: öğrenmeye eklenemez (BY_WORD'de yok)")
# No duplicates in the notebook, however the word is written.
a, new1 = vocab.add("café", meaning_tr="kafe")
b, new2 = vocab.add("Cafe")
c, new3 = vocab.add("  CAFÉ ")
if not (new1 and not new2 and not new3 and a["id"] == b["id"] == c["id"]):
    problems.append("defter: aynı kelime ikinci kez eklendi")
first = words.learn(["the"])
again = words.learn(["The", "THE"])
if len({e["id"] for e in first + again}) != 1:
    problems.append("öğrenmeye ekleme: aynı kelime iki kayıt oldu")
for p in problems[:40]:
    print("✗", p)
print("Sorun yok ✓" if not problems else f"{len(problems)} sorun")
sys.exit(1 if problems else 0)
