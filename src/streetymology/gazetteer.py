"""Gazetteer roots (data) and build/load/index (mechanism).

WDQS enforces a hard 60s deadline per query and 60s of processing time per
minute per client. Large domains are therefore paged; keep pages modest and
never run these concurrently.
"""
import hashlib
import json
from dataclasses import dataclass
from .config import DATA_DIR
from .wikidata import query, qid
from .normalize import entity_key

# Taxa MUST match on P1843 (taxon common name); rdfs:label yields Latin binomials.
TAXON = """SELECT DISTINCT ?s ?n WHERE {{
  ?s wdt:P171* wd:{root} ; wdt:P1843 ?n . FILTER(lang(?n)="en") }}"""

INSTANCE = """SELECT DISTINCT ?s ?n WHERE {{
  ?s wdt:P31/wdt:P279* wd:{root} ; rdfs:label ?n . FILTER(lang(?n)="en") }}"""

IN_US = """SELECT DISTINCT ?s ?n WHERE {{
  ?s wdt:P31/wdt:P279* wd:{root} ; wdt:P17 wd:Q30 ; rdfs:label ?n .
  FILTER(lang(?n)="en") }}"""


@dataclass(frozen=True)
class Root:
    sparql: str
    tier: str = "concept"   # concept | name | person
    paged: bool = False
    precision: str = "high"  # high | low - see artifacts/gazetteer_precision.md
    min_rows: int = 20      # sanity floor; see build() for why


ROOTS: dict[str, Root] = {
    # --- living things -------------------------------------------------
    "bird":        Root(TAXON.format(root="Q5113")),
    "plant":       Root(TAXON.format(root="Q756"), paged=True),
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
    return hashlib.sha256(ROOTS[domain].sparql.encode()).hexdigest()[:12]


def build(domain: str) -> int:
    root = ROOTS[domain]
    recs, seen = [], set()
    if not root.paged:
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


def index(domain: str) -> dict[str, list[dict]]:
    """Map comparison-key -> entries. Person domains also indexed by surname."""
    idx: dict[str, list[dict]] = {}
    person = domain in PERSON_DOMAINS
    for r in load(domain):
        e = {"qid": r["qid"], "name": r["name"], "via": "full"}
        idx.setdefault(entity_key(r["name"]), []).append(e)
        if person:
            parts = r["name"].split()
            if len(parts) > 1:
                idx.setdefault(entity_key(parts[-1]), []).append({**e, "via": "surname"})
    return idx
