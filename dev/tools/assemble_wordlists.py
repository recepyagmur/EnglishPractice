"""Assemble the reviewed word lists into app/content/vocab/<LEVEL>.json.

    runtime\\python\\python.exe dev\\tools\\assemble_wordlists.py <work folder>

<work>/cand/<LEVEL>.candidates.json  (dev/tools/build_wordlists.py: words, parts of speech, IPA)
<work>/review/<PART>.output[.partN].json  (the hand review: final Turkish meanings, skip flags)

Checks: every word reviewed exactly once and in order, no empty meaning, no leftover
Wiktionary oddities (glosses in English, "Bir soyadı.", very long explanations).
"""

import json
import re
import sys
from pathlib import Path

WORK = Path(sys.argv[1])
OUT = Path(__file__).resolve().parents[2] / "app" / "content" / "vocab"
PARTS = {"A1": ["A1"], "A2": ["A2"], "B1": ["B1-1", "B1-2"], "B2": ["B2-1", "B2-2"], "C1": ["C1"]}

# Decisions after the review (reported by the reviewers): misspellings in the source lists,
# a racial slur, a non-word, and the most common meaning missing because of the listed part of speech.
DROP = {"gook", "unscathing"}
OVERRIDES = {
    "chauffer": {"w": "chauffeur"},
    "refrain": {"pos": ["noun", "verb"], "tr": "fiil: kaçınmak (refrain from); isim: nakarat"},
    "pandemic": {"pos": ["noun", "adjective"], "tr": "isim: pandemi, küresel salgın; sıfat: pandemik"},
    "weep": {"pos": ["verb"], "tr": "ağlamak, gözyaşı dökmek"},
    "exaggerate": {"pos": ["verb"]},
    "bombard": {"pos": ["verb"]},
    "blurt": {"pos": ["verb"]},
    "enviable": {"pos": ["adjective"]},
}


def read_review(part: str) -> list[dict]:
    single = WORK / "review" / f"{part}.output.json"
    files = [single] if single.exists() else sorted((WORK / "review").glob(f"{part}.output.part*.json"),
                                                    key=lambda p: int(re.search(r"part(\d+)", p.name).group(1)))
    if not files:
        raise SystemExit(f"{part}: inceleme çıktısı yok")
    out = []
    for f in files:
        out += json.loads(f.read_text(encoding="utf-8"))
    return out


def problems_in(tr: str) -> list[str]:
    p = []
    if len(tr) > 90:
        p.append("çok uzun")
    if re.search(r"\b(the|of|to|and|or|a)\b", tr) and not re.search(r"[çğıöşüÇĞİÖŞÜ]", tr):
        p.append("İngilizce gibi")
    if "soyad" in tr.lower() or "özel ad" in tr.lower():
        p.append("özel ad")
    return p


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for level, parts in PARTS.items():
        cands = json.loads((WORK / "cand" / f"{level}.candidates.json").read_text(encoding="utf-8"))
        reviewed = [x for part in parts for x in read_review(part)]
        if len(reviewed) != len(cands):
            raise SystemExit(f"{level}: {len(cands)} kelime, inceleme {len(reviewed)}")
        words, flagged = [], []
        for c, r in zip(cands, reviewed):
            if r["w"].lower() != c["w"].lower():
                raise SystemExit(f"{level}: sıra kaydı: {c['w']} ≠ {r['w']}")
            if r.get("skip") or c["w"].lower() in DROP:
                continue
            tr = " ".join((r.get("tr") or "").split())
            if not tr:
                raise SystemExit(f"{level}: anlam boş: {c['w']}")
            if problems_in(tr):
                flagged.append(f"{c['w']}: {tr} ({', '.join(problems_in(tr))})")
            item = {"w": c["w"], "pos": c["pos"], "tr": tr, **OVERRIDES.get(c["w"].lower(), {})}
            if c.get("ipa"):
                item["ipa"] = c["ipa"] if c["ipa"].startswith(("/", "[")) else f"/{c['ipa']}/"
            words.append(item)
        data = {"level": level, "count": len(words), "words": words}
        (OUT / f"{level}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        total += len(words)
        print(f"{level}: {len(words)} kelime ({len(cands) - len(words)} atlandı)")
        for f in flagged[:40]:
            print("   kontrol et →", f)
    print(f"toplam {total} kelime → {OUT}")


main()
