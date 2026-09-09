"""Fetch full way geometry for named Ada County streets.

`osm_ways_center.json` holds one Overpass `out center` point per way. That is
enough to place a street but not to measure distance between two of them: a long
way's centroid can sit hundreds of metres from the street it branches off, so the
two never register as neighbours. 4.8% of cores get no nearby streets at all.

`out geom` returns every node of every way, so distance can be measured between
the polylines themselves rather than between their midpoints.

Written to `osm_ways_geom.json`; the centre file is left alone so nothing that
depends on it breaks while the switch is made.
"""
import argparse, json, sys, time, urllib.parse, urllib.request

from streetymology.config import OVERPASS_ENDPOINTS, USER_AGENT, data_path

OUT = "osm_ways_geom.json"

# Road classes only. Motorway and trunk are state highways nobody platted and
# never belonged here; path, proposed, cycleway, track, service and footway are
# not streets and were polluting both the labelling universe and the neighbour
# lists (5.0% of cores had no road way at all). Primary and secondary are kept
# in the download although arterials are not analysed: they are still the thing
# a later private street may be named after, and re-downloading to get them back
# costs an Overpass run.
CLASSES = ("residential|unclassified|tertiary|living_street|"
           "secondary|primary|tertiary_link|secondary_link|primary_link")

QUERY = """
[out:json][timeout:%(timeout)d];
area["name"="Ada County"]["admin_level"="6"]->.county;
way(area.county)["highway"~"^(%(classes)s)$"]["name"];
out geom;
"""


def fetch(timeout, endpoints=None):
    body = QUERY % {"timeout": timeout, "classes": CLASSES}
    last = None
    for endpoint in (endpoints or OVERPASS_ENDPOINTS):
        print(f"requesting {endpoint} ...", flush=True)
        req = urllib.request.Request(
            endpoint,
            data=urllib.parse.urlencode({"data": body}).encode(),
            headers={"User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout + 60) as r:
                return json.loads(r.read().decode())
        except Exception as e:                       # noqa: BLE001 - report and try next
            last = e
            print(f"  failed: {str(e)[:120]}", flush=True)
            time.sleep(5)
    raise SystemExit(f"all endpoints failed; last error: {last}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--endpoint", action="append",
                    help="override the configured endpoints, in order")
    a = ap.parse_args()

    d = fetch(a.timeout, a.endpoint)

    # Mirrors lag. kumi.systems once answered with a database 6 weeks older than
    # the file it was about to overwrite, silently reverting the author's own
    # OSM edits. Never write an extract older than the one on disk.
    base = (d.get("osm3s") or {}).get("timestamp_osm_base", "")
    print(f"database timestamp: {base or 'unknown'}")
    old = data_path(OUT)
    if old.exists():
        prev = (json.loads(old.read_text()).get("osm3s") or {}).get(
            "timestamp_osm_base", "")
        print(f"file on disk:       {prev or 'unknown'}")
        if base and prev and base < prev:
            raise SystemExit(f"REFUSING: mirror data ({base}) is older than the "
                             f"file on disk ({prev}). Try another endpoint.")
    els = d.get("elements", [])
    import collections
    kinds = collections.Counter(e.get("tags", {}).get("highway") for e in els)
    withgeom = sum(1 for e in els if e.get("geometry"))
    nodes = sum(len(e.get("geometry", ())) for e in els)
    path = data_path(OUT)
    path.write_text(json.dumps(d))
    print(f"\nwrote {path}")
    print(f"{len(els)} ways, {withgeom} with geometry, {nodes} nodes total")
    print("by class: " + ", ".join(f"{k} {v}" for k, v in kinds.most_common()))
    print(f"{path.stat().st_size / 1e6:.1f} MB")
    if not withgeom:
        sys.exit("no geometry returned - check the query")


if __name__ == "__main__":
    main()
