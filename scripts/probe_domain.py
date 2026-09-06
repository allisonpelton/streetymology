"""Test a candidate gazetteer domain WITHOUT adopting it.

Fetches the domain, matches it against Ada County street names that nothing else
matches, and reports the hits so they can be eyeballed. A domain earns a place in
gazetteer.ROOTS only if it produces a useful number of plausible matches --
size alone says nothing, and broad domains full of ordinary English words
(colours, instruments) can be large and still worthless.
"""
import sys, time
from streetymology.wikidata import query, qid
from streetymology.normalize import entity_key, key
from streetymology import gazetteer as g, match
from streetymology.streets import osm_cores

CANDIDATES = {
    # P279* only: instrument TYPES. P31/P279* also sweeps in individual named
    # instruments, brands and software (MusE, "Lucy", Gibson).
    "instrument": """SELECT DISTINCT ?s ?n WHERE {
        ?s wdt:P279* wd:Q34379 ; rdfs:label ?n . FILTER(lang(?n)="en") }""",
    "colour": """SELECT DISTINCT ?s ?n WHERE {
        ?s wdt:P31/wdt:P279* wd:Q1075 ; rdfs:label ?n . FILTER(lang(?n)="en") }""",
    "solar_body": """SELECT DISTINCT ?s ?n WHERE {
        { ?s wdt:P31 wd:Q634 ; wdt:P397 wd:Q525 } UNION { ?s wdt:P31 wd:Q2199 }
        ?s rdfs:label ?n . FILTER(lang(?n)="en") }""",
    "star": """SELECT DISTINCT ?s ?n WHERE {
        ?s wdt:P31/wdt:P279* wd:Q523 ; rdfs:label ?n . FILTER(lang(?n)="en")
        [] schema:about ?s ; schema:isPartOf <https://en.wikipedia.org/> . }""",
    "element": """SELECT DISTINCT ?s ?n WHERE {
        ?s wdt:P31/wdt:P279* wd:Q11344 ; rdfs:label ?n . FILTER(lang(?n)="en") }""",
    # ruby/emerald/amethyst are P31 Q429795 "mineral variety" -- covered by
    # neither the old gemstone root (P31/P279* Q83437, which returned individual
    # famous stones like the Agra Diamond) nor the mineral root.
    "gem": """SELECT DISTINCT ?s ?n WHERE {
        { ?s wdt:P31/wdt:P279* wd:Q429795 } UNION { ?s wdt:P279* wd:Q83437 }
          UNION { ?s wdt:P31/wdt:P279* wd:Q7946 }
        ?s rdfs:label ?n . FILTER(lang(?n)="en")
        [] schema:about ?s ; schema:isPartOf <https://en.wikipedia.org/> . }""",
    "university": """SELECT DISTINCT ?s ?n WHERE {
        ?s wdt:P31/wdt:P279* wd:Q3918 ; wdt:P17 wd:Q30 ; rdfs:label ?n .
        FILTER(lang(?n)="en") }""",
}


def probe(name, sparql, unmatched, existing):
    rows = query(sparql, timeout=70)
    idx = {}
    for r in rows:
        idx.setdefault(entity_key(r["n"]), []).append((qid(r["s"]), r["n"]))
    new = {k: (v, idx[k][0]) for k, v in unmatched.items() if k in idx}
    also = sum(1 for k in existing if k in idx)
    print(f"\n=== {name}: {len(rows)} entities, {len(idx)} distinct names")
    print(f"    NEW matches (streets nothing else matched): {len(new)}")
    print(f"    overlaps existing matches: {also}")
    for k, (street, (q, label)) in sorted(new.items())[:20]:
        print(f"      {street:32} -> {label} ({q})")
    return len(new)


if __name__ == "__main__":
    idx = match.build_indexes(g.available(), g.index)
    cores = osm_cores()
    unmatched = {k: v for k, v in cores.items() if not match.match(v, idx)}
    existing = {k for k in cores if k not in unmatched}
    print(f"{len(unmatched)} unmatched street names to test against")
    wanted = sys.argv[1:] or list(CANDIDATES)
    for name in wanted:
        try:
            probe(name, CANDIDATES[name], unmatched, existing)
        except Exception as e:
            print(f"\n=== {name}: FAILED {str(e)[:70]}")
        time.sleep(3)
