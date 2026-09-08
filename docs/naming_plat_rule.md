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

Every hard threshold tried here broke a real street, so plats are **scored** and
the score travels with the answer. Three signals, each of which caught a failure
the others missed:

| signal | definition | the failure it catches |
|---|---|---|
| cover | metres of street inside the plat ÷ street length | a plat that laid a street out holds most of it |
| continuity | longest unbroken run ÷ metres inside | tells a plat the street runs through from one it crosses repeatedly |
| dominance | metres inside ÷ street's PLATTED metres | grid streets: Boise's numbered streets are 0.97 platted, but no addition owns them |

    score = cover × (0.5 + 0.5 × continuity) × (0.5 + 0.5 × dominance)

`confidence` is that score normalised across the plats covering the street, so a
lone weak plat is not mistaken for a strong one. Both are written to
`place_context.json` for every plat, not just the winner.

**Age is a preference, not a signal.** Among plats scoring within `AGE_BAND`
(0.8) of the best, the oldest wins — it laid the ground out. It cannot override a
clearly better-scoring plat, because pre-1950 acreage filings own the dirt and
not the name. Below `MIN_SCORE` (0.15) no plat is named at all.

**Re-entry is normal and is bridged.** 41% of naming plats are entered more than
once, because plat boundaries detour around park parcels, school sites and phase
lines. Pieces whose ends are within 60 m count as one run. The parameter is not
sensitive: no bridging → 60 m changes 113 choices, 60 → 150 m changes 20,
60 → 400 m changes 32.

**Phases are one naming act.** `SUTTERS MILL SUB NO 01` and `NO 02` are joined on
base name, their metres added, the earliest recording taken as the date.

As of 2026-09-08: median naming score 0.87, p10 0.33; 2.5% of analysed places
name no plat; 4.6% are contested, meaning the top two plats score within 0.05.

## What the scores look like

    Copenhagen Lane  Danish Flats 2025   score 0.86  confidence 0.94
    Sycamore Drive   Sycamore Drive 1940 score 0.75  confidence 0.88
    Quail Ridge Dr   Quail Ridge 1989    score 0.63  confidence 1.00
    Chester Lane     The Glenn 1946      score 0.46  confidence 0.64
    Camden Avenue    Fairmont Park 1972  score 0.32  confidence 0.55
    Retort Avenue    Placerville 2007    score 0.24  confidence 0.36
    10th Street      Boise Townsite 1867 score 0.24  confidence 0.41
    29th Street      Cruzen 1906         score 0.19  confidence 0.32

Retort is correct at 0.24 and 29th Street is wrong at 0.19, which is why a hard
cutoff kept breaking one to fix the other. The score does not separate them; it
reports how weak both are, and the prompt can say so.

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
