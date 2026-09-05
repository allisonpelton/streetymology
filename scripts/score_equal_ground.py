"""Compare human and model answers on the equal-ground labelling set.

There is no ground-truth key for these 40 items, so this reports AGREEMENT
ONLY. No accuracy figure can be derived from these files.
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


if __name__ == "__main__":
    main()
