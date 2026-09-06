"""Compare LLM audit choices with the author's labels; emit disagreements.

Agreement rules:
  author `y` -> model should pick the letter mapping to her QID
  author `n` -> model should answer NONE
  author `w` -> she said right category / wrong item, so any non-NONE choice
                other than her QID is broad agreement
"""
import csv, collections
from streetymology.config import ARTIFACTS_DIR, DELIVERABLES_DIR

A = ARTIFACTS_DIR
D = DELIVERABLES_DIR


def parse(path):
    out = {}
    for line in path.read_text().splitlines():
        if not line.strip().startswith("|"):
            continue
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) < 3 or not c[0].isdigit():
            continue
        ch = c[2].upper().strip("`* ")
        ch = "NONE" if ch.startswith("NONE") else ch[:1]
        out[int(c[0])] = {"street": c[1], "choice": ch,
                          "confidence": c[3].lower() if len(c) > 3 else "",
                          "theme": c[4] if len(c) > 4 else "",
                          "reasoning": c[5] if len(c) > 5 else ""}
    return out


def agrees(k, r):
    v, letter, ch = k["author_verdict"], k["author_letter"], r["choice"]
    if v == "y":
        return ch == letter
    if v == "n":
        return ch == "NONE"
    return ch not in ("NONE", letter)          # 'w'


if __name__ == "__main__":
    res = {}
    for p in sorted(A.glob("label_audit_RESULT_*.md")):
        res.update(parse(p))
    key = {int(r["n"]): r for r in csv.DictReader((A / "label_audit_KEY.csv").open())}
    missing = [n for n in key if n not in res]
    print(f"parsed {len(res)}/{len(key)} rows" + (f"  MISSING {missing[:8]}" if missing else ""))

    agree = [n for n in key if n in res and agrees(key[n], res[n])]
    disagree = [n for n in key if n in res and not agrees(key[n], res[n])]
    print(f"\nagreement: {len(agree)}/{len(agree)+len(disagree)} "
          f"({len(agree)/(len(agree)+len(disagree))*100:.0f}%)")
    byv = collections.defaultdict(lambda: [0, 0])
    for n in agree + disagree:
        byv[key[n]["author_verdict"]][0] += n in agree
        byv[key[n]["author_verdict"]][1] += 1
    print("by author verdict:")
    for v, (a, t) in sorted(byv.items()):
        print(f"   author said '{v}': {a}/{t} agree ({a/t*100:.0f}%)")

    kind = collections.Counter()
    for n in disagree:
        k, r = key[n], res[n]
        if k["author_verdict"] == "y" and r["choice"] == "NONE":
            kind["author y, model NONE"] += 1
        elif k["author_verdict"] == "y":
            kind["author y, model picked a different entity"] += 1
        elif k["author_verdict"] == "n":
            kind["author n, model picked an entity"] += 1
        else:
            kind["other"] += 1
    print("\ndisagreement types:", dict(kind))

    out = D / "label_audit_review.csv"
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["n", "street", "domain", "author_verdict", "author_choice_letter",
                    "model_choice", "model_confidence", "model_theme", "model_reasoning",
                    "ruling__author_or_model", "notes"])
        for n in sorted(disagree):
            k, r = key[n], res[n]
            w.writerow([n, k["street"], k["domain"], k["author_verdict"],
                        k["author_letter"] or "NONE", r["choice"], r["confidence"],
                        r["theme"], r["reasoning"], "", ""])
    print(f"\n{len(disagree)} disagreements -> {out}")
    conf = collections.defaultdict(lambda: [0, 0])
    for n in agree + disagree:
        conf[res[n]["confidence"]][0] += n in agree
        conf[res[n]["confidence"]][1] += 1
    print("agreement by model confidence:")
    for c, (a, t) in sorted(conf.items()):
        print(f"   {c or '(blank)':10} {a}/{t}")
