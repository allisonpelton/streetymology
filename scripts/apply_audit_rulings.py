"""Build a corrected label set from AP's rulings on the audit disagreements.

Provenance is preserved per row: `source` records whether the verdict came from
the original hand pass, an audit ruling for the author, or an audit ruling for
the model. Any figure computed from this file must disclose that it is
LLM-assisted.
"""
import csv
from streetymology.config import LABELS_DIR, ARTIFACTS_DIR, DELIVERABLES_DIR

A = ARTIFACTS_DIR
D = DELIVERABLES_DIR
OUT = LABELS_DIR / "labels_corrected.csv"

if __name__ == "__main__":
    key = {int(r["n"]): r for r in csv.DictReader((A / "label_audit_KEY.csv").open())}
    rulings = {int(r["n"]): r for r in csv.DictReader((D / "label_audit_review.csv").open())}
    orig = list(csv.DictReader((LABELS_DIR / "labels_merged.csv").open()))
    by_pair = {(r["street"], r["domain"]): r for r in orig}

    rows, changed = [], 0
    for n, k in sorted(key.items()):
        base = dict(by_pair[(k["street"], k["domain"])])
        rul = rulings.get(n)
        source = "hand-label (audit agreed)"
        if rul:
            side = rul["ruling__author_or_model"].strip().lower()
            if side == "model":
                changed += 1
                mapping = dict(x.split("=") for x in k["candidates"].split("|") if "=" in x)
                choice = rul["model_choice"]
                if choice == "NONE":
                    base["verdict"] = "n"
                else:
                    base["verdict"] = "y"
                    base["qid"] = mapping.get(choice, base["qid"])
                source = "audit: ruled for model"
                base["notes"] = (base["notes"] + " | " if base["notes"] else "") + \
                    f"AUDIT: verdict changed to '{base['verdict']}' per AP ruling. " \
                    f"Model reasoning: {rul['model_reasoning'][:110]}"
            else:
                source = "audit: ruled for author"
        base["source"] = source
        rows.append(base)

    cols = [c for c in rows[0] if c != "source"] + ["source"]
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader(); w.writerows(rows)
    import collections
    print(f"{len(rows)} rows -> {OUT}")
    print(f"verdicts changed by audit: {changed}")
    print("before:", collections.Counter(r["verdict"] for r in orig))
    print("after :", collections.Counter(r["verdict"] for r in rows))
    print("provenance:", collections.Counter(r["source"] for r in rows))
