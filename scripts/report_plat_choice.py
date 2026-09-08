"""How to choose the plat that NAMED a street, when several cover it.

Earliest `RecordedDate` is the obvious rule and it is wrong on its own. AP's
observation: plats before about 1950 are original townsite and acreage filings
whose streets were named for trees and presidents, and much of that land was
re-platted decades later. A 1946 plat did not name a street built inside a 1993
re-plat of it.

This reports how often the earliest plat and the largest-share plat disagree,
how the disagreements distribute by era, and what a share threshold would do,
so the rule can be chosen from evidence rather than asserted.
"""
import argparse, collections, json

from streetymology.config import data_path

CTX = "place_context.json"


def year(rec):
    return int(rec[:4]) if rec else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old-before", type=int, default=1950)
    ap.add_argument("--examples", type=int, default=12)
    a = ap.parse_args()

    ctx = json.loads((data_path(CTX)).read_text())
    places = [v for v in ctx.values() if v["analysed"] and v["plats"]]
    print(f"{len(places)} analysed places with at least one plat\n")

    n_multi = 0
    disagree = []
    for v in places:
        pls = v["plats"]
        if len(pls) < 2:
            continue
        n_multi += 1
        earliest = min(pls, key=lambda p: (p["recorded"] or "9999"))
        biggest = max(pls, key=lambda p: p["share"])
        if earliest is not biggest:
            disagree.append((v, earliest, biggest))

    print(f"places covered by >1 plat: {n_multi} ({n_multi/len(places):.1%})")
    print(f"  earliest is NOT the largest share: {len(disagree)}"
          f"  ({len(disagree)/n_multi:.1%} of those,"
          f" {len(disagree)/len(places):.1%} of all)")

    eras = collections.Counter()
    for v, e, b in disagree:
        ey, by = year(e["recorded"]), year(b["recorded"])
        old_e = ey is not None and ey < a.old_before
        eras[("early plat pre-%d" % a.old_before) if old_e else "both modern"] += 1
    print("\ndisagreements by era of the earliest plat")
    for k, n in eras.most_common():
        print(f"  {k:24s} {n:5d}  {n/len(disagree):5.1%}")

    print("\nshare held by the earliest plat, where it loses on share")
    sh = sorted(e["share"] for v, e, b in disagree)
    for q, label in ((0.1, "p10"), (0.25, "p25"), (0.5, "median"), (0.9, "p90")):
        print(f"  {label:6s} {sh[int(len(sh)*q)]:.2f}")
    for t in (0.1, 0.25, 0.4, 0.5):
        keep = sum(1 for s in sh if s >= t)
        print(f"  a threshold of {t:.2f} would still pick the earliest in "
              f"{keep}/{len(sh)} = {keep/len(sh):.0%} of disagreements")

    print("\nyear gap between earliest and largest-share plat")
    gaps = sorted(abs((year(b['recorded']) or 0) - (year(e['recorded']) or 0))
                  for v, e, b in disagree)
    print(f"  median {gaps[len(gaps)//2]}, p90 {gaps[int(len(gaps)*0.9)]}, "
          f"max {gaps[-1]}")
    big = sum(1 for g in gaps if g >= 25)
    print(f"  25 years or more apart: {big} ({big/len(gaps):.0%})")

    print(f"\nexamples, largest year gap first")
    ex = sorted(disagree, key=lambda t: -(abs((year(t[2]['recorded']) or 0)
                                              - (year(t[1]['recorded']) or 0))))
    for v, e, b in ex[:a.examples]:
        print(f"  {v['name'][:32]:32s} earliest {e['name'][:22]:22s}"
              f" {e['recorded'][:4]} {e['share']:.2f}   largest "
              f"{b['name'][:22]:22s} {b['recorded'][:4]} {b['share']:.2f}")


if __name__ == "__main__":
    main()
