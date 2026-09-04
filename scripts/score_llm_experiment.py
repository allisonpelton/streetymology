"""Score a fresh-Claude experiment run against the known controls.

Paste each run's returned markdown table into
  $STREETYMOLOGY_DATA_DIR/artifacts/llm_experiment_RESULT_<model>.md
then run:  python scripts/score_llm_experiment.py [model ...]

With no arguments it scores every RESULT file it finds, so several models can be
compared side by side.
"""
import csv, re, sys, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from streetymology.config import DATA_DIR

A = DATA_DIR / "artifacts"


def parse(path: Path):
    out = {}
    for line in path.read_text().splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not cells[0].isdigit():
            continue
        out[int(cells[0])] = {"street": cells[1], "verdict": cells[2].lower().strip("`"),
                              "confidence": cells[3].lower() if len(cells) > 3 else "",
                              "theme": cells[4] if len(cells) > 4 else "",
                              "reasoning": cells[5] if len(cells) > 5 else ""}
    return out


def score(path: Path, key: dict):
    res = parse(path)
    ctrl = [(n, key[n], res[n]) for n in key if key[n]["is_control"] == "yes" and n in res]
    print(f"\n{'='*62}\n{path.stem.replace('llm_experiment_RESULT_','')}\n{'='*62}")
    print(f"parsed {len(res)} responses; {len(ctrl)} controls matched\n")
    if not ctrl:
        print("  no controls matched -- check the table parsed correctly"); return
    hit = sum(1 for _, k, r in ctrl if r["verdict"] == k["true_verdict"])
    print(f"exact agreement on controls: {hit}/{len(ctrl)} ({hit/len(ctrl)*100:.0f}%)")
    cm = collections.Counter((k["true_verdict"], r["verdict"]) for _, k, r in ctrl)
    print("\nconfusion (true -> predicted):")
    for (t, p), c in sorted(cm.items()):
        print(f"   {t} -> {p}: {c}")
    fp = [(n, k, r) for n, k, r in ctrl if k["true_verdict"] == "n" and r["verdict"] == "y"]
    print(f"\nFALSE POSITIVES (said y, truth n): {len(fp)}")
    for n, k, r in fp:
        print(f"   {n}. {k['street']} [{k['domain']}] conf={r['confidence']} — {r['reasoning'][:70]}")
    fn = [(n, k, r) for n, k, r in ctrl if k["true_verdict"] == "y" and r["verdict"] in ("n", "q")]
    print(f"\nMISSED (said {'n/q'}, truth y): {len(fn)}")
    for n, k, r in fn:
        print(f"   {n}. {k['street']} [{k['domain']}] said={r['verdict']} — {r['reasoning'][:70]}")
    unk = [(n, key[n], res[n]) for n in key if key[n]["is_control"] == "no" and n in res]
    dec = [x for x in unk if x[2]["verdict"] in ("y", "n", "w")]
    print(f"\nPreviously-unsure rows: {len(unk)} shown, {len(dec)} given a decision "
          f"({collections.Counter(r['verdict'] for _, _, r in dec).most_common()})")
    byconf = collections.defaultdict(lambda: [0, 0])
    for _, k, r in ctrl:
        byconf[r["confidence"]][0] += r["verdict"] == k["true_verdict"]
        byconf[r["confidence"]][1] += 1
    print("\naccuracy by stated confidence:")
    for c, (h, t) in sorted(byconf.items()):
        print(f"   {c or '(blank)':8} {h}/{t}")


if __name__ == "__main__":
    key = {int(r["n"]): r for r in csv.DictReader((A / "llm_experiment_KEY.csv").open())}
    wanted = sys.argv[1:]
    paths = ([A / f"llm_experiment_RESULT_{m}.md" for m in wanted] if wanted
             else sorted(A.glob("llm_experiment_RESULT*.md")))
    found = [p for p in paths if p.exists()]
    if not found:
        print("No RESULT files found in", A)
        print("Expected e.g. llm_experiment_RESULT_opus.md")
        sys.exit(1)
    for p in found:
        score(p, key)
