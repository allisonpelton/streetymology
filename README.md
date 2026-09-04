# streetymology

Working out where Ada County, Idaho's street names come from — and publishing
the answers as a map and as verified contributions to OpenStreetMap.

Boise's streets are named after birds, gemstones, Basque families, racehorses,
Greek gods, and a subdivision's worth of Game of Thrones characters. Most,
though, are named after nothing at all. This project tries to tell those apart
honestly.

## Status

Data pipeline and evaluation complete for the deterministic (non-LLM) stage.

| | |
|---|---|
| Unique street names (OSM, Ada County) | 8,368 |
| Matched to a Wikidata entity | 648 (7.7%) |
| Hand-labelled for evaluation | 199 rows |
| Classifier AUC | 0.860 |
| Precision @ 89% recall | 85% |

## The interesting problem

Most street names have no etymology. A developer filling out a plat in 1978
picked "Meadowlark Lane" because it sounded pleasant, not to honour
*Sturnella neglecta*. So the hard part is not finding referents — it is
**refusing to invent them**.

Three failure modes drive the design:

**Coincidence.** "Rainbow", "Buffalo" and "Highland" match something in almost
any reference list. Scored down by word frequency.

**Wrong-person transfer.** The USGS has 100,000+ US streams in Wikidata, nearly
all named after somebody's surname. Boise's Blake Drive and Pennsylvania's
Blake Run are named after two different Blakes, independently. A string match
carries no etymology across.

**Invention.** "Lake Creek", "Trail Creek", "Long Lake" are descriptive names
that exist in every state. Matching one to a real creek 3,000 miles away is
confidently wrong. These need an `invented` class, not a better guess.

## How it works

1. **Acquire** — street centrelines from OpenStreetMap via Overpass; the Ada
   County Assessor's name list as a cross-check.
2. **Normalise** — reduce "East 31st Street" and "E 31st St" to a shared core
   name. Street names lose directionals and post-types; Wikidata labels never do.
3. **Gazetteers** — bulk-download 26 categories from Wikidata SPARQL. Free, and
   matching happens locally, so 8,368 names cost zero API requests.
4. **Score** — five plausibility signals, each catching a different failure mode.
5. **Evaluate** — against hand-labelled ground truth, with calibrated confidence.
6. **Review** — every proposal checked by a human in JOSM before it touches OSM.

## Signals

| signal | AUC | catches |
|---|---|---|
| notability | 0.782 | bulk-import stubs nobody names a street after |
| commonness | 0.664 | coincidental collisions with everyday words |
| nameness | 0.649 | matches to features named after a different person |
| collision | 0.569 | strings matching many categories at once |
| **combined** | **0.860** | |

A place earns a street name by being **nearby or famous** — never both. Denmark
is 7,864 km away and obviously right; Cabarton, Idaho has zero Wikipedia
articles and is also right. Only obscure *and* distant fails.

## Quickstart

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # set STREETYMOLOGY_DATA_DIR
python scripts/build_gazetteer.py     # bulk Wikidata download (slow, serial)
python scripts/report_yield.py        # match rate
python scripts/fetch_metadata.py      # sitelinks, coordinates, name membership
python scripts/sample_for_review.py   # emit a labelling CSV
python scripts/merge_labels.py        # combine labelling passes
python scripts/evaluate_signals.py    # AUC and calibration
pytest tests/ -q
```

Downloaded data lives outside the repo. Hand-authored labels live in
`data/labels/` and are version-controlled — they cannot be regenerated.

## Honesty notes

- The 85% precision figure is **in-sample**. Weights were hand-set and evaluated
  on the same rows that informed them. It needs a held-out set before it means
  much.
- The remaining ~92% of streets are mostly thematic fill. That is a finding
  about how American suburbs are named, not a failure of the method.
- Nothing is uploaded to OpenStreetMap without human review, per the
  [Automated Edits code of conduct](https://wiki.openstreetmap.org/wiki/Automated_Edits_code_of_conduct).

## Next

Neighbouring-street clustering — the single most requested feature during
labelling. Themed subdivisions disambiguate their own members: Saturn Way is a
planet because Jupiter Street is round the corner. The same clustering should
identify invented names, which appear in blocks rather than alone.

## Licence

Code MIT. OpenStreetMap data ODbL. Wikidata CC0.
