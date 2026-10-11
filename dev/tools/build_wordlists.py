"""Candidate data for the level word lists (app/content/vocab/<LEVEL>.json), before the manual review.

Sources (all free; attribution in app/content/vocab/README.md):
- CEFR-J Wordlist 1.5 (A1–B2, Tono Laboratory, TUFS) and Octanove Vocabulary Profile C1 (CC BY-SA 4.0):
  https://github.com/openlanguageprofiles/olp-en-cefrj
- Turkish meanings: the app's English Wiktionary dictionary (data/dictionary.db) and the Turkish Wiktionary
  (kaikki.org/trwiktionary, English entries with Turkish glosses), both CC BY-SA.

    runtime\\python\\python.exe dev\\tools\\build_wordlists.py <folder with the downloaded files> <out folder>

Writes <out>/<LEVEL>.candidates.json: one item per word, meanings matched to the part of speech.
The candidates are then checked and completed by hand (the review), and assembled with
dev/tools/assemble_wordlists.py.
"""

import collections
import csv
import gzip
import json
import sqlite3
import sys
from pathlib import Path

SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2])
ROOT = Path(__file__).resolve().parents[2]
LEVELS = ["A1", "A2", "B1", "B2", "C1"]

# CEFR-J part of speech → Wiktionary's
POS = {"noun": "noun", "verb": "verb", "adjective": "adj", "adverb": "adv", "pronoun": "pron",
       "preposition": "prep", "determiner": "det", "conjunction": "conj", "number": "num",
       "interjection": "intj", "modal auxiliary": "verb", "be-verb": "verb", "do-verb": "verb",
       "have-verb": "verb", "infinitive-to": "particle"}


def headword(raw: str) -> str:
    return raw.split("/")[0].strip()  # "a.m./A.M./am/AM" → "a.m."


def load_rows() -> list[dict]:
    rows = list(csv.DictReader(open(SRC / "cefrj-vocabulary-profile-1.5.csv", encoding="utf-8")))
    rows += [r for r in csv.DictReader(open(SRC / "octanove-vocabulary-profile-c1c2-1.0.csv", encoding="utf-8"))
             if r["CEFR"] == "C1"]
    return rows


def load_trwikt() -> dict:
    out = collections.defaultdict(list)
    with gzip.open(SRC / "trwikt.jsonl.gz", "rt", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("lang_code") != "en":
                continue
            glosses = [g.strip() for s in d.get("senses", []) for g in s.get("glosses", []) if g and g.strip()]
            ipa = next((s["ipa"] for s in d.get("sounds", []) if s.get("ipa")), None)
            if glosses:
                out[d["word"].lower()].append({"pos": d.get("pos"), "glosses": glosses, "ipa": ipa})
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    trwikt = load_trwikt()
    dic = sqlite3.connect(ROOT / "data" / "dictionary.db")
    seen: dict[str, dict] = {}
    by_level = collections.defaultdict(list)
    for r in load_rows():
        word, level, pos = headword(r["headword"]), r["CEFR"], r["pos"]
        key = word.lower()
        if key in seen:  # same word, another part of speech: one card per word
            if pos not in seen[key]["pos"]:
                seen[key]["pos"].append(pos)
            continue
        item = {"w": word, "level": level, "pos": [pos]}
        seen[key] = item
        by_level[level].append(item)

    for level, items in by_level.items():
        for item in items:
            wanted = {POS.get(p, p) for p in item["pos"]}
            cands, ipa, definition, example = [], None, None, None
            for pos, tr_json, defs_json, ex, e_ipa in dic.execute(
                    "SELECT pos, tr_json, definitions_json, example, ipa FROM entries WHERE word = ? COLLATE NOCASE",
                    (item["w"],)):
                match = pos in wanted
                trs = [t["word"] for t in json.loads(tr_json)][:5]
                if trs:
                    cands.append({"from": "en-wikt", "pos": pos, "match": match, "tr": trs})
                ipa = ipa or e_ipa
                if match or not definition:
                    defs = json.loads(defs_json)
                    definition = (defs[0] if defs else None) if match or not definition else definition
                example = example or (ex if match else None)
            for t in trwikt.get(item["w"].lower(), []):
                cands.append({"from": "tr-wikt", "pos": t["pos"], "match": t["pos"] in wanted, "tr": t["glosses"][:5]})
                ipa = ipa or t["ipa"]
            item.update(candidates=cands, ipa=ipa, definition=definition, example=example)
        path = OUT / f"{level}.candidates.json"
        path.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
        missing = sum(1 for i in items if not i["candidates"])
        print(f"{level}: {len(items)} kelime, {missing} tanesinin Türkçe adayı yok → {path}")


main()
