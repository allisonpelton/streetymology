"""One sheet holding every equal-ground answer, for recoding the abstentions.

`NOETYM` turned out to be two classes wearing one label. AP's own round-2 notes
separate them without being asked: "seems invented" against "local's name". The
first has no referent and never will; the second has a real referent that
Wikidata does not carry. A map should not colour them the same.

Emits every item from every round with its final answer -- the label, overridden
by an adjudication verdict where one exists -- and an empty `new_class` column
for the abstentions. Letter answers are carried through and marked no-action, so
the sheet is a complete record rather than a worklist with holes.

Never writes to a labelling CSV. Output is a new file.
"""
import argparse, csv

from streetymology import rounds
from streetymology.config import DELIVERABLES_DIR

# INVENTED and PERSONAL are the split of the old NOETYM; NONE keeps its
# 2026-09-07 meaning, a pipeline miss rather than a property of the street.
CLASSES = ("INVENTED", "PERSONAL", "NONE")
ABSTENTIONS = {"NONE", "NOETYM"}


def read_round(n):
    """(final answer, note) per item for one round, or None if it is not on disk."""
    R = rounds.Round(n)
    labels = R.labels
    if not labels.exists():
        return None
    out = {}
    with labels.open(newline="") as fh:
        for r in csv.DictReader(fh):
            if not r.get("choice", "").strip():
                continue
            out[int(r["n"])] = {"street": r["street"],
                                "choice": r["choice"].strip().upper(),
                                "note": r.get("notes", "").strip()}

    for path in (R.adjudication_csv,):
        if not path.exists():
            continue
        with path.open(newline="") as fh:
            for r in csv.DictReader(fh):
                v = (r.get("verdict") or "").strip().upper()
                k = int(r["n"])
                if v and k in out:
                    out[k]["choice"] = v
                    extra = (r.get("notes") or "").strip()
                    if extra:
                        out[k]["note"] = f"{out[k]['note']} | {extra}".strip(" |")
        break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", default="1,2")
    ap.add_argument("--out", default=str(DELIVERABLES_DIR / "equal_ground" /
                                        "all_labels_recode.csv"))
    a = ap.parse_args()

    rows, missing = [], []
    for n in [int(x) for x in a.rounds.replace(",", " ").split()]:
        got = read_round(n)
        if got is None:
            missing.append(n)
            continue
        for k in sorted(got):
            r = got[k]
            needs = r["choice"] in ABSTENTIONS
            rows.append({"round": n, "n": k, "street": r["street"],
                         "answer": r["choice"],
                         "new_class": "" if needs else "(no action)",
                         "note": r["note"]})

    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["round", "n", "street", "answer",
                                           "new_class", "note"])
        w.writeheader()
        w.writerows(rows)

    todo = [r for r in rows if not r["new_class"]]
    print(f"wrote {a.out}")
    print(f"{len(rows)} items across rounds {a.rounds}; {len(todo)} need a class")
    if missing:
        print(f"rounds not found on disk: {missing}")
    from collections import Counter
    print("\nanswers needing recode:", dict(Counter(r["answer"] for r in todo)))
    print(f"of those, {sum(1 for r in todo if r['note'])} already carry a note")
    print(f"\nallowed values for new_class: {', '.join(CLASSES)}")


if __name__ == "__main__":
    main()
