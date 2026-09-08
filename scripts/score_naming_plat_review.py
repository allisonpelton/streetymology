"""Score AP's verdicts on the held-out naming-plat sample.

Reads the review CSV and reports nothing but what is in it. Never writes to the
sheet. The question it answers: on streets nobody tuned the rule against, how
often is the choice right, and does confidence rank the failures last?

`verdict` judges the choice of plat, `theme_ok` says whether a theme from that
plat would be plausible at all -- which is the era weight expressed in a form a
model can use, not a claim that the theme would help.
"""
import argparse, collections, csv

from streetymology.config import DELIVERABLES_DIR

DEFAULT = DELIVERABLES_DIR / "naming_plat_review" / "naming_plat_sample.csv"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", default=str(DEFAULT))
    a = ap.parse_args()

    with open(a.sheet, newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if (r["verdict"] or "").strip()]
    if not rows:
        print("no verdicts yet")
        return

    def f(r, k):
        v = (r.get(k) or "").strip()
        return float(v) if v else None

    n = len(rows)
    counts = collections.Counter(r["verdict"].strip().lower() for r in rows)
    print(f"{n} judged\n")
    for k, v in counts.most_common():
        print(f"  {k:8s} {v:3d}  {v/n:5.0%}")

    ok = [r for r in rows if r["verdict"].strip().lower() == "right"]
    bad = [r for r in rows if r["verdict"].strip().lower() not in ("right", "unsure")]
    print(f"\ncorrect on unseen streets: {len(ok)}/{n} = {len(ok)/n:.0%}")

    # The question a confidence number exists to answer: are the failures the
    # ones it was least sure about?
    co = sorted(x for x in (f(r, "confidence") for r in ok) if x is not None)
    cb = sorted(x for x in (f(r, "confidence") for r in bad) if x is not None)
    if co and cb:
        print(f"\nconfidence, correct rows:  min {co[0]:.2f}  median "
              f"{co[len(co)//2]:.2f}")
        print(f"confidence, failed rows:   {', '.join(f'{x:.2f}' for x in cb)}")
        below = sum(1 for x in co if x <= max(cb))
        print(f"correct rows at or below the worst failure's confidence: {below}")
        if below == 0:
            print("  -> confidence ranks every failure below every success")

    # The number that matters downstream. A wrong plat only hurts if the model
    # is also told to trust it for a theme: that is when an etymology gets
    # invented. A wrong plat at low theme confidence is nearly harmless.
    print("\nrisk of an invented theme: wrong or unnamed plat, by theme confidence")
    for lo, hi in ((0.0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.01)):
        band = [r for r in rows if (f(r, "theme_confidence") or 0) >= lo
                and (f(r, "theme_confidence") or 0) < hi]
        if not band:
            continue
        bad_b = [r for r in band
                 if r["verdict"].strip().lower() not in ("right", "unsure")]
        print(f"  theme {lo:.2f}-{hi:.2f}: {len(bad_b):2d} of {len(band):2d} rows"
              f" not right")
    risky = [r for r in rows
             if r["verdict"].strip().lower() not in ("right", "unsure")
             and (f(r, "theme_confidence") or 0) >= 0.6]
    print(f"  presented confidently AND wrong: {len(risky)}/{n} = {len(risky)/n:.0%}")
    for r in risky:
        print(f"      {r['street'][:18]:18s} theme {r['theme_confidence']:>5}"
              f"  {r['verdict']}  {r['notes'][:52]}")

    th = collections.Counter((r.get("theme_ok") or "").strip().lower()
                             for r in rows if (r.get("theme_ok") or "").strip())
    if th:
        print("\ntheme plausible, by AP:")
        for k, v in th.most_common():
            print(f"  {k:8s} {v:3d}")
        eras = [(f(r, "theme_confidence"), (r.get("theme_ok") or "").strip().lower())
                for r in rows]
        for label in ("yes", "no"):
            xs = sorted(x for x, t in eras if t == label and x is not None)
            if xs:
                print(f"  theme_confidence where {label:3s}: "
                      f"{xs[0]:.2f} to {xs[-1]:.2f}")


if __name__ == "__main__":
    main()
