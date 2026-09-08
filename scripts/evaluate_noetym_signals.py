"""Test whether `nameness` detects "no publishable etymology", its actual job.

`nameness` was previously measured against "is this candidate the right entity"
and scored AUC 0.568, which put it on notice for removal. That was the wrong
question. Surname matching does not claim to identify a referent; it claims a
street name is a bare personal name and therefore has no etymology worth
publishing. The equal-ground round-2 set is the first data able to test that,
because it has an explicit NOETYM class.

Predictor: nameness of the street's own core name, not of a candidate. Low
nameness (the core is a surname or given name) should predict NOETYM.

Truth: the author's label, overridden by her adjudication verdict where one
exists. Disagreements she left unruled are dropped -- they are exactly the
NONE/NOETYM boundary cases, so keeping them would score the signal against
answers she declined to give.
"""
import argparse, csv, json

from streetymology import rounds, signals as S
from streetymology.config import data_path
from streetymology.normalize import key
from streetymology.streets import osm_cores

NOETYM = "NOETYM"


def truth(R):
    """Final human answer per item: label, overridden by adjudication verdict."""
    with R.labels.open(newline="") as fh:
        H = {int(r["n"]): r for r in csv.DictReader(fh) if r.get("choice", "").strip()}
    V = {}
    if R.adjudication_csv.exists():
        with R.adjudication_csv.open(newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("verdict", "").strip():
                    V[int(r["n"])] = r["verdict"].strip().upper()
    return H, V


def auc(pos, neg):
    """Probability a random positive scores above a random negative."""
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def main():
    ap = argparse.ArgumentParser()
    rounds.add_argument(ap)
    ap.add_argument("--unruled", choices=("drop", "human"), default="drop",
                    help="unruled disagreements: drop them, or trust the human")
    a = ap.parse_args()
    R = rounds.Round(a.round)

    # Street-core nameness (scripts/fetch_core_nameness.py) is the right input:
    # meta_nameness.json covers candidate labels, so it is near-empty for the
    # unmatched streets these rounds are drawn from. Fall back to it where the
    # core file has no entry.
    by_core = {}
    for f in ("meta_nameness.json", "meta_nameness_cores.json"):
        p = data_path(f)
        if p.exists():
            by_core.update({key(k): v for k, v in json.loads(p.read_text()).items()})
    cores = osm_cores()

    H, V = truth(R)
    rows, skipped, uncovered = [], 0, 0
    for n, r in H.items():
        human = r["choice"].strip().upper()
        model_disagreed = n in V
        if n in V:
            final = V[n]
        elif a.unruled == "human":
            final = human
        else:
            # Unruled rows are only in V if adjudicated; a row absent from the
            # adjudication file was never disputed, so the human answer stands.
            final = human
        k = key(r["street"])
        if k not in cores:
            uncovered += 1
        nm = by_core.get(k)
        if nm is None:
            nm = {"surname": False, "given": False}
        rows.append({
            "n": n, "street": r["street"], "core": k, "final": final,
            "noetym": int(final == NOETYM),
            "nameness": S.nameness(nm.get("surname", False), nm.get("given", False)),
            "known_name": nm.get("surname", False) or nm.get("given", False),
        })

    # Drop the disagreements the author declined to rule on.
    if a.unruled == "drop":
        with R.adjudication_csv.open(newline="") as fh:
            unruled = {int(r["n"]) for r in csv.DictReader(fh)
                       if not r.get("verdict", "").strip()}
        skipped = sum(1 for r in rows if r["n"] in unruled)
        rows = [r for r in rows if r["n"] not in unruled]

    pos = [1 - r["nameness"] for r in rows if r["noetym"]]
    neg = [1 - r["nameness"] for r in rows if not r["noetym"]]
    print(f"round {R.n}: {len(rows)} scorable items"
          f"{f', {skipped} unruled disagreement(s) dropped' if skipped else ''}")
    print(f"NOETYM {len(pos)}, publishable {len(neg)}")

    A = auc(pos, neg)
    print(f"\nnameness as a NOETYM detector: AUC {A:.3f}" if A else "\nno AUC")

    # The signal is three-valued, so report the confusion directly: a threshold
    # sweep would invent precision it does not have.
    print("\nnameness value x outcome")
    print(f"  {'nameness':>8}  {'n':>4}  {'NOETYM':>7}  {'rate':>6}   meaning")
    meaning = {0.0: "surname AND given name", 0.2: "surname or given name",
               1.0: "not a known personal name"}
    for v in (0.0, 0.2, 1.0):
        sub = [r for r in rows if r["nameness"] == v]
        if not sub:
            continue
        k = sum(r["noetym"] for r in sub)
        print(f"  {v:8.1f}  {len(sub):4d}  {k:7d}  {k/len(sub):6.0%}   {meaning[v]}")

    flagged = [r for r in rows if r["known_name"]]
    if flagged:
        tp = sum(r["noetym"] for r in flagged)
        allp = sum(r["noetym"] for r in rows)
        print(f"\nrule: 'core is a known personal name' -> NOETYM")
        print(f"  precision {tp}/{len(flagged)} = {tp/len(flagged):.0%}")
        print(f"  recall    {tp}/{allp} = {tp/allp:.0%}")
        base = allp / len(rows)
        print(f"  base rate {allp}/{len(rows)} = {base:.0%}"
              f"  (lift {tp/len(flagged)/base:.2f}x)")

    misses = [r for r in rows if r["noetym"] and not r["known_name"]]
    print(f"\n{len(misses)} NOETYM item(s) the signal cannot see; first 15:")
    for r in misses[:15]:
        print(f"  {r['n']:4d}  {r['street']}")


if __name__ == "__main__":
    main()
