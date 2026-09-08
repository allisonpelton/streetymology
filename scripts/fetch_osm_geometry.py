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

QUERY = """
[out:json][timeout:%(timeout)d];
area["name"="Ada County"]["admin_level"="6"]->.county;
way(area.county)["highway"]["name"];
out geom;
"""


def fetch(timeout):
    body = QUERY % {"timeout": timeout}
    last = None
    for endpoint in OVERPASS_ENDPOINTS:
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
    a = ap.parse_args()

    d = fetch(a.timeout)
    els = d.get("elements", [])
    withgeom = sum(1 for e in els if e.get("geometry"))
    nodes = sum(len(e.get("geometry", ())) for e in els)
    path = data_path(OUT)
    path.write_text(json.dumps(d))
    print(f"\nwrote {path}")
    print(f"{len(els)} ways, {withgeom} with geometry, {nodes} nodes total")
    print(f"{path.stat().st_size / 1e6:.1f} MB")
    if not withgeom:
        sys.exit("no geometry returned - check the query")


if __name__ == "__main__":
    main()
