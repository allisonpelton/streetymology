"""Expected error rate over all eligible streets, from the two review samples.

The samples were drawn differently on purpose, so neither rate can be read
straight off:

  sample 1  uniform over places with at least one plat. Its 90% is close to a
            population estimate already, but 20 rows is thin.
  sample 2  stratified by confidence, and restricted to places covered by more
            than one plat. Its 57% is pessimistic BY CONSTRUCTION: it excludes
            the 59% of places with a single covering plat, which AP judges
            correct by definition, and it oversamples low-confidence bands.

This reweights sample 2 by the population of each confidence band, combines the
strata, and reports what falls out. Every figure is small-sample; the counts are
printed alongside so nobody quotes a rate whose denominator is 3.
"""
import argparse, csv, json

from streetymology.config import DELIVERABLES_DIR, data_path

CTX = "place_context.json"
BANDS = [(0.0, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 0.95), (0.95, 1.01)]
REVIEW = DELIVERABLES_DIR / "naming_plat_review"


def band_of(x):
    for lo, hi in BANDS:
        if lo <= x < hi:
            return (lo, hi)
    return BANDS[-1]


def read(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if (r["verdict"] or "").strip()]


def wrong(r):
    """An error is naming a plat that did not name the street."""
    return r["verdict"].strip().lower() in ("wrong", "none", "missed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet1", default=str(REVIEW / "naming_plat_sample.csv"))
    ap.add_argument("--sheet2", default=str(REVIEW / "naming_plat_sample_2.csv"))
    a = ap.parse_args()

    ctx = json.loads((data_path(CTX)).read_text())
    named = [v for v in ctx.values() if v["analysed"] and v["naming_plat"]]
    single = [v for v in named if len(v["plats"]) == 1]
    multi = [v for v in named if len(v["plats"]) > 1]
    n_all = len(named)
    print(f"places naming a plat: {n_all}")
    print(f"  one covering plat : {len(single):5d}  {len(single)/n_all:5.1%}"
          f"   (AP: correct barring patterns this data cannot show)")
    print(f"  more than one     : {len(multi):5d}  {len(multi)/n_all:5.1%}")

    s1, s2 = read(a.sheet1), read(a.sheet2)

    # Sample 1 rows that happened to fall in the single-plat stratum give the
    # only direct evidence on it.
    def plats_in_row(r):
        return len([x for x in r["plats_covering"].split(";") if x.strip()])
    s1_single = [r for r in s1 if plats_in_row(r) == 1]
    s1_multi = [r for r in s1 if plats_in_row(r) > 1]
    e_single = sum(wrong(r) for r in s1_single)
    print(f"\nsample 1: {len(s1_single)} single-plat rows, {e_single} wrong;"
          f" {len(s1_multi)} multi-plat rows, {sum(wrong(r) for r in s1_multi)} wrong")

    # Sample 2, reweighted: error within each confidence band, times that band's
    # share of the multi-plat population.
    print("\nmulti-plat stratum, sample 2 reweighted by band population")
    print(f"  {'band':>11} {'population':>11} {'share':>7} {'judged':>7} {'wrong':>6}"
          f" {'rate':>6}")
    est, covered = 0.0, 0.0
    rows_by_band = {}
    for lo, hi in BANDS:
        pop = [v for v in multi if lo <= v["confidence"] < hi]
        judged = [r for r in s2 if lo <= float(r["confidence"] or 0) < hi]
        rows_by_band[(lo, hi)] = (pop, judged)
        share = len(pop) / len(multi) if multi else 0
        if judged:
            rate = sum(wrong(r) for r in judged) / len(judged)
            est += share * rate
            covered += share
            print(f"  {lo:.2f}-{hi:4.2f} {len(pop):11d} {share:7.1%} {len(judged):7d}"
                  f" {sum(wrong(r) for r in judged):6d} {rate:6.0%}")
        else:
            print(f"  {lo:.2f}-{hi:4.2f} {len(pop):11d} {share:7.1%} {'-':>7}"
                  f" {'-':>6} {'-':>6}")
    if covered:
        est_multi = est / covered
        print(f"  weighted error over the multi-plat stratum: {est_multi:.0%}"
              f"  (bands covering {covered:.0%} of it)")

        # Single-plat stratum: use sample 1's direct evidence, and show the
        # answer at 0% too, since AP's argument is that it should be near zero.
        for label, e_s in (("observed", e_single / len(s1_single) if s1_single else 0.0),
                           ("assumed zero", 0.0)):
            overall = (len(single) / n_all) * e_s + (len(multi) / n_all) * est_multi
            print(f"\n  single-plat error {label} ({e_s:.0%})"
                  f" -> overall expected error {overall:.0%}")

    # What the error costs: a wrong plat only invents a theme if it is also
    # presented as trustworthy.
    print("\nof the errors, how many would be shown confidently (theme >= 0.6)")
    for name, rows in (("sample 1", s1), ("sample 2", s2)):
        bad = [r for r in rows if wrong(r)]
        risky = [r for r in bad if float(r["theme_confidence"] or 0) >= 0.6]
        print(f"  {name}: {len(risky)} of {len(bad)} errors, "
              f"{len(risky)}/{len(rows)} of rows")
    est_risky = 0.0
    for (lo, hi), (pop, judged) in rows_by_band.items():
        if not judged:
            continue
        share = len(pop) / len(multi)
        rate = sum(1 for r in judged if wrong(r)
                   and float(r["theme_confidence"] or 0) >= 0.6) / len(judged)
        est_risky += share * rate
    if covered:
        pop_risky = (len(multi) / n_all) * (est_risky / covered)
        print(f"  reweighted, over ALL eligible places: {pop_risky:.1%}"
              f"  <- wrong plat AND presented as trustworthy")


if __name__ == "__main__":
    main()
