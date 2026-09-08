"""How many streets get no theme context at all, and why.

Neighbour distance is measured centroid-to-centroid using Overpass `out center`,
one point per way. A long way's centroid can sit hundreds of metres from the
street it branches off, so the two are not neighbours at any sane radius. This
counts what that costs before anything is changed.
"""
import argparse, json

from streetymology import neighbours, themes
from streetymology.config import data_path
from streetymology.streets import osm_cores


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--radius", type=float, default=neighbours.RADIUS_M)
    a = ap.parse_args()

    cores = osm_cores()
    assign = themes.load()
    ni = neighbours.NeighbourIndex(radius_m=a.radius)

    no_near, no_sub, no_context, seg_counts = 0, 0, 0, {}
    for k in cores:
        near = ni.near(k)
        sub = (assign.get(k) or {}).get("subdivisions")
        seg_counts[k] = len(ni.segments.get(k, ()))
        if not near:
            no_near += 1
        if not sub:
            no_sub += 1
        if not near and not sub:
            no_context += 1

    n = len(cores)
    print(f"radius {a.radius:.0f} m | {n} cores\n")
    print(f"  no nearby streets        {no_near:5d}  {no_near/n:5.1%}")
    print(f"  no subdivision           {no_sub:5d}  {no_sub/n:5.1%}")
    print(f"  NEITHER, no context      {no_context:5d}  {no_context/n:5.1%}")

    single = [k for k, c in seg_counts.items() if c == 1]
    missing = [k for k, c in seg_counts.items() if c == 0]
    print(f"\n  cores with one way only  {len(single):5d}  {len(single)/n:5.1%}")
    print(f"  cores absent from centers{len(missing):5d}  {len(missing)/n:5.1%}")

    lonely = [k for k in single if not ni.near(k)]
    print(f"  single-way AND no nearby {len(lonely):5d}  {len(lonely)/n:5.1%}"
          f"   <- the long-segment suspects")
    for k in lonely[:12]:
        print(f"      {cores[k]}")


if __name__ == "__main__":
    main()
