# streetymology

Where do the names of the streets of Ada County, Idaho, come from?

Many of Boise's streets are named after birds, gemstones, racehorses,
Greek gods, and even Game of Thrones characters. Many more are named after nothing at all.
Who can identify their etymology better? Heuristics, a local resident, or an LLM?

## Status

Data pipeline and evaluation complete for the deterministic (non-LLM) stage.

| | |
|---|---|
| Unique street names (OSM, Ada County) | 8,368 |
| Matched to a Wikidata entity | TBD |
| Hand-labelled for evaluation | 199 rows, 176 decided |
| Classifier AUC | TBD |
| Precision @ TBD recall | TBD |

## How it works

Street names are pulled from OpenStreetMap and normalized to remove directionals and suffixes. A selection of Wikidata categories are used to create gazetteers. Then, the names are checked against the gazetteer.

## Signals

From a subset of 176 street names with hand-labeled etymologies:

| signal | AUC | catches | mechanism |
|---|---|---|---|
| notability | TBD | obscure subjects unlikely to inspire a Boise street name | Wikidata sitelink count, capped at 20
| commonness | TBD | words too common to refer to a particular concept | Normalized wordfreq Zipf frequency, using the most common word for compounds |
| nameness | TBD | words that could be names, and are unlikely to refer to a singular individual | Wikidata string is instance of surname or given name |
| collision | TBD | words with multiple meanings of similar prominence, regardless of frequency | Count of matched domains in etymology list |
| subdivision grouping | TBD | streets in the same subdivision sharing a theme | High-quality categories matching multiple streets |
| **combined** | **TBD** | | |

`max(proximity, notability)` is also used for etymological candidates with a geographic location to select candidates that are nearby or notable.

For subdivision grouping, street midpoints are identified inside or adjacent to landuse polygons representing subdivisions.
The Wikidata domain matches for the subdivision's streets are compared against random chance based on
the frequency of names in the whole county matching the domain.

## Quickstart

Not yet. This is currently a series of scripts that were used to arrive at the current results. Refactoring will follow.

## License

Code MIT. OpenStreetMap data ODbL. Wikidata CC0.
