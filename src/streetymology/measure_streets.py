"""Measure every street against the recorded plats. Geometry only, no judgement.

This is the expensive half and it changes only when OSM or the assessor data
changes: chaining ways into places, intersecting each place with every plat that
covers it, and finding which places touch or sit near which.

It deliberately decides nothing. Which plat NAMED a street, how confident that
is, and whether two pieces of a run count as one are all questions about naming
rather than geometry, and they live in `build_context`, which reads this file and
runs in about a second. Ten seconds of intersections should not be repeated every
time a threshold moves.

A "place" is one street name in ONE location. OSM splits a street into many ways,
and a core name can occur in unrelated parts of the county, so the ways of a name
that lie together are grouped: neighbours of one Blake are not evidence about a
Blake five kilometres away. 8,382 core names make 8,577 places; 161 names split.

  python -m streetymology.measure_streets
  python -m streetymology.measure_streets --report-dupes
"""
import argparse
import collections
import json

from shapely.geometry import LineString, MultiPoint
from shapely.strtree import STRtree

from streetymology import geo
from streetymology.config import data_path
from streetymology.geo import PlatIndex, pretty, to_utm
from streetymology.normalize import key, normalize

WAYS = "osm_ways_geom.json"
OUT = "street_measures.json"
NEAR_M = 200.0          # a street in no plat is context for one this close


def projected(geometry):
    """OSM lat/lon nodes -> [(x, y)] in metres. Everything downstream is metres."""
    xs, ys = to_utm([g["lon"] for g in geometry], [g["lat"] for g in geometry])
    return list(zip(xs, ys))


def load_places(ways, link_m, split_m):
    by_core = collections.defaultdict(list)
    for e in ways["elements"]:
        tags = e.get("tags", {})
        k = key(tags.get("name") or "")
        if not k or not e.get("geometry"):
            continue
        by_core[k].append({"id": e["id"], "name": tags["name"],
                           "highway": tags.get("highway"),
                           "nodes": e.get("nodes", []),
                           "points": projected(e["geometry"])})
    built = geo.build(by_core, link_m, split_m)
    return built, [p for ps in built.values() for p in ps]


def plats_for(place, index):
    """(street metres, metres in any plat, per-plat measurements).

    Phases of one plat are one naming act, so they are accumulated by base name:
    metres add up, pieces are concatenated, and the earliest date wins.
    """
    lines = [LineString(w["points"]) for w in place.ways if len(w["points"]) > 1]
    if not lines:
        return 0.0, 0.0, []
    street_m = sum(ln.length for ln in lines)
    covered_m, _ = index.covered_metres(lines)
    acc = {}
    for plat, (inside_m, pieces) in index.pieces_inside(lines).items():
        rec = plat.recorded.isoformat() if plat.recorded else None
        cur = acc.setdefault(plat.base, {
            "base": plat.base, "name": pretty(plat.name), "recorded": rec,
            "inside_m": 0.0, "pieces": []})
        cur["inside_m"] += inside_m
        # Full precision: build_context divides by these, and rounding here
        # moved shares and claims in the third decimal.
        cur["pieces"].extend([m, [round(c, 2) for c in a], [round(c, 2) for c in b]]
                             for m, a, b in pieces)
        if rec and (not cur["recorded"] or rec < cur["recorded"]):
            cur["recorded"] = rec
            cur["name"] = pretty(plat.name)
    return street_m, covered_m, sorted(acc.values(), key=lambda v: -v["inside_m"])


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--link", type=float, default=geo.LINK_M,
                    help="metres within which two ways are one alignment")
    ap.add_argument("--split", type=float, default=geo.SPLIT_M,
                    help="metres beyond which two alignments are separate places")
    ap.add_argument("--near", type=float, default=NEAR_M,
                    help="metres within which an unplatted street is context")
    ap.add_argument("--report-dupes", action="store_true",
                    help="cores occupying more than one place, for eyeballing")
    a = ap.parse_args()

    ways = json.loads(data_path(WAYS).read_text())
    print(f"extract timestamp: {(ways.get('osm3s') or {}).get('timestamp_osm_base')}")
    built, allp = load_places(ways, a.link, a.split)
    print(f"{len(built)} cores, {len(allp)} places, "
          f"{sum(1 for p in allp if p.analysed)} analysed")

    index = PlatIndex()
    print(f"{len(index)} plats")

    out, node_places = {}, collections.defaultdict(set)
    for p in allp:
        street_m, covered_m, plats = plats_for(p, index)
        for w in p.ways:
            for n in w["nodes"]:
                node_places[n].add(p.id)
        out[p.id] = {
            "core": p.core, "name": p.name, "analysed": p.analysed,
            # What a neighbour list should print. Directional and post-type
            # carry no etymology and cost prompt budget that names need:
            # "West Bayhorse Street" -> "Bayhorse".
            "display": normalize(p.name),
            "street_m": street_m, "covered_m": covered_m,
            "plats": plats,
        }

    # Attachment is exact: two places share an OSM node, so they really meet.
    attached = collections.defaultdict(set)
    for pids in node_places.values():
        if len(pids) > 1:
            for x in pids:
                attached[x] |= pids - {x}

    # Proximity is only evidence where no plat explains the street at all.
    # Full geometry rather than a sample: sampling measured vertex to vertex and
    # lost links, for 0.2 s of 11.
    pts = {p.id: MultiPoint(p.points) for p in allp}
    unplatted = [pid for pid, v in out.items() if not v["plats"]]
    tree = STRtree([pts[pid] for pid in unplatted])
    for p in allp:
        near = {unplatted[i] for i in
                tree.query(pts[p.id], predicate="dwithin", distance=a.near)}
        out[p.id]["attached"] = sorted(attached.get(p.id, ()))
        out[p.id]["near_unplatted"] = sorted(near - {p.id})

    path = data_path(OUT)
    path.write_text(json.dumps(out))
    path.chmod(0o664)

    covered = sum(1 for v in out.values() if v["plats"])
    print(f"  places touching a plat  {covered} ({covered / len(out):.1%})")
    print(f"  places with an attachment {sum(1 for v in out.values() if v['attached'])}")
    print(f"-> {path}")

    if a.report_dupes:
        report_dupes(built)


# REPORTING ONLY. Nothing downstream reads this; it exists to be read by AP and
# is safe to delete if it stops earning its keep.
def report_dupes(built):
    """Every core name used in more than one place, closest pair first.

    Closest first because a small separation is the suspicious end: two runs a
    few hundred metres apart are more likely one street the joining rules missed
    than two developers choosing the same word. A pair kilometres apart is
    almost certainly a real duplicate.
    """
    rows = []
    for core, ps in built.items():
        if len(ps) < 2:
            continue
        pts = [MultiPoint(p.points) for p in ps]
        sep = min(pts[i].distance(pts[j])
                  for i in range(len(ps)) for j in range(i + 1, len(ps)))
        rows.append((sep, core, ps))
    rows.sort()
    print(f"\n{len(rows)} core names used in more than one place, closest first")
    print(f"{'separation':>11}  {'places':>6}  core")
    for sep, core, ps in rows:
        names = " | ".join(sorted({p.name for p in ps}))
        art = "" if all(p.analysed for p in ps) else "  (arterial)"
        print(f"{sep/1000:8.2f} km  {len(ps):>6}  {core:22} {names}{art}")


if __name__ == "__main__":
    main()
