"""Fetch surname/given-name status for STREET CORES, not candidate labels.

`scripts/fetch_metadata.py` feeds `fetch_nameness` the labels of gazetteer
candidates, so `meta_nameness.json` only ever covers streets that matched a
gazetteer -- 1,395 of 8,368. The equal-ground sets are drawn from the unmatched
pool by design, so the signal was near-absent exactly where it was being judged:
3 of 200 round-2 streets had any nameness data at all.

This asks the same question of the street's own core name, which is what the
signal is actually about: is "Gossett" a surname? Written to its own file so the
existing artifact is not overwritten.
"""
import argparse, json, time

from streetymology import rounds
from streetymology.config import data_path
from streetymology.normalize import key
from streetymology.streets import osm_cores
from streetymology.wikidata import query

OUT = "meta_nameness_cores.json"
CHUNK = 250


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def label_form(core):
    """Wikidata labels for names are title case; cores are lowercased keys."""
    return " ".join(w.capitalize() for w in core.split())


def fetch(cores):
    out = {}
    for i, batch in enumerate(chunks(cores, CHUNK), 1):
        vals = " ".join('"%s"@en' % label_form(c).replace('"', '') for c in batch)
        q = """SELECT ?n (SAMPLE(?sur) AS ?surname) (SAMPLE(?giv) AS ?given) WHERE {
          VALUES ?n {%s}
          ?item rdfs:label ?n .
          OPTIONAL { ?item wdt:P31/wdt:P279* wd:Q101352 . BIND(1 AS ?sur) }
          OPTIONAL { ?item wdt:P31/wdt:P279* wd:Q202444 . BIND(1 AS ?giv) }
        } GROUP BY ?n""" % vals
        for r in query(q, timeout=70):
            out[key(r["n"])] = {"surname": bool(r.get("surname")),
                                "given": bool(r.get("given"))}
        print(f"  chunk {i}: {len(out)} names resolved", flush=True)
        time.sleep(2)
    return out


def main():
    ap = argparse.ArgumentParser()
    rounds.add_argument(ap, default=None)
    ap.add_argument("--all", action="store_true", help="every OSM core, not one round")
    a = ap.parse_args()

    cores = osm_cores()
    if a.all:
        wanted = sorted(cores)
    elif a.round:
        import csv
        R = rounds.Round(a.round)
        with R.labels.open(newline="") as fh:
            wanted = sorted({key(r["street"]) for r in csv.DictReader(fh) if r.get("street")})
    else:
        raise SystemExit("pass --round N or --all")

    print(f"{len(wanted)} core name(s) to resolve")
    got = fetch(wanted)

    path = data_path(OUT)
    merged = json.loads(path.read_text()) if path.exists() else {}
    merged.update(got)
    path.write_text(json.dumps(merged))
    named = sum(1 for v in got.values() if v["surname"] or v["given"])
    print(f"\nwrote {path} ({len(merged)} total)")
    print(f"{named}/{len(wanted)} of this batch are a surname or given name")


if __name__ == "__main__":
    main()
