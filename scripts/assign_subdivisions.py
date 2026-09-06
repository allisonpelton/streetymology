"""Cache street -> subdivision assignment. Point-in-polygon first, then nearest
within 150m for streets running along a boundary."""
import json, collections
from streetymology.config import data_path
from streetymology.subdivisions import SubdivisionIndex
from streetymology.normalize import key

OUT = data_path("street_subdivisions.json")

if __name__ == "__main__":
    si = SubdivisionIndex()
    ways = [e for e in json.loads((data_path("osm_ways_center.json")).read_text())["elements"]
            if "center" in e and e["tags"].get("highway") != "trunk"]
    core_to_subs = collections.defaultdict(collections.Counter)
    names = {}
    for e in ways:
        k = key(e["tags"]["name"])
        if not k:
            continue
        names.setdefault(k, e["tags"]["name"])
        lat, lon = e["center"]["lat"], e["center"]["lon"]
        subs = si.containing(lat, lon) or si.nearest(lat, lon, 150.0)
        for s in subs:
            core_to_subs[k][s] += 1
    out = {k: {"name": names[k], "subdivisions": dict(v)} for k, v in core_to_subs.items()}
    OUT.write_text(json.dumps(out))
    sizes = collections.Counter()
    sub_members = collections.defaultdict(set)
    for k, v in out.items():
        for s in v["subdivisions"]:
            sub_members[s].add(k)
    for s, mem in sub_members.items():
        sizes[len(mem)] += 1
    print(f"core names assigned: {len(out)}")
    print(f"subdivisions with >=1 street: {len(sub_members)}")
    print(f"median streets per subdivision: "
          f"{sorted(len(m) for m in sub_members.values())[len(sub_members)//2]}")
    print(f"subdivisions with >=5 streets: {sum(1 for m in sub_members.values() if len(m)>=5)}")
    print(f"-> {OUT}")
