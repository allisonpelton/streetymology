# Choosing CLEAN_SHARE: which plat named the street

Measured 2026-09-08 against the OSM extract of that date (8,504 analysed places)
and the Ada County Assessor's 8,000 recorded plats.

Regenerate with:

    python scripts/compare_clean_share.py --low 0.4 --high 0.9

## The rule being tuned

Several plats can cover one street. The naming plat is taken to be the **oldest
plat holding a whole segment cleanly inside it**; `CLEAN_SHARE` sets what
"cleanly" means as a fraction of that segment's length. Where no plat qualifies,
the largest share of the whole street wins.

Pure earliest-date fails without the clean test: 39.1% of analysed places sit in
more than one plat, and in 56.5% of those the earliest is not the largest share.
Pre-1950 filings are acreage plats later re-platted, so they own the dirt and not
the name — Copenhagen Lane belongs to Danish Flats (2025, 0.90), not to Ora Dell
(1910, 0.10).

## 0.4 against 0.9

| | 0.9 | 0.4 |
|---|---|---|
| naming plat from a clean segment | 78.0% | 94.4% |
| places whose naming plat differs from the other threshold | \- | 633 (7.4%) |
| of those, the lower threshold picks an older plat | \- | 621 of 633 |
| median years older | \- | 10 (max 113) |
| moved onto a pre-1950 plat | \- | 122 (19% of changes) |

0.4 buys 16 points of coverage and pays for them with wrong answers. A short stub
clipped by an old plat qualifies as "cleanly laid out by it", and because the
oldest candidate wins, the old plat takes the name:

    West Quail Ridge Drive   0.9-> Quail Ridge     1989 0.99   0.4-> Briarhill           1977 0.01
    North Milestone Way      0.9-> Milestone Ranch 2023 0.99   0.4-> Hoot Nanney Farms   2010 0.01
    North Bright Light Ave   0.9-> Stargazer       2026 0.98   0.4-> Hutton Ranchettes   1998 0.02

Quail Ridge Drive being named by the Quail Ridge plat is about as certain as this
data gets, and 0.4 breaks it. **0.9 stands.**

## What 0.9 still gets wrong

130 places (1.5%) end up with a naming plat holding under 10% of the whole
street — one segment lies cleanly inside an old plat while the rest of the street
does not:

    North Lakeharbor Lane  named-> Berridge   1908 0.01   largest Lakeharbor 1985 0.60
    East River Run Drive   named-> H G Myers  1962 0.01   largest River Run  1981 0.39
    North Roseland Way     named-> Rusty Spur 1994 0.01   largest Roselands  2013 0.41

A floor of about 0.10 on the naming plat's share of the whole street would fix
these without disturbing the 78%. Not yet implemented.

Note what the failures have in common: the plat name **is** the street name in
each case. That agreement is direct etymological evidence and the pipeline does
not use it anywhere.
