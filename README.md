# streetymology - matching street name origins to Wikidata by LLM

Where do the names of the streets of Ada County, Idaho, come from?

Early in Boise's founding, streets were usually numbered, named for 
their purpose, or for important residents, trees, presidents, and native 
Idaho peoples. This was common for many cities in the West, which is reflected 
in some of the most popular street names nationwide: Main, Second, Oak, and Park.

Development patterns changed after World War II. The post-war 
suburb offered developers an opportunity to theme large subdivisions. 
Meanwhile, municipalities began setting stricter naming rules, primarily to
improve mail delivery. The result was an explosion of unique names. Silver 
Trail in Kuna received local news coverage for its *Game of Thrones* theme. 
Other subdivisions are full of coinages. Sugarberry Woods in Eagle features 
Sugar Loaf, Sugar Bush, and Sugar Crest. While these names may be shared with 
real places, those places are not genuine etymologies.

Not all themes are obvious to everyone. What do Pratt, Bollman, and 
Baltimore have in common? They're all truss types. An LLM finds this easily,
but only architects and civil engineers are likely to spot it.

## How it works

Highways from OpenStreetMap and subdivision data from the Ada County Assessor 
are analyzed to identify clusters of potentially related names. Names are fed 
to the Wikidata API `wbsearchentities` search endpoint to find etymology 
candidates. Names, subdivision information, nearby streets, and Wikidata 
candidates are turned into an LLM prompt.

The LLM uses reasoning to identify themes and select one of the candidates. 
Alternatively, it can identify a name as invented, referring to a local, 
non-notable person or family, or as potentially having a valid Wikidata 
reference that was not listed.

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
| Documentation | This README | `README.md` | 3 |
| Write-up | Forthcoming blog post detailing the project | *(not built)* | 3 |
| OSM contribution | JOSM review of every street before upload | *(not started)* | 3 |
| Web map | Public map of results | *(not built)* | TBD |

## License

Code MIT. OpenStreetMap data ODbL. Wikidata CC0.
