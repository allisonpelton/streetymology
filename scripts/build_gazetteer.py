"""Build name gazetteers from Wikidata SPARQL. Free, unmetered, no LLM."""
import csv, io, json, os, sys, time
import requests

ENDPOINT = "https://query.wikidata.org/sparql"
UA = "streetymology/0.1 (https://github.com/allisonpelton/streetymology)"
OUT = os.environ.get("STREETYMOLOGY_DATA_DIR", "/workspace/streetymology-data")

# Taxa: match on P1843 (taxon common name), NEVER rdfs:label (Latin binomials).
TAXON = """SELECT DISTINCT ?s ?n WHERE {{
  ?s wdt:P171* wd:{root} ; wdt:P1843 ?n .
  FILTER(lang(?n)="en")
}}"""

QUERIES = {
    "bird":    TAXON.format(root="Q5113"),    # Aves
    "plant":   TAXON.format(root="Q756"),     # Plantae
    "mammal":  TAXON.format(root="Q7377"),    # Mammalia
    "fish":    TAXON.format(root="Q152"),     # Fish
    "mineral": """SELECT DISTINCT ?s ?n WHERE {
        ?s wdt:P31/wdt:P279* wd:Q7946 ; rdfs:label ?n . FILTER(lang(?n)="en") }""",
    "us_state": """SELECT DISTINCT ?s ?n WHERE {
        ?s wdt:P31 wd:Q35657 ; rdfs:label ?n . FILTER(lang(?n)="en") }""",
    "us_president": """SELECT DISTINCT ?s ?n WHERE {
        ?s wdt:P39 wd:Q11696 ; rdfs:label ?n . FILTER(lang(?n)="en") }""",
    "idaho_place": """SELECT DISTINCT ?s ?n WHERE {
        ?s wdt:P131* wd:Q1221 ; wdt:P31/wdt:P279* wd:Q486972 ;
           rdfs:label ?n . FILTER(lang(?n)="en") }""",
}


def run(q, tries=3):
    for i in range(tries):
        r = requests.post(ENDPOINT, data={"query": q},
                          headers={"Accept": "text/csv", "User-Agent": UA}, timeout=300)
        if r.ok:
            return list(csv.DictReader(io.StringIO(r.text)))
        time.sleep(5 * (i + 1))
    raise RuntimeError(f"SPARQL failed {r.status_code}: {r.text[:200]}")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    summary = {}
    for name, q in QUERIES.items():
        try:
            rows = run(q)
        except Exception as e:
            print(f"{name:14} FAILED  {e}", flush=True); continue
        recs = [{"qid": r["s"].rsplit("/", 1)[-1], "name": r["n"]} for r in rows if r.get("n")]
        with open(f"{OUT}/gaz_{name}.json", "w") as f:
            json.dump(recs, f)
        summary[name] = len(recs)
        print(f"{name:14} {len(recs):>7} names", flush=True)
    print("\n", summary)
