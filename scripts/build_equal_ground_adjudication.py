"""Emit a blind adjudication CSV for equal-ground items where human and model
disagreed.

Blind by construction: the two disputed choices are written in a seeded random
order as option_1/option_2, with no indication of which side gave which, and no
reasoning text from either. The mapping is written to artifacts/, not
deliverables/, so it is not read by accident during adjudication.

The verdict column is free-form: the adjudicator may pick any letter or NONE,
not only the two disputed options.
"""
import argparse, csv, os, random, re

DATA = os.environ.get("STREETYMOLOGY_DATA_DIR", "/workspace/streetymology-data")
SEED = 20260905


def parse_items(path):
    items, cur = {}, None
    for line in open(path, encoding="utf-8"):
        m = re.match(r"^### (\d+)\.\s+(.*)", line)
        if m:
            cur = {"n": int(m.group(1)), "street": m.group(2).strip(),
                   "subdivision": "", "nearby": "", "cands": []}
            items[cur["n"]] = cur
            continue
        if cur is None:
            continue
        if m := re.match(r"^- \*\*Subdivision:\*\*\s*(.*)", line):
            cur["subdivision"] = m.group(1).strip()
        elif m := re.match(r"^- \*\*Nearby streets:\*\*\s*(.*)", line):
            cur["nearby"] = m.group(1).strip()
        elif m := re.match(r"^\s+- \*\*([A-E])\.\*\*\s*(.*)", line):
            cur["cands"].append(f"{m.group(1)}. {m.group(2).strip()}")
    return items


def read_human(p):
    return {int(r["n"]): r for r in csv.DictReader(open(p, newline="", encoding="utf-8"))}


def read_model(p):
    rows = {}
    for line in open(p, encoding="utf-8"):
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) >= 6 and re.fullmatch(r"\d+", c[0]):
            rows[int(c[0])] = {"choice": c[2], "confidence": c[3]}
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", default=f"{DATA}/deliverables/equal_ground.md")
    ap.add_argument("--human", default=f"{DATA}/deliverables/equal_ground_labels.csv")
    ap.add_argument("--model", default=f"{DATA}/deliverables/equal_ground_results.md")
    ap.add_argument("--out", default=f"{DATA}/deliverables/equal_ground_adjudication.csv")
    ap.add_argument("--sources", default=f"{DATA}/artifacts/equal_ground_adjudication_SOURCES.csv")
    a = ap.parse_args()

    items, H, M = parse_items(a.items), read_human(a.human), read_model(a.model)
    disputed = [n for n in sorted(set(H) & set(M)) if H[n]["choice"] != M[n]["choice"]]

    rng = random.Random(SEED)
    rows, srcs = [], []
    for n in disputed:
        it = items[n]
        pair = [("human", H[n]["choice"]), ("model", M[n]["choice"])]
        rng.shuffle(pair)
        rows.append({
            "n": n, "street": it["street"], "subdivision": it["subdivision"],
            "nearby_streets": it["nearby"],
            "candidates": " || ".join(it["cands"]),
            "option_1": pair[0][1], "option_2": pair[1][1],
            "verdict": "", "notes": "",
        })
        srcs.append({"n": n, "street": it["street"],
                     "option_1_source": pair[0][0], "option_2_source": pair[1][0],
                     "human": H[n]["choice"], "model": M[n]["choice"]})

    for path, data in ((a.out, rows), (a.sources, srcs)):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(data[0]))
            w.writeheader()
            w.writerows(data)
    print(f"{len(rows)} disputed items -> {a.out}")
    print(f"blind mapping -> {a.sources}")


if __name__ == "__main__":
    main()
