"""Score the plat-context run against AP's labels, and against the old run.

Ground truth is `deliverables/equal_ground/all_labels_recode.csv`: her answer for
every item in rounds 1 and 2, adjudicated where it was disputed, with each
abstention recoded to INVENTED, PERSONAL or NONE.

Two scorings, because the old run could not have produced the new taxonomy:

  strict      the new answers against the three-way truth. Only the new run can
              be scored this way; round 1 and 2 offered NONE and NOETYM.
  comparable  both runs collapsed to {a letter, ABSTAIN}, which is the only
              question both were asked. This is the before/after.

Usage:
  python scripts/score_context_prompt.py
"""
import argparse
import collections
import csv
import pathlib
import re

from streetymology.config import DELIVERABLES_DIR

EG = DELIVERABLES_DIR / "equal_ground"
NEW = DELIVERABLES_DIR / "context_prompt" / "context_prompt_RESULT.md"
INDEX = DELIVERABLES_DIR / "context_prompt" / "context_prompt_index.csv"
OLD = {1: EG / "round1" / "equal_ground_results.md",
       2: EG / "round2" / "equal_ground_2_results.md"}
ABSTAIN = {"NONE", "NOETYM", "INVENTED", "PERSONAL"}


def read_table(path):
    """n -> row, from a markdown table with a leading `n` column."""
    out = {}
    for line in pathlib.Path(path).read_text(encoding="utf-8-sig").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not cells[0].isdigit():
            continue
        out[int(cells[0])] = {
            "street": cells[1], "choice": cells[2].upper(),
            "confidence": cells[3].lower() if len(cells) > 3 else "",
            "theme": cells[4] if len(cells) > 4 else "",
        }
    return out


def truth_map():
    """(round, n) -> the answer AP stands behind, in the new taxonomy."""
    out = {}
    with (EG / "all_labels_recode.csv").open(newline="") as fh:
        for r in csv.DictReader(fh):
            ans = r["answer"].strip().upper()
            cls = r["new_class"].strip().upper()
            out[(int(r["round"]), int(r["n"]))] = (
                cls if ans in ABSTAIN and cls and cls != "(NO ACTION)" else ans)
    return out


def pct(a, b):
    return f"{a}/{b} = {a / b:.1%}" if b else "n/a"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--new", default=str(NEW))
    a = ap.parse_args()

    truth = truth_map()
    new = read_table(a.new)
    old = {r: read_table(p) for r, p in OLD.items()}

    rows = []
    with pathlib.Path(INDEX).open(newline="") as fh:
        for r in csv.DictReader(fh):
            n, rnd, rn = int(r["n"]), int(r["round"]), int(r["round_n"])
            if r["score"] != "yes":
                continue
            t = truth.get((rnd, rn))
            nn = new.get(n)
            oo = old[rnd].get(rn)
            if t is None or nn is None:
                continue
            rows.append({"n": n, "round": rnd, "round_n": rn, "street": r["street"],
                         "truth": t, "new": nn["choice"], "conf": nn["confidence"],
                         "theme": nn["theme"],
                         "old": oo["choice"] if oo else None,
                         "merged": r["phase_merged"] == "yes"})

    print(f"scored items: {len(rows)}  (missing from the result table: "
          f"{240 - len(rows) - 1})\n")

    # ---- strict
    ok = [r for r in rows if r["new"] == r["truth"]]
    print("STRICT — new run against the three-way truth")
    print(f"  overall            {pct(len(ok), len(rows))}")
    for cls in ("LETTER", "NONE", "INVENTED", "PERSONAL"):
        sub = [r for r in rows if (r["truth"] not in ABSTAIN if cls == "LETTER"
                                   else r["truth"] == cls)]
        good = [r for r in sub if r["new"] == r["truth"]]
        print(f"  truth = {cls:9}  {pct(len(good), len(sub))}")

    # ---- comparable
    def collapse(c):
        return "ABSTAIN" if c in ABSTAIN else c

    both = [r for r in rows if r["old"]]
    on = sum(1 for r in both if collapse(r["new"]) == collapse(r["truth"]))
    oo_ = sum(1 for r in both if collapse(r["old"]) == collapse(r["truth"]))
    print("\nCOMPARABLE — letter vs abstain, the question both runs were asked")
    print(f"  old context        {pct(oo_, len(both))}")
    print(f"  plat context       {pct(on, len(both))}")
    ch = [r for r in both if collapse(r["old"]) != collapse(r["new"])]
    gained = [r for r in ch if collapse(r["new"]) == collapse(r["truth"])]
    lost = [r for r in ch if collapse(r["old"]) == collapse(r["truth"])]
    print(f"  answers that moved  {len(ch)}   fixed {len(gained)}   broken {len(lost)}")

    # ---- exact-answer movement, letters included
    exact_ch = [r for r in both if r["old"] != r["new"]]
    print(f"\n  exact answer changed on {len(exact_ch)} of {len(both)} items")

    print("\nCONFIDENCE")
    for c in ("high", "medium", "low"):
        sub = [r for r in rows if r["conf"] == c]
        good = [r for r in sub if r["new"] == r["truth"]]
        print(f"  {c:7} {pct(len(good), len(sub))}")

    print("\nCONFUSION (truth -> what the model said), top 8")
    conf = collections.Counter((r["truth"] if r["truth"] in ABSTAIN else "LETTER",
                                r["new"] if r["new"] in ABSTAIN else "LETTER")
                               for r in rows if r["new"] != r["truth"])
    for (t, g), c in conf.most_common(8):
        print(f"  {t:9} -> {g:9} {c}")

    # ---- the one question the taxonomy change does not touch: when AP says the
    # answer IS a candidate letter, does the run pick the same letter?
    letters = [r for r in rows if r["truth"] not in ABSTAIN and r["old"]]
    n_ok = sum(1 for r in letters if r["new"] == r["truth"])
    o_ok = sum(1 for r in letters if r["old"] == r["truth"])
    print("\nLETTER ITEMS ONLY — same candidates, same letters, both runs")
    print(f"  old context        {pct(o_ok, len(letters))}")
    print(f"  plat context       {pct(n_ok, len(letters))}")
    flips = [r for r in letters if r["old"] != r["new"]]
    print(f"  changed            {len(flips)}   "
          f"fixed {sum(1 for r in flips if r['new'] == r['truth'])}   "
          f"broken {sum(1 for r in flips if r['old'] == r['truth'])}")

    # abstention rate, which the taxonomy change is expected to move
    print("\nABSTENTION RATE")
    print(f"  old  {sum(1 for r in rows if r['old'] in ABSTAIN)}/{len(rows)}")
    print(f"  new  {sum(1 for r in rows if r['new'] in ABSTAIN)}/{len(rows)}")

    merged = [r for r in rows if r["merged"]]
    if merged:
        good = [r for r in merged if r["new"] == r["truth"]]
        print(f"\nPHASE-MERGED ITEMS  {pct(len(good), len(merged))}")
        for r in merged:
            mark = "ok " if r["new"] == r["truth"] else "MISS"
            print(f"  {mark} {r['street']:34} truth={r['truth']:9} "
                  f"new={r['new']:9} old={r['old']}")


if __name__ == "__main__":
    main()
