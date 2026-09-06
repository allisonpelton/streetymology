"""Score the multi-candidate selection experiment against AP's labels.

Positive controls: did the model pick the letter mapping to the known QID?
Negative controls: did it answer NONE? (Disagreements may be adjudicable --
search can surface an entity AP never saw.)
"""
import csv, collections
from streetymology.config import ARTIFACTS_DIR

A = ARTIFACTS_DIR


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


def score(path, key):
    res = parse(path)
    name = path.stem.replace("selection_experiment_RESULT_", "")
    print(f"\n{'='*64}\n{name}\n{'='*64}")
    pos = [(n, key[n], res[n]) for n in key
           if key[n]["is_control"] == "yes" and key[n]["truth_letter"] not in ("", "NONE") and n in res]
    neg = [(n, key[n], res[n]) for n in key
           if key[n]["truth_letter"] == "NONE" and n in res]
    unk = [(n, key[n], res[n]) for n in key if key[n]["is_control"] == "no" and n in res]
    print(f"parsed {len(res)}/40 rows\n")
    ph = sum(1 for _, k, r in pos if r["choice"] == k["truth_letter"])
    pn = sum(1 for _, k, r in pos if r["choice"] == "NONE")
    print(f"POSITIVE controls: {ph}/{len(pos)} correct letter"
          f"   ({pn} answered NONE, {len(pos)-ph-pn} picked a wrong candidate)")
    nh = sum(1 for _, k, r in neg if r["choice"] == "NONE")
    print(f"NEGATIVE controls: {nh}/{len(neg)} correctly answered NONE"
          f"   ({len(neg)-nh} picked a candidate)")
    tot = len(pos) + len(neg)
    print(f"overall control accuracy: {ph+nh}/{tot} ({(ph+nh)/tot*100:.0f}%)")
    print("\nwrong picks on POSITIVE controls:")
    for n, k, r in pos:
        if r["choice"] not in (k["truth_letter"],):
            print(f"   {n:>2}. {k['street']:28} said={r['choice']:5} truth={k['truth_letter']:5} "
                  f"conf={r['confidence']:7} {r['reasoning'][:44]}")
    print("\nNEGATIVE controls where a candidate was picked (may be adjudicable):")
    for n, k, r in neg:
        if r["choice"] != "NONE":
            print(f"   {n:>2}. {k['street']:28} said={r['choice']:5} conf={r['confidence']:7} "
                  f"{r['reasoning'][:52]}")
    c = collections.Counter(r["choice"] == "NONE" for _, _, r in unk)
    print(f"\nUNKNOWNS: {len(unk)} shown | NONE={c[True]} | picked a candidate={c[False]}")
    byconf = collections.defaultdict(lambda: [0, 0])
    for _, k, r in pos + neg:
        byconf[r["confidence"]][0] += r["choice"] == k["truth_letter"]
        byconf[r["confidence"]][1] += 1
    print("accuracy by stated confidence:")
    for cf, (h, t) in sorted(byconf.items()):
        print(f"   {cf or '(blank)':10} {h}/{t}")
    return res


if __name__ == "__main__":
    key = {int(r["n"]): r for r in csv.DictReader((A / "selection_experiment_KEY.csv").open())}
    runs = {}
    for p in sorted(A.glob("selection_experiment_RESULT_*.md")):
        runs[p.stem.split("_")[-1]] = score(p, key)
    if len(runs) == 2:
        (a, ra), (b, rb) = list(runs.items())
        both = [n for n in key if n in ra and n in rb]
        agree = sum(1 for n in both if ra[n]["choice"] == rb[n]["choice"])
        print(f"\n{'='*64}\ninter-model agreement: {agree}/{len(both)} ({agree/len(both)*100:.0f}%)")
        unk = [n for n in both if key[n]["is_control"] == "no"]
        ua = sum(1 for n in unk if ra[n]["choice"] == rb[n]["choice"])
        print(f"  on the {len(unk)} unknowns: {ua} ({ua/len(unk)*100:.0f}%)")
