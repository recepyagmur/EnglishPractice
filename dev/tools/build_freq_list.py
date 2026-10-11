"""Build app/content/vocab/top3000.json: the 3000 most frequent English words for Kelime Çalış ("⭐ En sık 3000").

Sources (CC BY-SA 4.0; attribution in app/content/vocab/README.md and on the page):
- New General Service List 1.2 (Browne, C., Culligan, B. & Phillips, J.), https://www.newgeneralservicelist.com:
  NGSL_12_stats.csv (2809 words, "SFI Rank" = frequency order) and NGSLwithSFI-31K.xlsx (the same corpus' word
  frequencies beyond the NGSL). The list = the 2809 NGSL words in their rank order, then the most frequent other
  words (by SFI) up to 3000. Not included: the NGSL supplement (numbers, days, months), abbreviations and word
  fragments, profanity, very technical terms and spelling variants of NGSL words (EXCLUDE below).
- Turkish meanings: a word that is in a level list (app/content/vocab/A1–C1.json, checked by hand) uses that entry
  at run time (backend/words.py); the file carries pos / tr / ipa only for the others (MEANINGS: written and then
  checked independently, see the README).

    runtime\\python\\python.exe dev\\tools\\build_freq_list.py <folder with the NGSL files> [meanings.json]

Without meanings.json the meanings already in top3000.json are kept (they were checked by hand: edit them there).
"""

import csv
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

SRC = Path(sys.argv[1])
MEANINGS = Path(sys.argv[2]) if len(sys.argv) > 2 else None
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "app" / "content" / "vocab" / "top3000.json"
TOTAL = 3000
# Not words a learner should drill from a frequency list (see the docstring).
EXCLUDE = {"ph", "en", "mid", "par", "ex", "fuck", "rape", "oocyte", "amongst", "zero"}
# The form learners meet (the corpus lemma is rare on its own).
RENAME = {"headquarter": "headquarters", "sophisticate": "sophisticated",
          # the level lists' spelling of the same word: one notebook entry, one meaning
          "okay": "OK", "café": "cafe"}
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def xlsx_rows(path: Path) -> list[dict]:
    """The first sheet of an .xlsx as {column letter: value} (no extra packages)."""
    z = zipfile.ZipFile(path)
    shared = ["".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t"))
              for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS)]
    rows = []
    for r in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).iter(f"{{{NS['m']}}}row"):
        row = {}
        for c in r.findall("m:c", NS):
            v = c.find("m:v", NS)
            if v is not None:
                row[re.match(r"[A-Z]+", c.get("r")).group(0)] = shared[int(v.text)] if c.get("t") == "s" else v.text
        rows.append(row)
    return rows[1:]  # header


def main() -> None:
    ngsl = sorted(csv.DictReader(open(SRC / "NGSL_12_stats.csv", encoding="utf-8-sig")), key=lambda r: int(r["SFI Rank"]))
    # The NGSL file went through Excel: "true" / "false" came out as TRUE / FALSE. Its lemmas are lower case ("I" aside).
    ngsl_words = [r["Lemma"] if r["Lemma"] == "I" else r["Lemma"].lower() for r in ngsl]
    taken = {w.lower() for w in ngsl_words}
    supplement = {line.split(",")[0].strip().lower() for line in open(SRC / "SUP_lemmatized.csv", encoding="utf-8")
                  if line.strip()}
    others = [r for r in xlsx_rows(SRC / "NGSLwithSFI-31K.xlsx")
              if r.get("A") and r["A"].lower() not in taken | supplement | EXCLUDE]
    others.sort(key=lambda r: -float(r.get("D") or 0))  # D = SFI, the measure the NGSL ranks by
    words = ngsl_words + [r["A"] for r in others[:TOTAL - len(ngsl_words)]]
    words = [RENAME.get(w, w) for w in words]
    assert len(words) == TOTAL and len({w.lower() for w in words}) == TOTAL, "duplicates or wrong count"

    in_levels = set()
    for level in ("A1", "A2", "B1", "B2", "C1"):
        for w in json.loads((OUT.parent / f"{level}.json").read_text(encoding="utf-8"))["words"]:
            in_levels.add(w["w"].lower())
    if MEANINGS:
        meanings = {m["w"].lower(): m for m in json.loads(MEANINGS.read_text(encoding="utf-8"))}
    else:
        meanings = {m["w"].lower(): m for m in json.loads(OUT.read_text(encoding="utf-8"))["words"] if "tr" in m}
    out, missing = [], []
    for rank, w in enumerate(words, 1):
        if w.lower() in in_levels:
            out.append({"w": w, "rank": rank})
            continue
        m = meanings.get(w.lower())
        if not m:
            missing.append(w)
            continue
        out.append({"w": w, "rank": rank, "pos": m["pos"], "tr": m["tr"], **({"ipa": m["ipa"]} if m.get("ipa") else {})})
    if missing:
        sys.exit(f"Türkçe anlamı olmayan kelimeler: {missing}")
    data = {
        "id": "TOP3000", "count": len(out),
        "sources": [
            {"title": "New General Service List 1.2 (Browne, Culligan & Phillips)", "license": "CC BY-SA 4.0",
             "url": "https://www.newgeneralservicelist.com/new-general-service-list"},
        ],
        "note": "rank = frequency order; words in a level list take their meaning from it (backend/words.py)",
        "words": out,
    }
    # One word per line: easy to read and to review (diffs show the changed words only).
    head = json.dumps({k: v for k, v in data.items() if k != "words"}, ensure_ascii=False, indent=1)[:-2]
    body = ",\n".join("  " + json.dumps(w, ensure_ascii=False) for w in out)
    OUT.write_text(f'{head},\n "words": [\n{body}\n ]\n}}\n', encoding="utf-8")
    print(f"{OUT}: {len(out)} kelime, {sum(1 for x in out if 'tr' in x)} tanesi kendi anlamıyla")


if __name__ == "__main__":
    main()
