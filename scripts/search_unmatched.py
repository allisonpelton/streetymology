"""Query the Wikidata search API for street names no gazetteer matches.

Curated gazetteers cannot reach entities whose label differs from the street
name -- Wikidata calls it "Harvard University", not "Harvard". wbsearchentities
does prefix/alias matching and finds them.

This is the Action API, not WDQS: no SPARQL limits, but the User-Agent policy
still applies and requests must be serial. Resumable; safe to interrupt.

Usage:
  python scripts/search_unmatched.py --limit 20     # sample, for timing
  python scripts/search_unmatched.py                # everything
"""
import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from streetymology.config import DATA_DIR, USER_AGENT
from streetymology import gazetteer as g, match
from streetymology.streets import osm_cores
from streetymology.normalize import normalize
import requests

API = "https://www.wikidata.org/w/api.php"
OUT = DATA_DIR / "search_unmatched.json"
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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()

    idx = match.build_indexes(g.available(), g.index)
    cores = osm_cores()
    unmatched = {k: normalize(v) for k, v in cores.items()
                 if not match.match(v, idx, fallback_domains=g.FALLBACK_DOMAINS)}
    cache = json.loads(OUT.read_text()) if OUT.exists() else {}
    todo = [k for k in sorted(unmatched) if k not in cache]
    if a.limit:
        todo = todo[:a.limit]
    print(f"{len(unmatched)} unmatched, {len(todo)} to query", flush=True)

    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    t0 = time.time()
    for i, k in enumerate(todo, 1):
        try:
            cache[k] = search(s, unmatched[k])
        except Exception as e:
            print(f"  {k}: {str(e)[:60]}", flush=True)
            time.sleep(3)
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
