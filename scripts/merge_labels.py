"""Merge the first labelling pass with the focused re-label pass.

Re-label rows supersede originals, including their QID: 6 rows were re-shown
with a different (better-ranked) candidate.
"""
import csv, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from streetymology.config import DATA_DIR

ARTIFACTS = DATA_DIR / "artifacts"
FIELDS = ["street", "domain", "qid", "wikidata_label", "sitelinks",
          "km_from_ada_county", "same_name_items", "other_domains",
          "verdict", "notes", "pass"]


def merge():
    base = {}
    for r in csv.DictReader((ARTIFACTS / "review_sample.csv").open()):
        base[(r["street"], r["domain"])] = {
            "street": r["street"], "domain": r["domain"], "qid": r["qid"],
            "wikidata_label": r["wikidata_label"], "sitelinks": r["sitelinks"],
            "km_from_ada_county": r["km_from_ada_county"],
            "same_name_items": r["same_name_items_in_domain"],
            "other_domains": r["other_domains"],
            "verdict": r["verdict__y_n_w_q"].strip().lower(),
            "notes": r["notes"], "pass": "1",
        }
    n_over = 0
    for r in csv.DictReader((ARTIFACTS / "relabel_sample.csv").open()):
        v = r["verdict__y_n_w_q"].strip().lower()
        if not v:
            continue                       # left blank; keep the pass-1 'q'
        k = (r["street"], r["domain"])
        base[k] = {
            "street": r["street"], "domain": r["domain"], "qid": r["qid"],
            "wikidata_label": r["wikidata_label"], "sitelinks": r["sitelinks"],
            "km_from_ada_county": r["km_from_ada_county"],
            "same_name_items": r["same_name_items"],
            "other_domains": base.get(k, {}).get("other_domains", "-"),
            "verdict": v, "notes": r["notes"], "pass": "2",
        }
        n_over += 1
    return list(base.values()), n_over


if __name__ == "__main__":
    rows, n_over = merge()
    out = ARTIFACTS / "labels_merged.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader(); w.writerows(rows)
    import collections
    c = collections.Counter(r["verdict"] for r in rows)
    decided = sum(c[k] for k in "ynw")
    print(f"{len(rows)} rows, {n_over} superseded by pass 2")
    print(f"verdicts: {dict(c)}")
    print(f"decided (y/n/w): {decided}  -> {out}")
