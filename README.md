# streetymology

Working out where Ada County, Idaho's street names come from — and publishing
the answers as a map and as verified contributions to OpenStreetMap.

Many of Boise's streets are named after birds, gemstones, racehorses,
Greek gods, and even Game of Thrones characters. Many more are named after nothing at all.
How many can we determine heuristically?

## Status

Data pipeline and evaluation complete for the deterministic (non-LLM) stage.

| | |
|---|---|
| Unique street names (OSM, Ada County) | 8,368 |
| Matched to a Wikidata entity | 648 (7.7%) |
| Hand-labelled for evaluation | 199 rows, 176 decided |
| Classifier AUC | 0.869 |
| Precision @ 68% recall | 93% |

## How it works

Street names are pulled from OpenStreetMap and normalized to remove directionals and suffixes. A selection of Wikidata categories are used to create gazetteers. Then, the names are checked against the gazetteer.

## Signals

From a subset of 176 street names with hand-labeled etymologies:

| signal | AUC | catches | mechanism |
|---|---|---|---|
| notability | 0.782 | obscure subjects unlikely to inspire a Boise street name | Wikidata sitelink count, capped at 20
| commonness | 0.664 | words too common to refer to a particular concept | Normalized wordfreq Zipf frequency, using the most common word for compounds |
| nameness | 0.649 | words that could be names, and are unlikely to refer to a singular individual | Wikidata string is instance of surname or given name |
| collision | 0.569 | words with multiple meanings of similar prominence, regardless of frequency | Count of matched domains in etymology list |
| subdivision grouping | 0.643 | streets in the same subdivision sharing a theme | High-quality categories matching multiple streets |
| **combined** | **0.869** | | |

`max(proximity, notability)` is also used for etymological candidates with a geographic location to select candidates that are nearby or notable.

For subdivision grouping, street midpoints are identified inside or adjacent to landuse polygons representing subdivisions.
The Wikidata domain matches for the subdivision's streets are compared against random chance based on
the frequency of names in the whole county matching the domain.

## Quickstart

Not yet. This is currently a series of scripts that were used to arrive at the current results. Refactoring will follow.

## Current caveats

- The 93% precision figure is **in-sample**. Weights were hand-set and evaluated
  on the same rows that informed them. It needs a held-out set before it means
  much.
- The remaining ~92% of streets aren't a match for any of the domains. They're likely generic, and a heuristic is unlikely to identify themes between them.

## Next

Subdivision clustering allows identification of thematic naming. Griffon is a mythological creature and a dog breed.
Griffon Street intersects Doberman Drive. Any other street in the subdivision whose name matches a dog breed probably is named for the dog breed.
This can also be used to identify invented names and avoid overconfidence: a subdivision likely has many themed names or none at all. 

## License

Code MIT. OpenStreetMap data ODbL. Wikidata CC0.
