# streetymology

Where do the names of the streets of Ada County, Idaho, come from?

Many of Boise's streets are named after birds, gemstones, racehorses,
Greek gods, and even Game of Thrones characters. Many more are named after nothing at all.
Who can identify their etymology better? Heuristics, a local resident, or an LLM?

## How it works

TODO: Expand and separate into stages

Street names are pulled from OpenStreetMap and normalized to remove directionals and suffixes. A selection of Wikidata categories are used to create gazetteers. Then, the names are checked against the gazetteer.

## Usage

Nothing for anyone to "use" yet. This will probably be a pipeline of scripts 
to run in order.

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
| OSM ingest | Overpass queries, street extraction, name normalization, landuse polygons | `src/streetymology/streets.py` | -2 |
| Subdivision mapping | Residential polygons traced from aerials and plats | *(upstream in OSM)* | 3 |
| Back-end code | All Python files and scripts | `src/streetymology/*.py` | -2 |
| Ground truth labels | Streets with correct etymology manually identified | `data/labels/` | 2 |
| Experiment design | Scoring, weights, signals | N/A | 1 |
| Repo tooling | Packaging, dependency locking, Claude Code config | `pyproject.toml`, `requirements.lock`, `.claude/` | -3 |
| Project instructions | CLAUDE.md, including the AI-usage principles | `CLAUDE.md` | 0 |
| Documentation | This README and the explainers | `README.md`, `docs/` | 3 |
| Write-up | Forthcoming blog post detailing the project | *(not built)* | 3 |
| OSM contribution | JOSM review of every street before upload | *(not started)* | 3 |
| Web map | Public map of results | *(not built)* | TBD |

## License

Code MIT. OpenStreetMap data ODbL. Wikidata CC0.
