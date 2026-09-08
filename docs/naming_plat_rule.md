# Which plat named the street

How the pipeline decides which recorded plat gave a street its name, what was
tried and rejected, and what is still unsound. Measured against the OSM extract
of 2026-09-08 and the Ada County Assessor's 8,000 recorded plats.

Regenerate every figure here with:

    python scripts/build_place_context.py          # the rule, and its coverage
    python scripts/review_naming_plat.py --contested   # top two plats near-tied
    python scripts/review_naming_plat.py --numbered    # grid streets: the hard case
    python scripts/review_naming_plat.py --weak

> **Supersedes the CLEAN_SHARE experiment.** An earlier version of this document
> tuned a threshold on the share of a single OSM *way* lying inside a plat. That
> parameter no longer exists. It was measuring mapping accidents: OSM splits a
> street at arbitrary points, so "share of a way" varies with how the street was
> edited. The comparison that retired it — 0.4 handing Quail Ridge Drive to
> Briarhill on an 8 m clip — is kept below because the failure mode recurs.

## The rule

Two questions, answered separately. Tangling them was the mistake in the previous
version.

**1. Was this street laid out by plats at all?** `confidence` is the fraction of
the street lying inside any plat. East Meadow View Road, a farm road, is 0.15;
Retort Avenue is 1.00. Below `MIN_PLATTED` (0.25) no plat is named at all.

**2. Which plat named it?** The oldest plat with a *material* claim — one holding
at least `MATERIAL_RATIO` (0.5) of the metres the leading plat holds. The count
of material plats is reported as `contenders`. Ambiguity here says nothing about
question 1: Retort sits in three plats at a third each and is no less certainly a
platted street for it.

`theme_confidence` is `confidence × era_weight`, the era ramping from 0.15 at
1915 to 1.0 at 1965.

Metres are measured on the merged geometry of a place, not per OSM way, since way
splits are arbitrary. Runs re-entering a plat within `BRIDGE_M` (60 m) count as
one: 41% of naming plats are entered more than once, because boundaries detour
around park parcels and phase lines. Phases of one plat are joined on base name,
their metres added, the earliest recording taken as the date.

Five numbers in total: `BRIDGE_M`, `MATERIAL_RATIO`, `MIN_PLATTED`, and the two
era endpoints.

### What this replaced, and why

The previous version multiplied three terms with floors:

    score = cover × (0.5 + 0.5 × continuity) × (0.5 + 0.5 × dominance × platted)

It double-counted. `dominance` is `inside ÷ (platted × street)`, which equals
`cover` whenever a street is fully platted, so the score squared cover and
punished Retort twice for the single fact of sharing its street with two
neighbours — precisely the case where the oldest plat is the obvious answer. The
0.5 floors existed only to stop a term zeroing a score, were never justified by
anything, and are gone with it. Twelve tunables became five.

As of 2026-09-08: confidence median 1.00, under 0.5 for 1.2% of places; theme
confidence median 1.00, under 0.25 for 5.4%; 18.2% have more than one contender;
1.4% name no plat.

## What the numbers look like

    street            plat                  confidence   theme   contenders
    Retort Avenue     Placerville 2007         1.00       1.00        3
    29th Street       West Side 1905           1.00       0.15        4
    Chester Lane      The Glenn 1946           0.96       0.65        2
    Quail Ridge Dr    Quail Ridge 1989         1.00       1.00        1
    Copenhagen Lane   Danish Flats 2025        1.00       1.00        1
    Sycamore Drive    Sycamore Drive 1940      1.00       0.57        1
    Meadow View Road  none                     -          -           -

Retort and 29th Street are both fully platted and are separated by era alone.
Meadow View abstains because 15% of it lies in any plat.



    Copenhagen Lane  Danish Flats 2025   score 0.86  confidence 0.94
    Sycamore Drive   Sycamore Drive 1940 score 0.75  confidence 0.88
    Quail Ridge Dr   Quail Ridge 1989    score 0.63  confidence 1.00
    Chester Lane     The Glenn 1946      score 0.46  confidence 0.64
    Camden Avenue    Fairmont Park 1972  score 0.32  confidence 0.55
    Retort Avenue    Placerville 2007    score 0.24  confidence 0.36
    10th Street      Boise Townsite 1867 score 0.24  confidence 0.41
    29th Street      Cruzen 1906         score 0.19  confidence 0.32

Under the two-factor rule these separate cleanly, but only because of the era
weight; the geometry still cannot tell them apart.

## Plat names are membership evidence, not theme evidence

Two cautions from AP, both of which argue against reading a theme off the plat
name:

- the recorded name is often a bare given name or surname while the subdivision's
  sign carries the name people actually use;
- name-only plats are common before 1950 and, today, mostly divide farmland,
  where there are no streets and nothing to derive beyond the name itself.

Membership still matters even when the name says nothing: it is what groups a
street with its peers. 21 places take a naming plat whose name carries no theme
at all — `R E`, `One`, `Mixed Use`, `C P` — and 132 have a single-word plat name
of five letters or fewer, mostly surnames.

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

## The unsound part: streets the plats grew around

Boise's numbered grid streets are laid out by the town, with additions filed
piecemeal along them for decades. The score marks them down — 29th Street 0.19,
10th Street 0.24 — but does not separate them from a weak correct answer: Retort
Avenue is right at 0.24.

The two are **structurally identical in the geometry**. Retort sits in three
plats holding 118 m, 109 m and 105 m of it; 29th sits in plats holding 674 m,
399 m, 396 m and 391 m. Same shape, same proportions, different history. Six
hypotheses were tested against the data and none separates them:

| hypothesis | result |
|---|---|
| the naming plat owns land on **both sides** of the street | rejected. Cruzen holds 29% of 29th Street's left offset and 30% of its right; Quail Ridge, correct, sits at 0.28/0.39 |
| a developer's street **terminates** inside its plat, a grid street passes through | rejected, including on a fair per-alignment test. The correct plat frequently holds a street's MIDDLE while later, smaller plats hold its ends, so terminating inside a plat is weak evidence *against*: The Glenn 0/2 on Chester and Avimor No 09 0/2, both correct, against Mcafee 2/2, wrong |
| plat boundaries meet a street they laid out **at junctions**, and cut a pre-existing street mid-block | rejected. Nearly every plat scores 100%, including Cruzen on 29th. Ada County plat boundaries follow rights-of-way |
| a **fully platted** street was created by plats | rejected, twice over. It does not discriminate — 83.6% of streets are within 10 m of fully platted — and AP's objection stands independently: a street dipping out of its plat where it meets an arterial must behave like one that does not |
| **junction density**: a grid street crosses many others | rejected. Numbered streets 1.05 attachments per 100 m, everything else 1.07. Retort is denser (2.11) than 29th (1.05), the opposite of the prediction |
| **era**: the grid is old | correlates strongly — earliest plat is pre-1950 for 75.3% of numbered streets against 14.5% of others — but is not causal, and using it would punish `Sycamore Drive → Sycamore Drive 1940` and `Chester → The Glenn 1946`, both correct |
| **date spread** across the covering plats | the best correlate found: numbered median 45 years, others 18. Still not a decider — Chester spans 51 years and Wichita 48, and both are right |

Plat geometry alone cannot tell a street the plats were built around from one
they built: the two leave the same footprint. What differs is history, and the
only trace of history here is the date.

## Age as a weight, not a cutoff

Date is used, but only where a wrong answer is cheap. AP's rule: a plat recorded
before about 1950 is never a source of theme. The exceptions — trees and
presidents — are self-evident from the street name and need no subdivision. Such
a plat is still wanted for membership.

So `theme_confidence = confidence × era_weight`, where the weight ramps from 0.15
at 1915 to 1.0 at 1965. It never touches the geometric score and never changes
which plat is chosen. Graded rather than all-or-nothing, so a 1946 plat is damped
and not discarded.

This is what finally separates the two cases six geometric hypotheses could not:

    street            plat                  confidence   theme confidence
    Retort Avenue     Placerville 2007         0.36           0.36
    29th Street       Cruzen 1906              0.32           0.05
    11th Street       Boise Townsite 1867      0.42           0.06
    Chester Lane      The Glenn 1946           0.64           0.43
    Sycamore Drive    Sycamore Drive 1940      0.88           0.51
    Quail Ridge Dr    Quail Ridge 1989         1.00           1.00

Median theme confidence is 1.00; 4.6% of places fall below 0.25.

It is a proxy for a development pattern a person would recognise on sight, and it
does not fix everything: 9th Avenue still takes Canna Lily Estates (1995) at 0.59,
because that plat really is modern.

A plat-count proxy was tried and removed: abstain when a street crosses 5+ plats
and its naming plat holds under 60% of the platted length. An 8:1 enrichment on
numbered streets, but no mechanism, and AP's objection was decisive — some
alignments legitimately run through many subdivisions.

## Checking the result

Street names that resemble one of the plats covering them are a review aid only.
They are never written where the pipeline can see them, and they are not ground
truth, because the direction of naming is often the reverse of what it looks
like: a 2023 plat called *Wichita* holding 9% of a street that has sat inside
Ranchero Estates since 1975 was named **after** the street.

`scripts/review_naming_plat.py` prints those cases for a person to judge, and
`--contested` lists the places where the top two plats score within 0.05.

Contested cases divide into two kinds. Some are ties the age preference resolves
correctly — West Lupine Street goes to Wildflower (1977) over Settlers Meadow
(1978), and lupine is a wildflower; West Vega Lane goes to Shooting Comet (1996)
over Rockbridge (2002), and Vega is a star. Others are streets that form the
boundary between two developments, each holding half, where no single answer is
right. And the age preference can lose: South Wardle Street is split evenly
between Wardle (1941) and State (1891), and the older one wins.

One known disagreement is deliberately left alone: `West Elder Court` is given to
Home Acres (1944, 503 m) over Elder (1952, 722 m). It is a 1,660 m "Court", so
the place merges several alignments and the case is genuinely ambiguous. Home
Acres is roughly fifteen separate subdivisions across Boise, presumably one
landowner, and Elder is a surname that may have been used twice. Chasing it would
be overfitting to one street.

## How often it is wrong

Fifty places judged by AP across two draws, neither of them streets the rule was
built on. Regenerate with `scripts/estimate_naming_plat_error.py`.

- **Sample 1**, 20 places drawn uniformly: 18 right. Its two failures scored 0.52
  and 0.62 while every correct row was at or above 0.89, so confidence separated
  them completely.
- **Sample 2**, 30 places stratified by confidence and restricted to the 41% of
  places covered by more than one plat: 17 right. Deliberately pessimistic — it
  excludes the single-plat majority and oversamples weak bands.

Reweighting sample 2 by band population and combining the strata:

    overall expected error                       3%
    wrong AND presented at theme confidence >0.6  1.1%

**The 3% is a central estimate, not a ceiling.** The 0.95-1.00 band holds 87% of
the ambiguous stratum and rests on six judged rows with no errors; if its true
rate were 5% the overall figure would be 4.7%, and at 10% it would be 6.5%. The
honest range is 3-7% overall, 1-2% presented confidently.

Errors concentrate where confidence is low: 67% wrong in the 0.4-0.8 bands, which
together are 6% of the population.

## Failure modes found, and what can be done about them

| mode | example | fixable? |
|---|---|---|
| the street was never named by any plat — former county and farm roads the plats grew around | Duncan, Eugene, Lewis, Waltman, Aikens, Horseshoe Bend | no signal found. AP: county roads are not reliably PLSS-aligned — the river breaks the grid, some run mid-mile, and some mid-mile roads are new enough to be themed |
| platted but unnamed: the plat laid the street out without naming it | Hartman, Aikens | not from this data. "Laid out by" and "named by" are different events and the pipeline conflates them |
| the plat polygon was redrawn by later replats until it no longer contains the street | Saxton, Ballard | no. The evidence is destroyed in the source |
| OSM road geometry is wrong | Fisher Park | not a pipeline problem |
| the street was renamed after platting | Breneman, formerly Pennsylvania Avenue | no |
| the name comes from a person or feature the plat merely echoes | Aikens (property owner), Table Rock (the mountain), James Court (a sheriff, via the plat's namesake) | no, and the model may do better than the geometry here |

Every mode above is a limit of the source data rather than of the rule. That is
the reason this line of work was stopped.
