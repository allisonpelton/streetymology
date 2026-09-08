"""Model performance against the three-way recode of the abstentions.

The label sheets carry two abstention classes, NONE and NOETYM. AP recoded every
abstention in `all_labels_recode.csv` into INVENTED (no referent), PERSONAL (a
real person or family Wikidata does not carry) and NONE (a real etymology the
pipeline failed to surface). The model's answers are unchanged; only the human
side gained resolution, so this rescores the same runs against a finer reference.

Why it matters for the model: the three classes carry different verdicts on a
model that answered with a candidate letter.

  INVENTED  a letter is a fabricated referent. Never publishable.
  PERSONAL  a letter is wrong, but the street does have a referent.
  NONE      a letter is a disagreement about candidates, and the pipeline
            already failed regardless of what either side said.

Reads the recode sheet and each round's model answers. Writes nothing.
"""
import argparse, collections, csv, re

from streetymology import rounds
from streetymology.config import DELIVERABLES_DIR

CLASSES = ("INVENTED", "PERSONAL", "NONE")
MODEL_KINDS = ("letter", "NONE", "NOETYM")


def kind(choice):
    c = (choice or "").strip().upper()
    return c if c in ("NONE", "NOETYM") else "letter"


def read_model(path):
    """Model answers out of the results markdown table, keyed by item number."""
    rows = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 6 or not re.fullmatch(r"\d+", cells[0]):
                continue
            rows[int(cells[0])] = cells[2].strip().upper()
    return rows


def pct(a, b):
    return f"{a}/{b} = {a/b:.0%}" if b else f"{a}/0"


def table(title, rowkeys, colkeys, count):
    print(f"\n{title}")
    print(f"  {'':10s}" + "".join(f"{c:>9s}" for c in colkeys) + f"{'total':>9s}")
    for r in rowkeys:
        vals = [count(r, c) for c in colkeys]
        print(f"  {r:10s}" + "".join(f"{v:9d}" for v in vals) + f"{sum(vals):9d}")
    tots = [sum(count(r, c) for r in rowkeys) for c in colkeys]
    print(f"  {'total':10s}" + "".join(f"{v:9d}" for v in tots) + f"{sum(tots):9d}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recode", default=str(DELIVERABLES_DIR / "equal_ground" /
                                            "all_labels_recode.csv"))
    ap.add_argument("--per-item", action="store_true",
                    help="list the streets the model claimed a referent for")
    a = ap.parse_args()

    with open(a.recode, newline="", encoding="utf-8") as fh:
        sheet = list(csv.DictReader(fh))

    models = {}
    items = []
    for r in sheet:
        rd = int(r["round"])
        if rd not in models:
            models[rd] = read_model(rounds.Round(rd).results)
        m = models[rd].get(int(r["n"]))
        if m is None:
            continue
        items.append({"round": rd, "n": int(r["n"]), "street": r["street"],
                      "answer": r["answer"].strip().upper(),
                      "new_class": r["new_class"].strip().upper(),
                      "note": r["note"], "model": m})

    print(f"recode sheet: {a.recode}")
    print(f"{len(sheet)} rows, {len(items)} matched to a model answer")
    blank = [i for i in items if not i["new_class"]]
    if blank:
        print(f"WARNING: {len(blank)} abstention(s) still unrecoded; excluded")
        items = [i for i in items if i["new_class"]]

    recoded = [i for i in items if i["new_class"] in CLASSES]
    print(f"\nabstentions recoded: {len(recoded)}")
    for rd in sorted({i['round'] for i in recoded}):
        c = collections.Counter(i["new_class"] for i in recoded if i["round"] == rd)
        n = sum(c.values())
        print(f"  round {rd}  n={n:3d}  " +
              "  ".join(f"{k} {c[k]:3d} ({c[k]/n:.0%})" for k in CLASSES))
    c = collections.Counter(i["new_class"] for i in recoded)
    n = len(recoded)
    print(f"  all      n={n:3d}  " +
          "  ".join(f"{k} {c[k]:3d} ({c[k]/n:.0%})" for k in CLASSES))

    # How the old two-way label maps onto the new three-way one. NOETYM was the
    # label under test; NONE rows are here because AP could recode them too.
    table("old human label (row) x new class (column)",
          ("NOETYM", "NONE"), CLASSES,
          lambda o, nc: sum(1 for i in recoded
                            if i["answer"] == o and i["new_class"] == nc))

    table("new human class (row) x model answer (column)",
          CLASSES, MODEL_KINDS,
          lambda nc, mk: sum(1 for i in recoded
                             if i["new_class"] == nc and kind(i["model"]) == mk))

    # The decision that reaches OSM. On every one of these rows the human
    # withheld, so any model letter is a claim she would not publish.
    for nc in CLASSES:
        pool = [i for i in recoded if i["new_class"] == nc]
        letters = [i for i in pool if kind(i["model"]) == "letter"]
        print(f"\n{nc}: model claimed a referent on {pct(len(letters), len(pool))}")
        if a.per_item:
            for i in letters:
                print(f"    r{i['round']} {i['n']:3d} {i['street'][:38]:38s}"
                      f" -> {i['model']:6s} note: {i['note'][:40]}")

    # Model NOETYM scored against the classes where withholding is the street's
    # own property. NONE is a pipeline complaint, so a model NOETYM there is an
    # over-withhold, not a hit.
    mn = [i for i in recoded if kind(i["model"]) == "NOETYM"]
    real = [i for i in recoded if i["new_class"] in ("INVENTED", "PERSONAL")]
    hit = [i for i in mn if i["new_class"] in ("INVENTED", "PERSONAL")]
    print("\nmodel NOETYM as a detector of 'no publishable referent'"
          " (INVENTED + PERSONAL)")
    print(f"  precision {pct(len(hit), len(mn))}")
    print(f"  recall    {pct(len(hit), len(real))}")
    inv = [i for i in mn if i["new_class"] == "INVENTED"]
    print(f"  of the model's NOETYM calls, {pct(len(inv), len(mn))} are INVENTED")

    # Can the model tell INVENTED from PERSONAL at all? It never had the classes,
    # so this is only a check on whether its two abstention words track them.
    table("new class (row) x model abstention word (column), abstentions only",
          ("INVENTED", "PERSONAL", "NONE"), ("NONE", "NOETYM"),
          lambda nc, mk: sum(1 for i in recoded
                             if i["new_class"] == nc and kind(i["model"]) == mk))


if __name__ == "__main__":
    main()
