"""Compare human and model answers on the equal-ground labelling set.

Agreement is reported for all answered items. Accuracy is reported only where an
adjudication file supplies verdicts, since the set has no ground-truth key.

Three answer kinds: a letter (a candidate is right), NONE (a referent may exist
but is not among the candidates), NOETYM (the name has no etymology worth
publishing). NOETYM is reported as its own class rather than folded into NONE.

Two accuracy figures are printed. "etymology accuracy" drops rows where either
side said NOETYM or the verdict was NOETYM, and is the figure comparable to
round 1. "full accuracy" keeps them and treats NOETYM as an ordinary answer.
Use --exclude to drop further rows by number.

Never writes to the labelling CSV. Adjudication lives in its own file.
"""
import argparse, csv, collections, os, re

from streetymology import rounds

DATA = os.environ.get("STREETYMOLOGY_DATA_DIR", "/workspace/streetymology-data")

NONE, NOETYM = "NONE", "NOETYM"


def kind(choice):
    """Answer class of a raw choice cell."""
    c = (choice or "").strip().upper()
    return c if c in (NONE, NOETYM) else "letter"


def read_human(path):
    """Answered rows only, so a partly finished sheet scores on what is done."""
    with open(path, newline="", encoding="utf-8") as fh:
        rows = {}
        for r in csv.DictReader(fh):
            r["choice"] = (r.get("choice") or "").strip().upper()
            if r["choice"]:
                rows[int(r["n"])] = r
        return rows


def read_model(path):
    rows = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 6 or not re.fullmatch(r"\d+", cells[0]):
                continue
            r = dict(zip(("n", "street", "choice", "confidence", "theme", "reasoning"), cells))
            r["choice"] = r["choice"].strip().upper()
            rows[int(r["n"])] = r
    return rows


def main():
    ap = argparse.ArgumentParser()
    rounds.add_argument(ap)
    ap.add_argument("--human", help="override the round's label sheet")
    ap.add_argument("--model", help="override the round's model answers")
    ap.add_argument("--adjudication", help="override the round's adjudication sheet")
    ap.add_argument("--exclude", default="", help="comma-separated item numbers")
    ap.add_argument("--per-item", action="store_true",
                    help="list individual disagreements; withhold while labelling")
    a = ap.parse_args()
    R = rounds.Round(a.round)
    a.human = a.human or R.labels
    a.model = a.model or R.results
    a.adjudication = a.adjudication or R.adjudication_csv
    print(f"round {R.n}: {R.deliverables}")

    H, M = read_human(a.human), read_model(a.model)
    ns = sorted(set(H) & set(M))
    if not ns:
        print("no answered items in common")
        return
    print(f"items: human answered {len(H)}, model {len(M)}, compared {len(ns)}")
    if len(H) < len(M):
        print(f"  partial sheet: {len(M) - len(H)} item(s) not yet labelled\n")
    else:
        print()

    exact = [n for n in ns if H[n]["choice"] == M[n]["choice"]]
    same_kind = [n for n in ns if kind(H[n]["choice"]) == kind(M[n]["choice"])]
    print(f"exact choice agreement: {len(exact)}/{len(ns)} = {len(exact)/len(ns):.0%}")
    print(f"answer-class agreement: {len(same_kind)}/{len(ns)} = {len(same_kind)/len(ns):.0%}")

    print("\nanswer class mix")
    for who, D in (("human", H), ("model", M)):
        c = collections.Counter(kind(D[n]["choice"]) for n in ns)
        print(f"  {who}  letter {c['letter']:3d}   NONE {c[NONE]:3d}   NOETYM {c[NOETYM]:3d}")

    print("\nclass confusion, human row x model column")
    ks = ("letter", NONE, NOETYM)
    print(f"  {'':8s}" + "".join(f"{k:>8s}" for k in ks))
    for hk in ks:
        row = [sum(1 for n in ns if kind(H[n]["choice"]) == hk
                   and kind(M[n]["choice"]) == mk) for mk in ks]
        print(f"  {hk:8s}" + "".join(f"{v:8d}" for v in row))

    # The decision that reaches OSM is binary: publish a QID or do not.
    pub = lambda c: kind(c) == "letter"
    same_pub = [n for n in ns if pub(H[n]["choice"]) == pub(M[n]["choice"])]
    print(f"\npublish/withhold agreement: {len(same_pub)}/{len(ns)}"
          f" = {len(same_pub)/len(ns):.0%}")

    # NOETYM as a detector, scored against the human as reference.
    hn = {n for n in ns if kind(H[n]["choice"]) == NOETYM}
    mn = {n for n in ns if kind(M[n]["choice"]) == NOETYM}
    if hn or mn:
        tp = len(hn & mn)
        print(f"\nNOETYM detection, human as reference")
        print(f"  human {len(hn)}, model {len(mn)}, both {tp}")
        if mn:
            print(f"  precision {tp}/{len(mn)} = {tp/len(mn):.0%}")
        if hn:
            print(f"  recall    {tp}/{len(hn)} = {tp/len(hn):.0%}")

    print("\nagreement by human confidence")
    for c in ("high", "medium", "low"):
        sub = [n for n in ns if (H[n].get("confidence") or "").strip().lower() == c]
        if sub:
            ok = sum(H[n]["choice"] == M[n]["choice"] for n in sub)
            print(f"  {c:7s} n={len(sub):3d}  agree {ok}/{len(sub)} = {ok/len(sub):.0%}")

    disagree = [n for n in ns if H[n]["choice"] != M[n]["choice"]]
    print(f"\ndisagreements: {len(disagree)}")
    if a.per_item:
        for n in disagree:
            print(f"  {n:3d} {H[n]['street'][:34]:34s} human {H[n]['choice']:6s}"
                  f"({(H[n].get('confidence') or '')[:3]})  "
                  f"model {M[n]['choice']:6s}({M[n]['confidence'][:3]})")
    else:
        print("  (per-item detail withheld; pass --per-item once labelling is done)")

    if not os.path.exists(a.adjudication):
        print("\nno adjudication file; agreement only, no accuracy figure")
        return

    V = {}
    with open(a.adjudication, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("verdict", "").strip():
                V[int(r["n"])] = r["verdict"].strip().upper()

    manual = {int(x) for x in a.exclude.split(",") if x.strip()}

    def truth(n):
        """Adjudicated verdict, else the agreed answer, else unknown."""
        if n in V:
            return V[n]
        return H[n]["choice"] if H[n]["choice"] == M[n]["choice"] else None

    def report(label, pool):
        rows = [n for n in pool if truth(n)]
        if not rows:
            print(f"\n{label}: no scorable rows")
            return
        hs = sum(truth(n) == H[n]["choice"] for n in rows)
        ms = sum(truth(n) == M[n]["choice"] for n in rows)
        print(f"\n{label}, n={len(rows)}")
        print(f"  human {hs}/{len(rows)} = {hs/len(rows):.0%}")
        print(f"  model {ms}/{len(rows)} = {ms/len(rows):.0%}")

    scorable = [n for n in ns if n not in manual]
    # Either side saying NOETYM makes the row an editorial call, not an evidence call.
    noetym_rows = {n for n in scorable
                   if NOETYM in (kind(H[n]["choice"]), kind(M[n]["choice"]))
                   or V.get(n) == NOETYM}
    report("full accuracy, NOETYM kept as an answer", scorable)
    report("etymology accuracy, NOETYM rows dropped",
           [n for n in scorable if n not in noetym_rows])
    print(f"\n  {len(noetym_rows)} NOETYM row(s) dropped from the second figure"
          f"{f', {len(manual)} excluded manually' if manual else ''}")

    # The figures above credit both sides for every undisputed row, so they
    # share a floor of len(agreed) correct answers and compress the gap. Only
    # the adjudicated rows carry information about who was right.
    disputed = [n for n in scorable if H[n]["choice"] != M[n]["choice"]]
    report("adjudicated disagreements only", [n for n in disputed if n in V])

    unruled = [n for n in disputed if n not in V]
    if unruled:
        print(f"\n{len(unruled)} disagreement(s) left unruled, excluded above")
        pattern = collections.Counter(
            f"human {kind(H[n]['choice'])} vs model {kind(M[n]['choice'])}"
            for n in unruled)
        for k, v in pattern.most_common():
            print(f"  {v:3d}  {k}")
        print(f"  items: {', '.join(str(n) for n in unruled)}")


if __name__ == "__main__":
    main()
