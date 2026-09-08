"""Assign every OSM street way to the assessor plats it runs through.

Replaces `assign_subdivisions.py`, which took a way's CENTROID and merged
"inside the polygon" with "within 150 m of one" into a single untagged count.
Two consequences AP ruled against: membership could not be distinguished from
adjacency, and a street was credited to whichever polygon had the most members
rather than to the plat that named it.

Here a way is a polyline and membership is the SHARE OF ITS LENGTH inside each
plat, so a street running along a boundary is visibly different from one wholly
inside. Every intersecting plat is kept; nothing is resolved to a single answer
at this stage, because the resolution rule is earliest `RecordedDate` and that
belongs to whatever consumes this file.

Writes `derived/street_plats.json`, keyed by way id, with the core name so a
place-level grouping can be built on top without re-reading the geometry.
"""
import argparse, collections, json

import math

from shapely.geometry import LineString

from streetymology.config import data_path
from streetymology.normalize import key
from streetymology.plats import PlatIndex, pretty

WAYS = "osm_ways_geom.json"
OUT = "street_plats.json"
# Analysed classes. Arterials are excluded: they predate the plats they cross,
# they were not named by developers, and a plat that a highway clips did not
# name it.
ANALYSED = {"residential", "unclassified", "tertiary", "living_street"}


def length_m(pts):
    """Polyline length in metres. Shapely works in degrees here, which are not
    comparable between a north-south and an east-west street."""
    t = 0.0
    for a, b in zip(pts, pts[1:]):
        dy = (b[1] - a[1]) * 111_320.0
        dx = (b[0] - a[0]) * 111_320.0 * math.cos(math.radians(a[1]))
        t += math.hypot(dx, dy)
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--min-share", type=float, default=0.02,
                    help="ignore plats holding less than this share of a way")
    a = ap.parse_args()

    pi = PlatIndex()
    print(f"{len(pi)} plats")

    els = json.loads((data_path(WAYS)).read_text())["elements"]
    out, stats = {}, collections.Counter()
    for e in els:
        tags = e.get("tags", {})
        name = tags.get("name")
        cls = tags.get("highway")
        if not name or not e.get("geometry"):
            continue
        pts = [(g["lon"], g["lat"]) for g in e["geometry"]]
        if len(pts) < 2:
            continue
        line = LineString(pts)
        shares = pi.share_inside(line)
        keep = {p: s for p, s in shares.items() if s >= a.min_share}
        stats["ways"] += 1
        stats["analysed" if cls in ANALYSED else "context_only"] += 1
        if keep:
            stats["with_plat"] += 1
            if cls in ANALYSED:
                stats["analysed_with_plat"] += 1
        out[str(e["id"])] = {
            "name": name, "core": key(name), "highway": cls,
            # Length matters downstream: a place's membership must be weighted
            # by metres, not averaged over ways. Averaging turned a 302 m street
            # 94% inside The Glenn into "0.31 of Chester is in The Glenn".
            "length_m": round(length_m(pts), 1),
            "analysed": cls in ANALYSED,
            "plats": [{"oid": p.oid, "name": pretty(p.name), "raw": p.name,
                       "base": p.base,
                       "recorded": p.recorded.isoformat() if p.recorded else None,
                       "share": round(s, 3)}
                      for p, s in sorted(keep.items(), key=lambda kv: -kv[1])],
        }

    path = data_path(a.out)
    path.write_text(json.dumps(out))
    path.chmod(0o664)

    n, na = stats["ways"], stats["analysed"]
    print(f"{n} named ways, {na} analysed classes, {n - na} context-only (arterial)")
    print(f"  in at least one plat        {stats['with_plat']:6d}"
          f"  {stats['with_plat']/n:6.1%}")
    print(f"  analysed ways in a plat     {stats['analysed_with_plat']:6d}"
          f"  {stats['analysed_with_plat']/na:6.1%}")

    counts = collections.Counter(len(v["plats"]) for v in out.values() if v["analysed"])
    print("\nplats per analysed way: " + ", ".join(
        f"{k}:{counts[k]}" for k in sorted(counts)[:8]))

    top = [max((p["share"] for p in v["plats"]), default=0.0)
           for v in out.values() if v["analysed"]]
    top.sort()
    if top:
        m = len(top)
        print(f"largest share of a way inside one plat: median {top[m//2]:.2f}, "
              f"p10 {top[m//10]:.2f}, share of ways >0.9: "
              f"{sum(1 for t in top if t > 0.9)/m:.1%}")
    print(f"-> {path}")


if __name__ == "__main__":
    main()
