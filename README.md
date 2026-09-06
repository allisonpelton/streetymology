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

TODO: Expand and separate into stages

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

## Usage

Nothing for anyone to "use" yet.

## AI transparency

The ratio of AI to human authorship varies across parts of the project. They 
are scored as follows:

  - -3 - Entirely AI generated with no human involvement
  - -2 - Entirely AI generated with some human assistance
  - -1 - Majority AI generated with some direct human edits
  - 0 - Mix of AI and human authorship
  - 1 - Majority human authored with some direct AI edits
  - 2 - Entirely human authored with some AI assistance
  - 3 - Entirely human authored with no AI involvement
  
| Component | What it covers | Key files | Score |
|---|---|---|:--:|
| Project direction | Goal, scope, method, what counts as an acceptable answer | — | 2 |
| OSM ingest | Overpass queries, street extraction, name normalization, landuse polygons | `src/streetymology/streets.py` | -3 |
| Subdivision mapping | Residential polygons traced from aerials and plats | *(upstream in OSM)* | 3 |
| Back-end code | All Python files and scripts | `*.py` | -3 |
| Ground truth labels | Streets with correct etymology manually identified | `data/labels/` | 2 |
| Experiment design | Scoring, weights, signals | N/A | -3 |
| Repo tooling | Packaging, dependency locking, Claude Code config | `pyproject.toml`, `requirements.lock`, `.claude/` | -3 |
| Project instructions | CLAUDE.md, including the AI-usage principles | `CLAUDE.md` | 0 |
| Documentation | This README and the explainers | `README.md`, `docs/` | 3 |
| Write-up | Forthcoming blog post detailing the project | *(not built)* | 3 |
| OSM contribution | JOSM review of every street before upload | *(not started)* | 3 |
| Web map | Public map of results | *(not built)* | TBD |

## License

Code MIT. OpenStreetMap data ODbL. Wikidata CC0.
