"""Evidence for judging whether two plat names are phases of one naming act.

`plats.base_name` already folds "SUB NO 01" and "PHASE 02" into one act. It does
not fold a qualifier word: LUGARNO TERRA and LUGARNO TERRA NORTH stay separate,
so East Blakehurst Street sees three peers instead of nine.

Merging them cannot be decided from the string. "Lugarno Terra North" is
obviously the next phase of "Lugarno Terra"; "Castlebury West Business Park" is a
business park beside a housing development and shares nothing but a landowner's
choice of word. So this script only gathers evidence. A person decides, records
the decision in a merge list, and the list is what the pipeline reads.

Evidence gathered per candidate family, and what each is worth:

  distance_m    minimum distance between the two footprints. Phases of one
                development abut or nearly abut. Kilometres apart means the word
                was reused somewhere else in the county.
  year gap      phases follow within a few years. A long gap is a reuse.
  streets       the street names each side named. This is the decisive one: one
                naming act shows one theme carried across the boundary.
  group_gap     distance between assessor GroupNumbers. WEAK. GroupNumber is 85%
                alphabetical, so adjacency mostly restates that the names sort
                together. It only carries information where it breaks
                alphabetical order.
  area          a much smaller partner is often a commercial remnant or a common
                lot, not a phase.

Usage:
  python scripts/plat_phase_report.py                 # every candidate family
  python scripts/plat_phase_report.py --stem LUGARNO  # one, in detail
"""
import argparse
import collections
import datetime
import json

from streetymology.config import data_path
from streetymology.plats import PlatIndex, base_name, pretty


def year(ms):
    if not ms:
        return None
    return datetime.datetime.utcfromtimestamp(ms / 1000).year


DIRECTIONAL = {"NORTH", "SOUTH", "EAST", "WEST", "NORTHEAST", "NORTHWEST",
               "SOUTHEAST", "SOUTHWEST", "N", "S", "E", "W"}


def qualifier_families(bases):
    """Base names where one extends another by DIRECTIONAL WORDS ONLY.

    LUGARNO TERRA -> LUGARNO TERRA NORTH, and nothing else. An unrestricted
    word-prefix rule returns 458 pairs, almost all of them separate
    developments sharing a first word: Crane -> Crane Creek Hollow, Bond ->
    Bond Street Condo. A directional is the one extension that plausibly means
    "the next piece of the same thing", and it is exactly what base_name fails
    to fold.
    """
    by_words = {b: b.split() for b in bases}
    fams = collections.defaultdict(set)
    for short, sw in by_words.items():
        for long, lw in by_words.items():
            if short == long or len(lw) <= len(sw) or lw[:len(sw)] != sw:
                continue
            if all(w in DIRECTIONAL for w in lw[len(sw):]):
                fams[short].add(long)
    return fams


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stem", help="only families whose parent contains this")
    ap.add_argument("--json", help="write the report here as well")
    a = ap.parse_args()

    idx = PlatIndex()
    ctx = json.loads(data_path("place_context.json").read_text())
    # Plat keeps no raw attributes; GroupNumber and area come from the source.
    raw = {f["attributes"]["OBJECTID"]: f["attributes"]
           for f in json.loads(data_path("assessor_subdivisions.json").read_text())["features"]}

    by_base = collections.defaultdict(list)
    for p in idx.plats:
        by_base[p.base].append(p)

    # streets each base name named, from the context the pipeline already built
    named = collections.defaultdict(list)
    for pid, rec in ctx.items():
        if rec.get("naming_plat"):
            named[rec["naming_plat"]].append(rec["display"])

    fams = qualifier_families(set(by_base))
    report = []
    for parent, children in sorted(fams.items()):
        if a.stem and a.stem.upper() not in parent:
            continue
        pp = by_base[parent]
        for child in sorted(children):
            cp = by_base[child]
            dist = min(x.geom.distance(y.geom) for x in pp for y in cp)
            py = [x.year for x in pp]
            cy = [x.year for x in cp]
            pg = [int(str(raw.get(x.oid, {}).get("GroupNumber", "")).strip() or 0) for x in pp]
            cg = [int(str(raw.get(x.oid, {}).get("GroupNumber", "")).strip() or 0) for x in cp]
            pa = sum(x.geom.area for x in pp)
            ca = sum(x.geom.area for x in cp)
            report.append({
                "parent": pretty(parent), "child": pretty(child),
                "parent_raw": parent, "child_raw": child,
                "distance_m": round(dist, 1),
                "parent_years": [y for y in sorted(set(py)) if y],
                "child_years": [y for y in sorted(set(cy)) if y],
                "year_gap": (min(cy) - max(py)) if py and cy and all(py) and all(cy) else None,
                "group_gap": (min(g for g in cg if g) - max(g for g in pg if g)
                              if any(pg) and any(cg) else None),
                "area_ratio": round(ca / pa, 2) if pa else None,
                "parent_streets": sorted(named.get(pretty(parent), [])),
                "child_streets": sorted(named.get(pretty(child), [])),
            })

    for r in report:
        print(f"\n{r['parent']}  ->  {r['child']}")
        print(f"  distance {r['distance_m']} m | years {r['parent_years']} then "
              f"{r['child_years']} (gap {r['year_gap']}) | group gap {r['group_gap']}"
              f" | area x{r['area_ratio']}")
        print(f"  named by parent ({len(r['parent_streets'])}): "
              f"{', '.join(r['parent_streets']) or '(none)'}")
        print(f"  named by child  ({len(r['child_streets'])}): "
              f"{', '.join(r['child_streets']) or '(none)'}")

    print(f"\n{len(report)} candidate pairs")
    if a.json:
        __import__("pathlib").Path(a.json).write_text(json.dumps(report, indent=1))
        print(f"wrote {a.json}")


if __name__ == "__main__":
    main()
