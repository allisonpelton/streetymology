"""Bulk-fetch Wikidata metadata for match candidates.

Two passes, both chunked to stay well inside the WDQS limit of 60s processing
time per 60s per client:
  1. candidate QIDs  -> sitelinks, statement count, enwiki article, description
  2. matched strings -> is this also a surname (Q101352) / given name (Q202444)?

Pass 2 is the correct use of the name data we rejected as a gazetteer: asking
"is 'Blake' a surname?" is a useful penalty; asking "which surname?" is tautology.
"""
import json, re, time
from streetymology.config import data_path
from streetymology.wikidata import query
from streetymology import gazetteer as g, match
from streetymology.streets import osm_cores

CHUNK = 150


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def all_matches():
    cores = osm_cores()
    idx = match.build_indexes(g.available(), g.index)
    out = []
    for k, orig in cores.items():
        for c in match.match(orig, idx):
            out.append((orig, c))
    return out


def fetch_candidates(qids):
    out = data_path("meta_candidates.json")
    meta = json.loads(out.read_text()) if out.exists() else {}
    qids = [q for q in qids if q not in meta]
    print(f"  {len(qids)} still to fetch", flush=True)
    for i, batch in enumerate(chunks(qids, CHUNK), 1):
        q = """SELECT ?s (COUNT(DISTINCT ?sl) AS ?sitelinks)
                      (SAMPLE(?en) AS ?enwiki) (SAMPLE(?d) AS ?descr) WHERE {
          VALUES ?s {%s}
          OPTIONAL { ?sl schema:about ?s }
          OPTIONAL { ?en schema:about ?s ; schema:isPartOf <https://en.wikipedia.org/> }
          OPTIONAL { ?s schema:description ?d . FILTER(lang(?d)="en") }
        } GROUP BY ?s""" % " ".join("wd:" + x for x in batch)
        for r in query(q, timeout=70):
            meta[r["s"].rsplit("/", 1)[-1]] = {
                "sitelinks": int(r["sitelinks"]),
                "enwiki": bool(r.get("enwiki")), "description": r.get("descr", ""),
            }
        out.write_text(json.dumps(meta))
        if i % 10 == 0:
            print(f"  candidates chunk {i}: {len(meta)} total", flush=True)
        time.sleep(1)
    return meta


def fetch_coords(qids):
    """P625 coordinates, for the proximity signal.

    A place candidate 15 miles from Boise is plausible however obscure it is;
    an identically-named one in Alabama is not. Sitelink count cannot express
    that, because locally important features are often poorly documented.
    """
    out = data_path("meta_coords.json")
    coords = json.loads(out.read_text()) if out.exists() else {}
    todo = [q for q in qids if q not in coords]
    print(f"  {len(todo)} candidates still need coordinates", flush=True)
    for i, batch in enumerate(chunks(todo, CHUNK), 1):
        q = "SELECT ?s ?coord WHERE { VALUES ?s {%s} ?s wdt:P625 ?coord }" % (
            " ".join("wd:" + x for x in batch))
        found = set()
        for r in query(q, timeout=70):
            qid_ = r["s"].rsplit("/", 1)[-1]
            m = re.match(r"Point\(([-0-9.]+) ([-0-9.]+)\)", r["coord"])
            if m:
                coords[qid_] = [float(m.group(2)), float(m.group(1))]  # lat, lon
                found.add(qid_)
        for x in batch:
            coords.setdefault(x, None)      # remember "no coordinate"
        out.write_text(json.dumps(coords))
        if i % 10 == 0:
            print(f"  coords chunk {i}: {sum(1 for v in coords.values() if v)} located", flush=True)
        time.sleep(1)
    return coords


def fetch_nameness(strings):
    names = {}
    for i, batch in enumerate(chunks(strings, 250), 1):
        vals = " ".join('"%s"@en' % s.replace('"', '') for s in batch)
        q = """SELECT ?n (SAMPLE(?sur) AS ?surname) (SAMPLE(?giv) AS ?given) WHERE {
          VALUES ?n {%s}
          ?item rdfs:label ?n .
          OPTIONAL { ?item wdt:P31/wdt:P279* wd:Q101352 . BIND(1 AS ?sur) }
          OPTIONAL { ?item wdt:P31/wdt:P279* wd:Q202444 . BIND(1 AS ?giv) }
        } GROUP BY ?n""" % vals
        for r in query(q, timeout=70):
            names[r["n"]] = {"surname": bool(r.get("surname")), "given": bool(r.get("given"))}
        print(f"  nameness chunk {i}: {len(names)} total", flush=True)
        time.sleep(2)
    return names


if __name__ == "__main__":
    ms = all_matches()
    qids = sorted({c.qid for _, c in ms})
    strings = sorted({c.name for _, c in ms})
    print(f"{len(ms)} matches | {len(qids)} distinct QIDs | {len(strings)} distinct strings")
    cand = fetch_candidates(qids)
    (data_path("meta_candidates.json")).write_text(json.dumps(cand))
    co = fetch_coords(qids)
    nm = fetch_nameness(strings)
    (data_path("meta_nameness.json")).write_text(json.dumps(nm))
    located = sum(1 for v in co.values() if v)
    print(f"\nwrote meta_candidates.json ({len(cand)}), meta_coords.json "
          f"({located} located of {len(co)}), meta_nameness.json ({len(nm)})")
