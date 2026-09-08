# Which plat named the street

How the pipeline decides which recorded plat gave a street its name, what was
tried and rejected, and what is still unsound. Measured against the OSM extract
of 2026-09-08 and the Ada County Assessor's 8,000 recorded plats.

Regenerate every figure here with:

    python scripts/build_place_context.py          # the rule, and its coverage
    python scripts/review_naming_plat.py --weak    # choices holding little street
    python scripts/review_naming_plat.py --numbered

> **Supersedes the CLEAN_SHARE experiment.** An earlier version of this document
> tuned a threshold on the share of a single OSM *way* lying inside a plat. That
> parameter no longer exists. It was measuring mapping accidents: OSM splits a
> street at arbitrary points, so "share of a way" varies with how the street was
> edited. The comparison that retired it — 0.4 handing Quail Ridge Drive to
> Briarhill on an 8 m clip — is kept below because the failure mode recurs.

## The rule

A plat **laid out** a street if all three hold:

| test | value | why it exists |
|---|---|---|
| unbroken run inside the plat | ≥ 60 m, capped at 0.8 × street length | a plat that built a street holds a continuous piece of it. The cap exists because a 54 m cul-de-sac cannot hold 60 m of anything — Copenhagen Lane abstained without it |
| total metres inside | ≥ half of the best plat's metres | compared on TOTAL, not on the bridged run: bridging joined Mcafee's fragments into a 505 m run that beat Avimor's 831 m |
| share of the whole street | ≥ 0.25 | rules out rural roads that predate the plats along them |

Among plats that pass, the **oldest** wins, ties broken by the longer run. If none
passes, **no plat is named** — an abstention, not a fallback. The fallback used to
be "plat with the longest run", which named plats a street merely grazed at
`run 0 m, inside 0 m`.

**Re-entry is normal and is bridged.** 40% of naming plats are entered more than
once, because plat boundaries detour around park parcels, school sites and phase
lines. Pieces whose ends are within 60 m count as one run. The parameter is not
sensitive: no bridging → 60 m changes 113 choices, 60 → 150 m changes 20,
60 → 400 m changes 32.

**Phases are one naming act.** `SUTTERS MILL SUB NO 01` and `NO 02` are joined on
base name, their metres added, and the earliest recording taken as the date.

## Why not the obvious rules

- **Earliest date alone.** Pre-1950 filings are acreage plats later re-platted:
  they own the dirt, not the name. Copenhagen Lane belongs to Danish Flats
  (2025), not Ora Dell (1910).
- **Largest share alone.** Prefers a big generic plat over the small themed one
  that did the naming.
- **Share of an OSM way (`CLEAN_SHARE`).** Measures where OSM split the street.
  At 0.4, Quail Ridge Drive went to Briarhill (8 m clip) and Milestone Way to
  Hoot Nanney Farms; at 0.9 it demanded a whole way inside one plat, which only
  streets with convenient splits could satisfy.

## The unsound part: streets no plat named

Boise's numbered grid streets are laid out by the town, with additions filed
piecemeal along them for decades. Before this was addressed, 29th Street was
named by Cruzen's 1906 addition and 9th Avenue by Canna Lily Estates (1995).

Two causal explanations were tested against the geometry and **both failed**:

- *The plat that laid out a street owns the land on both sides of it.* Rejected:
  Cruzen holds 29% of the left offset of 29th Street and 30% of the right —
  symmetric — while Quail Ridge, a correct case, sits at 0.28/0.39.
- *A developer's street terminates inside its plat; a grid street passes
  through.* Rejected as a decider: it reads 29th, 10th and 11th correctly as
  pass-through, but The Glenn scores 0.00 on Chester, which is the right answer,
  and Mcafee scores 0.93 against Avimor's 0.07, which is inverted. Both failures
  come from a place merging several roads, so "free ends" counts every cul-de-sac
  in the core rather than the ends of one road. Untested per-alignment.

What is in the code instead is a **proxy, not a mechanism**: a street crossing 5
or more plats whose naming plat holds under 60% of its platted length abstains.
It abstains on 30% of numbered street places against 3.7% of all others, an 8:1
enrichment, and it raised numbered-street abstentions from 16 of 93 to 39 of 93.
AP's objection stands and is not resolved: some alignments legitimately do run
through many subdivisions, so plat count is not the cause of anything.

Union coverage was checked as an alternative and does not separate: numbered
streets are 0.97 platted at the median, the same as everything else. The
additions cover the grid; they simply each own a slice.

## Checking the result

Street names that resemble one of the plats covering them are a review aid only.
They are never written where the pipeline can see them, and they are not ground
truth, because the direction of naming is often the reverse of what it looks
like: a 2023 plat called *Wichita* holding 9% of a street that has sat inside
Ranchero Estates since 1975 was named **after** the street.

`scripts/review_naming_plat.py` prints those cases for a person to judge. As of
2026-09-08 the chosen plat matches the street name in 271 places and does not in
89.

One known disagreement is deliberately left alone: `West Elder Court` is given to
Home Acres (1944, 503 m) over Elder (1952, 722 m). It is a 1,660 m "Court", so
the place merges several alignments and the case is genuinely ambiguous. Home
Acres is roughly fifteen separate subdivisions across Boise, presumably one
landowner, and Elder is a surname that may have been used twice. Chasing it would
be overfitting to one street.
