"""Compare human and model answers on the equal-ground labelling set.

Agreement is reported for all items. Accuracy is reported only where an
adjudication file supplies verdicts, since the set has no ground-truth key.

Rows adjudicated NOETYM are excluded from the accuracy comparison: they turn on
an editorial judgement about what belongs in OSM, not on evidence. Use
--exclude to exclude further rows by number.
"""
import argparse, csv, collections, os, re

DATA = os.environ.get("STREETYMOLOGY_DATA_DIR", "/workspace/streetymology-data")


def read_human(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return {int(r["n"]): r for r in csv.DictReader(fh)}


def read_model(path):
    rows = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 6 or not re.fullmatch(r"\d+", cells[0]):
                continue
            rows[int(cells[0])] = dict(
                zip(("n", "street", "choice", "confidence", "theme", "reasoning"), cells)
            )
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--human", default=f"{DATA}/deliverables/equal_ground_labels.csv")
    ap.add_argument("--model", default=f"{DATA}/deliverables/equal_ground_results.md")
    ap.add_argument("--adjudication",
                    default=f"{DATA}/deliverables/equal_ground_adjudication.csv")
    ap.add_argument("--exclude", default="", help="comma-separated item numbers")
    a = ap.parse_args()

    H, M = read_human(a.human), read_model(a.model)
    ns = sorted(set(H) & set(M))
    print(f"items: human {len(H)}, model {len(M)}, compared {len(ns)}\n")

    exact = [n for n in ns if H[n]["choice"] == M[n]["choice"]]
    abst = lambda c: c.upper() == "NONE"
    same_call = [n for n in ns if abst(H[n]["choice"]) == abst(M[n]["choice"])]

    print(f"exact choice agreement : {len(exact)}/{len(ns)} = {len(exact)/len(ns):.0%}")
    print(f"abstain/commit agreement: {len(same_call)}/{len(ns)} = {len(same_call)/len(ns):.0%}")
    print(f"human abstained : {sum(abst(H[n]['choice']) for n in ns)}/{len(ns)}")
    print(f"model abstained : {sum(abst(M[n]['choice']) for n in ns)}/{len(ns)}")

    kinds = collections.Counter()
    for n in ns:
        h, m = H[n]["choice"], M[n]["choice"]
        if h == m:
            kinds["agree"] += 1
        elif abst(h):
            kinds["human NONE, model committed"] += 1
        elif abst(m):
            kinds["model NONE, human committed"] += 1
        else:
            kinds["both committed, different letter"] += 1
    print("\ndisagreement shape")
    for k, v in kinds.most_common():
        print(f"  {k:34s} {v}")

    print("\nagreement by human confidence")
    for c in ("high", "medium", "low"):
        sub = [n for n in ns if H[n]["confidence"].strip().lower() == c]
        if sub:
            ok = sum(H[n]["choice"] == M[n]["choice"] for n in sub)
            print(f"  {c:7s} n={len(sub):2d}  agree {ok}/{len(sub)} = {ok/len(sub):.0%}")

    print("\ndisagreements")
    for n in ns:
        if H[n]["choice"] != M[n]["choice"]:
            print(f"  {n:2d} {H[n]['street'][:34]:34s} human {H[n]['choice']:4s}"
                  f"({H[n]['confidence'][:3]})  model {M[n]['choice']:4s}({M[n]['confidence'][:3]})")

    if not os.path.exists(a.adjudication):
        print("\nno adjudication file; agreement only, no accuracy figure")
        return

    V = {}
    with open(a.adjudication, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("verdict", "").strip():
                V[int(r["n"])] = r["verdict"].strip()

    manual = {int(x) for x in a.exclude.split(",") if x.strip()}
    noetym = {n for n, v in V.items() if v.upper() == "NOETYM"} | manual
    scored = [n for n in ns if n not in noetym and (n not in V or V[n])]

    def truth(n):
        return V.get(n, H[n]["choice"] if H[n]["choice"] == M[n]["choice"] else None)

    hs = sum(truth(n) == H[n]["choice"] for n in scored if truth(n))
    ms = sum(truth(n) == M[n]["choice"] for n in scored if truth(n))
    tot = sum(1 for n in scored if truth(n))
    print(f"\naccuracy, {len(noetym)} row(s) excluded")
    print(f"  human {hs}/{tot} = {hs/tot:.0%}")
    print(f"  model {ms}/{tot} = {ms/tot:.0%}")


if __name__ == "__main__":
    main()
