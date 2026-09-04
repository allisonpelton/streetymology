"""Gazetteer roots (data) and build/load/index (mechanism).

WDQS enforces a hard 60s deadline per query and 60s of processing time per
minute per client. Large domains are therefore paged; keep pages modest and
never run these concurrently.
"""
import hashlib
import json
import time
from dataclasses import dataclass
from .config import DATA_DIR
from .wikidata import query, qid
from .normalize import entity_key

# Taxa MUST match on P1843 (taxon common name); rdfs:label yields Latin binomials.
# skos:altLabel adds ~3x more names (Acer saccharinum: "river maple", "soft maple",
# "white maple" alongside "silver maple") but aliases are noisier, so provenance is
# tracked and match.py scores them lower.
# Aliases are NOT fetched here. Adding a skos:altLabel UNION inside the P171*
# traversal made every taxon query exceed the WDQS deadline. They are fetched in
# a separate pass keyed by QID (scripts/fetch_aliases.py), which is cheap and
# reliable, and merged at index time.
TAXON = """SELECT DISTINCT ?s ?n WHERE {{
  ?s wdt:P171* wd:{root} ; wdt:P1843 ?n . FILTER(lang(?n)="en") }}"""

# Deep P171* traversal from a kingdom root can exceed the WDQS deadline and, worse,
# return PARTIAL results without erroring. Plants hit this: Q756 (Plantae) yielded
# 22466 taxa while angiosperms ALONE hold 34201, and silver/red/sugar maple were all
# missing. Large kingdoms are therefore split into clades that each complete.
TAXON_CLADES = {
    "plant": ["Q25314", "Q133712", "Q373615", "Q25347"],   # angiosperms, gymnosperms, ferns, bryophytes
}

INSTANCE = """SELECT DISTINCT ?s ?n WHERE {{
  ?s wdt:P31/wdt:P279* wd:{root} ; rdfs:label ?n . FILTER(lang(?n)="en") }}"""

IN_US = """SELECT DISTINCT ?s ?n WHERE {{
  ?s wdt:P31/wdt:P279* wd:{root} ; wdt:P17 wd:Q30 ; rdfs:label ?n .
  FILTER(lang(?n)="en") }}"""


@dataclass(frozen=True)
class Root:
    sparql: str | tuple
    tier: str = "concept"   # concept | name | person
    paged: bool = False
    precision: str = "high"  # high | low - see artifacts/gazetteer_precision.md
    min_rows: int = 20      # sanity floor; see build() for why


ROOTS: dict[str, Root] = {
    # --- living things -------------------------------------------------
    "bird":        Root(TAXON.format(root="Q5113")),
    "plant":       Root(tuple(TAXON.format(root=r) for r in TAXON_CLADES["plant"])),
    "mammal":      Root(TAXON.format(root="Q7377")),
    "fish":        Root(TAXON.format(root="Q127282"), precision="low"),  # generic common names
    "insect":      Root(TAXON.format(root="Q1390"), paged=True),
    "amphibian":   Root(TAXON.format(root="Q10908")),
    # --- earth ---------------------------------------------------------
    "mineral":     Root(INSTANCE.format(root="Q7946")),
    "gemstone":    Root(INSTANCE.format(root="Q83437")),
    "constellation": Root(INSTANCE.format(root="Q8928")),
    # --- places --------------------------------------------------------
    "us_state":    Root("""SELECT DISTINCT ?s ?n WHERE {
                       ?s wdt:P31 wd:Q35657 ; rdfs:label ?n . FILTER(lang(?n)="en") }"""),
    "country":     Root(INSTANCE.format(root="Q6256")),
    "us_mountain": Root(IN_US.format(root="Q8502"), paged=True, precision="low"),
    "us_river":    Root(IN_US.format(root="Q4022"), paged=True, precision="low"),
    "us_lake":     Root(IN_US.format(root="Q23397"), paged=True, precision="low"),
    "national_park": Root(IN_US.format(root="Q46169")),
    "ski_resort":  Root(INSTANCE.format(root="Q130003")),
    "golf_course": Root(INSTANCE.format(root="Q1048525"), paged=True),
    "idaho_place": Root("""SELECT DISTINCT ?s ?n WHERE {
      {
        ?s wdt:P31/wdt:P279* ?t . VALUES ?t { wd:Q486972 wd:Q13410433 }
        ?s wdt:P131* wd:Q1221 .
      } UNION {
        ?s wdt:P31/wdt:P279* ?t2 . VALUES ?t2 { wd:Q46831 wd:Q8502 wd:Q4022 wd:Q23397 wd:Q131681 }
        ?s wdt:P131* wd:Q1221 .
        [] schema:about ?s ; schema:isPartOf <https://en.wikipedia.org/> .
      }
      ?s rdfs:label ?n . FILTER(lang(?n)="en") }"""),
    # --- culture -------------------------------------------------------
    "us_ethnic_group": Root("""SELECT DISTINCT ?s ?n WHERE {
                       ?s wdt:P31/wdt:P279* wd:Q41710 ; wdt:P17 wd:Q30 ;
                          rdfs:label ?n . FILTER(lang(?n)="en") }"""),
    "greek_deity": Root(INSTANCE.format(root="Q22989102")),
    "norse_deity": Root(INSTANCE.format(root="Q16513881")),
    "roman_deity": Root(INSTANCE.format(root="Q11688446")),
    "dog_breed":   Root(INSTANCE.format(root="Q39367")),
    "horse_breed": Root(INSTANCE.format(root="Q1160573")),
    "grape_variety": Root(INSTANCE.format(root="Q958314"), precision="low"),
    # --- added 2026-09-04 after probing yield with scripts/probe_domain.py.
    # UNVALIDATED: no hand-labelled rows cover these four, so their precision
    # marking is provisional. Label before quoting a precision figure for them.
    "element":    Root(INSTANCE.format(root="Q11344")),          # 9 new matches
    "colour":     Root(INSTANCE.format(root="Q1075")),           # 55 new matches
    # P279* only: P31/P279* sweeps in individual named instruments and software.
    "instrument": Root("""SELECT DISTINCT ?s ?n WHERE {
        ?s wdt:P279* wd:Q34379 ; rdfs:label ?n . FILTER(lang(?n)="en") }"""),
    # Restricted to stars with an English Wikipedia article; the unrestricted
    # set is mostly catalogue designations.
    "star":       Root("""SELECT DISTINCT ?s ?n WHERE {
        ?s wdt:P31/wdt:P279* wd:Q523 ; rdfs:label ?n . FILTER(lang(?n)="en")
        [] schema:about ?s ; schema:isPartOf <https://en.wikipedia.org/> . }"""),
    # --- people ---------------------------------------------------------
    "us_president": Root("""SELECT DISTINCT ?s ?n WHERE {
                       ?s wdt:P39 wd:Q11696 ; rdfs:label ?n . FILTER(lang(?n)="en") }""",
                       tier="person"),
}

PERSON_DOMAINS = {d for d, r in ROOTS.items() if r.tier == "person"}
HIGH_PRECISION = {d for d, r in ROOTS.items() if r.precision == "high"}
PAGE = 50_000


def path(domain: str):
    return DATA_DIR / f"gaz_{domain}.json"


class GazetteerTooSmall(RuntimeError):
    """A root returned far fewer rows than expected.

    Wikidata is a live, community-edited upstream dependency. Editors merge,
    split, deprecate and reclassify items continuously, so a root that worked
    last month can quietly stop matching anything. A category that silently
    returns zero rows is indistinguishable from a category that legitimately
    has no matches in Ada County -- the whole category would vanish from the
    map and nobody would notice until the results looked thin.

    Failing loudly turns a silent data-quality regression into an obvious one,
    and preserves the previous good file instead of overwriting it with junk.
    """


def root_hash(domain: str) -> str:
    sp = ROOTS[domain].sparql
    blob = "".join(sp) if isinstance(sp, tuple) else sp
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def build(domain: str) -> int:
    root = ROOTS[domain]
    recs, seen = [], set()
    if isinstance(root.sparql, tuple):
        rows = []
        for i, sub in enumerate(root.sparql, 1):
            rows += query(sub, timeout=70)
            print(f"      clade {i}/{len(root.sparql)}: {len(rows)} rows so far", flush=True)
            time.sleep(2)
    elif not root.paged:
        rows = query(root.sparql, timeout=70)
    else:
        rows, offset = [], 0
        while True:
            page = query(f"{root.sparql}\nORDER BY ?s LIMIT {PAGE} OFFSET {offset}", timeout=70)
            rows += page
            if len(page) < PAGE:
                break
            offset += PAGE
    for r in rows:
        if not r.get("n"):
            continue
        q = qid(r["s"])
        if (q, r["n"]) in seen:
            continue
        seen.add((q, r["n"]))
        recs.append({"qid": q, "name": r["n"]})
    if len(recs) < root.min_rows:
        raise GazetteerTooSmall(
            f"{domain}: {len(recs)} rows, expected >= {root.min_rows}. "
            f"The root QID may have been merged or reclassified upstream."
        )
    path(domain).write_text(json.dumps({"root_hash": root_hash(domain), "entries": recs}))
    return len(recs)


def is_stale(domain: str) -> bool:
    """True if the cached file was built from a different query than the current
    root definition. Prevents an edited root from silently reusing old results."""
    if not path(domain).exists():
        return True
    try:
        return json.loads(path(domain).read_text()).get("root_hash") != root_hash(domain)
    except (json.JSONDecodeError, AttributeError):
        return True


def load(domain: str) -> list[dict]:
    raw = json.loads(path(domain).read_text())
    return raw["entries"] if isinstance(raw, dict) else raw   # tolerate old format


def available(tier: str | None = None) -> list[str]:
    return sorted(d for d, r in ROOTS.items()
                  if path(d).exists() and (tier is None or r.tier == tier))


ALIAS_FILE = "gaz_aliases.json"

# Aliases are merged only for domains whose vocabulary is distinctive. Adding
# them to the GNIS geography domains would multiply names on gazetteers that are
# already the main source of false positives.
ALIAS_DOMAINS = {"plant", "bird", "mammal", "fish", "amphibian", "insect",
                 "dog_breed", "horse_breed", "gemstone", "mineral",
                 "constellation", "greek_deity", "roman_deity", "norse_deity",
                 "us_ethnic_group", "grape_variety"}


def load_aliases() -> dict[str, list[str]]:
    p = DATA_DIR / ALIAS_FILE
    return json.loads(p.read_text()) if p.exists() else {}


def index(domain: str, aliases: dict | None = None) -> dict[str, list[dict]]:
    """Map comparison-key -> entries. Person domains also indexed by surname.

    Aliases are merged if available and tagged src="alias" so match.py can score
    them below primary common names.
    """
    idx: dict[str, list[dict]] = {}
    person = domain in PERSON_DOMAINS
    aliases = (load_aliases() if aliases is None else aliases) \
        if domain in ALIAS_DOMAINS else {}
    for r in load(domain):
        e = {"qid": r["qid"], "name": r["name"], "via": "full", "src": "p1843"}
        for alt in aliases.get(r["qid"], ()):
            idx.setdefault(entity_key(alt), []).append(
                {"qid": r["qid"], "name": r["name"], "via": "full", "src": "alias"})
        idx.setdefault(entity_key(r["name"]), []).append(e)
        if person:
            parts = r["name"].split()
            if len(parts) > 1:
                idx.setdefault(entity_key(parts[-1]), []).append({**e, "via": "surname"})
    return idx
