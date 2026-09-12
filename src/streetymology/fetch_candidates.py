"""Query the Wikidata search API for every street name.

This is now the only candidate source. It was written to cover the names the
curated gazetteers missed; the gazetteer arm was retired on 2026-09-07 after it
reached 16.7% of streets against search's 73%, so the filter it applied is gone
and every core is searched.

Curated gazetteers cannot reach entities whose label differs from the street
name -- Wikidata calls it "Harvard University", not "Harvard". wbsearchentities
does prefix/alias matching and finds them.

This is the Action API, not WDQS: no SPARQL limits, but the User-Agent policy
still applies and requests must be serial. Resumable; safe to interrupt.

Usage:
  python -m streetymology.fetch_candidates --limit 20   # sample, for timing
  python -m streetymology.fetch_candidates              # everything
"""
import argparse
import json
import time
from streetymology.config import data_path, session
from streetymology.normalize import osm_cores

API = "https://www.wikidata.org/w/api.php"
OUT = data_path("search_unmatched.json")
PAUSE = 0.25          # serial and polite; the API has no published hard limit


def search(session, term, limit=5):
    r = session.get(API, params={
        "action": "wbsearchentities", "search": term, "language": "en",
        "uselang": "en", "type": "item", "limit": limit, "format": "json",
    }, timeout=30)
    r.raise_for_status()
    return [{"qid": h["id"], "label": h.get("label", ""),
             "description": h.get("description", ""),
             "matched": h.get("match", {}).get("text", ""),
             "match_type": h.get("match", {}).get("type", "")}
            for h in r.json().get("search", [])]


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()

    cores = osm_cores()
    unmatched = dict(cores)
    cache = json.loads(OUT.read_text()) if OUT.exists() else {}
    todo = [k for k in sorted(unmatched) if k not in cache]
    if a.limit:
        todo = todo[:a.limit]
    print(f"{len(unmatched)} unmatched, {len(todo)} to query", flush=True)

    s = session()
    t0 = time.time()
    for i, k in enumerate(todo, 1):
        try:
            # The core, not unmatched[k], which is the full street name. A
            # search for "South Jupiter Avenue" finds nothing; "jupiter" finds
            # the planet. The 1,392 cores searched the wrong way on 2026-09-10
            # returned 8 hits between them, all of them other cities' streets.
            cache[k] = search(s, k)
        except Exception as e:                       # noqa: BLE001
            # The session has already retried transport and 5xx errors. Getting
            # here means this one term is bad, so skip it and keep the run going.
            print(f"  {k}: {str(e)[:60]}", flush=True)
            continue
        if i % 200 == 0:
            el = time.time() - t0
            print(f"  {i}/{len(todo)}  {el:.0f}s elapsed, "
                  f"{el/i*(len(todo)-i)/60:.0f} min remaining", flush=True)
            OUT.write_text(json.dumps(cache))
        time.sleep(PAUSE)
    OUT.write_text(json.dumps(cache))
    hits = sum(1 for v in cache.values() if v)
    print(f"done in {time.time()-t0:.0f}s. {hits}/{len(cache)} names returned candidates")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
