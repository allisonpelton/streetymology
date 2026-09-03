"""Gazetteer roots (data) and build/load/index (mechanism), kept separate so
adding a category never touches working code."""
import json
from .config import DATA_DIR
from .wikidata import query, qid
from .normalize import key

# Taxa MUST match on P1843 (taxon common name); rdfs:label gives Latin binomials.
TAXON = """SELECT DISTINCT ?s ?n WHERE {{
  ?s wdt:P171* wd:{root} ; wdt:P1843 ?n . FILTER(lang(?n)="en") }}"""

INSTANCE = """SELECT DISTINCT ?s ?n WHERE {{
  ?s wdt:P31/wdt:P279* wd:{root} ; rdfs:label ?n . FILTER(lang(?n)="en") }}"""

ROOTS: dict[str, str] = {
    "bird":         TAXON.format(root="Q5113"),
    "plant":        TAXON.format(root="Q756"),
    "mammal":       TAXON.format(root="Q7377"),
    "mineral":      INSTANCE.format(root="Q7946"),
    "us_state":     """SELECT DISTINCT ?s ?n WHERE {
        ?s wdt:P31 wd:Q35657 ; rdfs:label ?n . FILTER(lang(?n)="en") }""",
    "us_president": """SELECT DISTINCT ?s ?n WHERE {
        ?s wdt:P39 wd:Q11696 ; rdfs:label ?n . FILTER(lang(?n)="en") }""",
}

# Domains whose entries are people: also index by surname (2 -> 36 for presidents).
PERSON_DOMAINS = {"us_president"}


def path(domain: str):
    return DATA_DIR / f"gaz_{domain}.json"


def build(domain: str) -> int:
    rows = query(ROOTS[domain])
    recs = [{"qid": qid(r["s"]), "name": r["n"]} for r in rows if r.get("n")]
    path(domain).write_text(json.dumps(recs))
    return len(recs)


def load(domain: str) -> list[dict]:
    return json.loads(path(domain).read_text())


def available() -> list[str]:
    return sorted(d for d in ROOTS if path(d).exists())


def index(domain: str) -> dict[str, list[dict]]:
    """Map comparison-key -> entries. Person domains also indexed by surname."""
    idx: dict[str, list[dict]] = {}
    person = domain in PERSON_DOMAINS
    for r in load(domain):
        entry = {"qid": r["qid"], "name": r["name"], "via": "full"}
        idx.setdefault(key(r["name"]), []).append(entry)
        if person:
            parts = r["name"].split()
            if len(parts) > 1:
                idx.setdefault(key(parts[-1]), []).append({**entry, "via": "surname"})
    return idx
