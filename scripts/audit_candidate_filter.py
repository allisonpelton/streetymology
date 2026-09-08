"""How much would the candidate filter have changed a round that already ran?

Rounds already labelled cannot be rebuilt, but the filter can be replayed over
their key to size the problem: how many offered candidates were bare personal
names, and how many items the author or model actually chose one for.
"""
import argparse, csv, json

from streetymology import rounds
from streetymology.candidates import publishable
from streetymology.config import data_path


def main():
    ap = argparse.ArgumentParser()
    rounds.add_argument(ap)
    a = ap.parse_args()
    R = rounds.Round(a.round)

    meta = json.loads(data_path("meta_candidates.json").read_text())
    search = json.loads(data_path("search_unmatched.json").read_text())
    # Search hits carry their own descriptions; gazetteer matches use meta.
    desc = {h["qid"]: h.get("description", "")
            for hits in search.values() for h in hits}
    for q, m in meta.items():
        desc.setdefault(q, m.get("description", ""))

    with R.labels.open(newline="") as fh:
        human = {int(r["n"]): r["choice"].strip().upper()
                 for r in csv.DictReader(fh) if r.get("choice", "").strip()}

    total = dropped = 0
    emptied = []
    lost_human = []
    with R.key.open(newline="") as fh:
        for r in csv.DictReader(fh):
            n = int(r["n"])
            pairs = [p.split("=") for p in r["candidates"].split("|") if "=" in p]
            keep = []
            for letter, qid in pairs:
                total += 1
                if publishable(desc.get(qid)):
                    keep.append(letter)
                else:
                    dropped += 1
                    if human.get(n) == letter:
                        lost_human.append((n, r.get("street", ""), letter, desc.get(qid)))
            if pairs and not keep:
                emptied.append((n, r.get("street", "")))

    print(f"round {R.n}: {total} candidates offered, {dropped} would be dropped "
          f"({dropped/total:.0%})")
    print(f"{len(emptied)} item(s) would be left with no candidates at all")
    for n, st in emptied[:10]:
        print(f"    {n:4d}  {st}")
    print(f"\n{len(lost_human)} item(s) where the author's own pick would vanish:")
    for n, st, letter, d in lost_human:
        print(f"    {n:4d}  {st:<34} {letter}  {d!r}")


if __name__ == "__main__":
    main()
