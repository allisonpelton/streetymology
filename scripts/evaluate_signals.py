"""Measure how well each plausibility signal separates the author's labels.

'q' (unsure) rows are excluded from precision maths -- they are neither correct
nor incorrect, and folding them either way would bias the thresholds.
"""
import csv, json, sys, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from streetymology.config import DATA_DIR, LABELS_DIR
from streetymology import signals as S

import os
LABEL_FILE = os.environ.get("STREETYMOLOGY_LABELS", "labels_corrected.csv")

ARTIFACTS = DATA_DIR / "artifacts"


def load():
    coords = json.loads((DATA_DIR / "meta_coords.json").read_text())
    names = json.loads((DATA_DIR / "meta_nameness.json").read_text())
    rows = []
    for r in csv.DictReader((LABELS_DIR / LABEL_FILE).open()):
        v = (r["verdict"] or "").strip().lower()
        if v not in {"y", "n", "w"}:
            continue
        label = r["wikidata_label"]
        nm = names.get(label, {})
        km = S.distance_to_ada(coords.get(r["qid"]))
        rows.append({
            "row": r, "y": 1 if v == "y" else 0,
            "commonness": S.commonness(label),
            "notability": S.notability(int(r["sitelinks"] or 0)),
            "nameness": S.nameness(nm.get("surname", False), nm.get("given", False)),
            "proximity": S.proximity(km),
        })
    return rows


def auc(rows, sig):
    """Probability a random correct row scores above a random incorrect one."""
    pos = [r[sig] for r in rows if r["y"] and r[sig] is not None]
    neg = [r[sig] for r in rows if not r["y"] and r[sig] is not None]
    if not pos or not neg:
        return None, len(pos), len(neg)
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg)), len(pos), len(neg)


if __name__ == "__main__":
    rows = load()
    print(f"decided rows: {len(rows)}  (y={sum(r['y'] for r in rows)}, "
          f"n={sum(1 for r in rows if not r['y'])})")
    print(f"baseline precision: {sum(r['y'] for r in rows)/len(rows)*100:.1f}%\n")
    print(f"{'signal':14} {'AUC':>6} {'n_pos':>6} {'n_neg':>6}   interpretation")
    for sig in ["commonness", "notability", "nameness", "proximity"]:
        a, npos, nneg = auc(rows, sig)
        if a is None:
            print(f"  {sig:14} {'n/a':>6}"); continue
        verdict = ("useless" if 0.45 <= a <= 0.55 else
                   "weak" if 0.55 < a <= 0.62 else
                   "useful" if 0.62 < a <= 0.75 else
                   "strong" if a > 0.75 else
                   "INVERTED (predicts wrong)" if a < 0.45 else "")
        print(f"  {sig:14} {a:>6.3f} {npos:>6} {nneg:>6}   {verdict}")
