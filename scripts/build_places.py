"""Group street ways into places: one core name in one location.

The analysis unit stops being a NAME and becomes a NAME IN A PLACE. See
`streetymology.places` for the two thresholds and for the Five Mile rule that
makes arterial contamination a property of the whole alignment.

Writes `derived/street_places.json`. Reports how much the change costs and what
it removes from the labelling universe.
"""
import argparse, collections, json

from streetymology import places
from streetymology.config import data_path
from streetymology.normalize import key

WAYS = "osm_ways_geom.json"
OUT = "street_places.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--link", type=float, default=places.LINK_M)
    ap.add_argument("--split", type=float, default=places.SPLIT_M)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--report-dupes", action="store_true",
                    help="cores occupying more than one place, for eyeballing")
    ap.add_argument("--report-merges", action="store_true",
                    help="list places built from alignments that do not touch")
    a = ap.parse_args()

    doc = json.loads((data_path(WAYS)).read_text())
    print(f"extract timestamp: {(doc.get('osm3s') or {}).get('timestamp_osm_base')}")

    by_core = collections.defaultdict(list)
    for e in doc["elements"]:
        t = e.get("tags", {})
        if not t.get("name") or not e.get("geometry"):
            continue
        k = key(t["name"])
        if not k:
            continue
        by_core[k].append({
            "id": e["id"], "name": t["name"], "highway": t.get("highway"),
            "nodes": e.get("nodes", []),
            "points": [(g["lat"], g["lon"]) for g in e["geometry"]],
        })

    print(f"{sum(len(v) for v in by_core.values())} ways, {len(by_core)} cores")
    built = places.build(by_core, a.link, a.split)

    all_places = [p for ps in built.values() for p in ps]
    analysed = [p for p in all_places if p.analysed]
    multi = {k: ps for k, ps in built.items() if len(ps) > 1}
    print(f"\nplaces {len(all_places)} from {len(built)} cores")
    print(f"  cores in >1 place        {len(multi):5d}  {len(multi)/len(built):5.1%}"
          f"   (link {a.link:.0f} m, split {a.split:.0f} m)")
    sizes = collections.Counter(len(ps) for ps in built.values())
    print("  places per core: " + ", ".join(f"{k}:{sizes[k]}" for k in sorted(sizes)))

    print(f"\n  analysed places          {len(analysed):5d}"
          f"  {len(analysed)/len(all_places):5.1%}")
    dropped = [p for p in all_places if not p.analysed]
    print(f"  arterial-contaminated    {len(dropped):5d}"
          f"  {len(dropped)/len(all_places):5.1%}")

    # The Five Mile cases: an alignment that LOOKS residential way-by-way but
    # carries an arterial classification somewhere along its length.
    sneaky = [p for p in dropped
              if p.classes & places.ANALYSED_CLASSES and
              len(p.classes & places.ANALYSED_CLASSES) < len(p.classes)]
    part_res = [p for p in sneaky if "residential" in p.classes]
    print(f"  of those, mixed class    {len(sneaky):5d}"
          f"   ({len(part_res)} include residential ways)"
          f"   <- the Five Mile shape")
    for p in sorted(part_res, key=lambda p: -len(p.ways))[:8]:
        print(f"      {p.name:34s} {len(p.ways):3d} ways  {sorted(p.classes)}")

    cores_analysed = {k for k, ps in built.items() if any(q.analysed for q in ps)}
    print(f"\n  cores keeping >=1 analysed place {len(cores_analysed)}"
          f"  ({len(cores_analysed)/len(built):.1%}); "
          f"{len(built) - len(cores_analysed)} cores leave the universe")

    if a.report_dupes:
        # A core in several places is a name used twice. Numbered streets are
        # excluded: they are known repeats and would swamp the list.
        import re as _re
        num = _re.compile(r"^\d+(st|nd|rd|th)$")
        rows = []
        for k, ps in built.items():
            if len(ps) < 2 or num.match(k.strip()):
                continue
            gaps = []
            for i in range(len(ps)):
                for j in range(i + 1, len(ps)):
                    gaps.append(places._min_dist(ps[i].points, ps[j].points, 0.0))
            rows.append((min(gaps), max(gaps), len(ps), ps[0].name,
                         sum(1 for q in ps if q.analysed)))
        rows.sort()
        print(f"\n{len(rows)} non-numbered core(s) split into separate places\n")
        print(f"{'closest':>8} {'furthest':>9} {'places':>7}  street")
        for lo, hi, n, name, an in rows:
            flag = "" if an == n else f"  ({n - an} arterial)"
            print(f"{lo/1000:8.2f} {hi/1000:9.2f} {n:7d}  {name}{flag}")
        print("\n(distances in km, between the nearest points of two places)")
        return

    if a.report_merges:
        # Places assembled from separate alignments: the road stops, and another
        # road of the same name starts somewhere between link and split. These
        # are AP's ambiguous band -- one naming act, or the same word twice.
        rows = []
        for k, ps in built.items():
            for q in ps:
                aligns = places._components(
                    q.ways, lambda w: places._thin(w["points"]), a.link,
                    places._road_test)
                if len(aligns) < 2:
                    continue
                gaps = []
                for i in range(len(aligns)):
                    for j in range(i + 1, len(aligns)):
                        gaps.append(places._min_dist(aligns[i]["pts"],
                                                     aligns[j]["pts"], 0.0))
                rows.append((max(gaps), q.name, len(aligns)))
        rows.sort(reverse=True)
        print(f"\n{len(rows)} place(s) built from >1 alignment")
        print(f"{'gap m':>8}  {'aligns':>6}  street")
        for gap, nm, na in rows[:40]:
            print(f"{gap:8.0f}  {na:6d}  {nm}")
        return

    out = {p.id: {"core": p.core, "name": p.name, "analysed": p.analysed,
                  "classes": sorted(c for c in p.classes if c),
                  "ways": [w["id"] for w in p.ways],
                  "n_points": len(p.points)}
           for p in all_places}
    path = data_path(a.out)
    path.write_text(json.dumps(out))
    path.chmod(0o664)
    print(f"-> {path}")


if __name__ == "__main__":
    main()
