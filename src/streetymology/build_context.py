"""Decide which plat named each street, and assemble its neighbour context.

Reads `street_measures.json` and touches no geometry, so every threshold here can
be moved and the result re-read in about a second. `measure_streets` does the ten
seconds of intersections that this depends on, and none of them change when a
threshold does.

Everything below is a judgement about naming rather than a fact about geometry:

  BRIDGE_M        a street that leaves a plat and comes straight back was still
                  laid out by it -- boundaries detour around parks and phase
                  lines. Two pieces closer than this count as one run.
  MIN_PLATTED     below this share inside any plat, the street is not a platted
                  street at all and no plat is credited with naming it.
  MATERIAL_RATIO  a plat holding far less of the street than the leader is not a
                  contender for having named it.
  era curve       an older plat suggests less theme. Pre-war subdivisions named
                  streets after people and places with no theme at all.

  python -m streetymology.build_context
  python -m streetymology.build_context --bridge 0 --dump "West Indus Street"
"""
import argparse
import collections
import json
import math

from streetymology.config import data_path
from streetymology.normalize import key

MEASURES = "street_measures.json"
OUT = "place_context.json"

BRIDGE_M = 60.0          # excursion tolerated before a re-entry counts as a break
# Of the leading plat's metres, to be a contender for having named the street.
# At 0.5 Iron Mountain Ridge held 44 m of West War Eagle Court against Milestone
# Ranch's 92 and missed the bar by two metres, so a 2023 plat named a 2019
# street and the model read a Georgia-town theme off the wrong neighbours.
MATERIAL_RATIO = 0.4
MIN_PLATTED = 0.25       # below this the street is not a platted street

# Theme by era. Naming a subdivision to a theme is a post-war marketing habit, so
# an old plat is weak evidence of a theme even when it certainly laid the street
# out. The curve is a ramp, not a cutoff: a cutoff was tried and rejected.
THEME_ERA_FLOOR = 0.15
THEME_ERA_START = 1915
THEME_ERA_FULL = 1965
THEMELESS_BEFORE = 1950

# Nothing here is ever certain: the assessor's polygons are approximate, OSM's
# geometry is approximate, and "which plat named this" is an inference from
# overlap. A bare 1.00 tells the model the answer is settled when it is not.
CONFIDENCE_CAP = 0.95


def era_weight(year):
    if not year:
        return THEME_ERA_FLOOR
    if year >= THEME_ERA_FULL:
        return 1.0
    if year <= THEME_ERA_START:
        return THEME_ERA_FLOOR
    span = THEME_ERA_FULL - THEME_ERA_START
    return THEME_ERA_FLOOR + (1 - THEME_ERA_FLOOR) * (year - THEME_ERA_START) / span


def longest_run(pieces, bridge_m=0.0):
    """Longest chain of pieces, joining any two whose ends are within bridge_m.

    `pieces` are (length_m, end, end) tuples rather than geometry, so the
    measuring stage can write them to disk and the selecting stage can vary
    bridge_m without touching a polygon again.
    """
    if not pieces:
        return 0.0
    lens = [pc[0] for pc in pieces]
    if bridge_m <= 0 or len(pieces) == 1:
        return max(lens)
    ends = [(tuple(pc[1]), tuple(pc[2])) for pc in pieces]

    def gap(i, j):
        return min(math.dist(a, b) for a in ends[i] for b in ends[j])

    seen, best = set(), 0.0
    for i in range(len(pieces)):
        if i in seen:
            continue
        stack, total = [i], 0.0
        seen.add(i)
        while stack:
            k = stack.pop()
            total += lens[k]
            for j in range(len(pieces)):
                if j not in seen and gap(k, j) <= bridge_m:
                    seen.add(j)
                    stack.append(j)
        best = max(best, total)
    return best


def score_plats(rec, bridge_m, material_ratio):
    """Add run length, share, claim, materiality and era weight to each plat."""
    street_m = rec["street_m"] or 1
    covered_m = rec["covered_m"]
    best = max((p["inside_m"] for p in rec["plats"]), default=0.0)
    out = []
    for p in rec["plats"]:
        out.append({
            "base": p["base"], "name": p["name"], "recorded": p["recorded"],
            "inside_m": round(p["inside_m"]), "street_m": round(street_m),
            "run_m": round(longest_run(p["pieces"], bridge_m)),
            "pieces": len(p["pieces"]),
            # of the street, and of the street's PLATTED part
            "share": round(p["inside_m"] / street_m, 3),
            "claim": round(p["inside_m"] / covered_m, 3) if covered_m else 0.0,
            "material": p["inside_m"] >= material_ratio * best,
            "era_weight": era_weight(int(p["recorded"][:4]) if p["recorded"] else None),
        })
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bridge", type=float, default=BRIDGE_M)
    ap.add_argument("--min-platted", type=float, default=MIN_PLATTED)
    ap.add_argument("--material-ratio", type=float, default=MATERIAL_RATIO)
    ap.add_argument("--dump", help="print the context of one street and stop")
    a = ap.parse_args()

    measures = json.loads(data_path(MEASURES).read_text())
    scored = {pid: score_plats(rec, a.bridge, a.material_ratio)
              for pid, rec in measures.items()}

    # Which places a plat touches, by base name, so peers can be found.
    members = collections.defaultdict(set)
    for pid, pls in scored.items():
        for p in pls:
            members[p["base"]].add(pid)

    def platted_share(rec):
        return (rec["covered_m"] / rec["street_m"]) if rec["street_m"] else 0.0

    def naming_plat(pid):
        """The earliest plat with a material claim, if any plat named this at all.

        Earliest, because the plat that laid a street out named it and later ones
        inherited it. But not across the war: a pre-1950 plat subdivided land,
        while naming streets to a theme is a post-war habit. Without that guard
        North Patricia Lane leaves Randall Acres (1953, among Claudia, Edna and
        Henry) for Meadow Place (1906).

        The guard only applies where the modern plat holds at least as much of
        the street. A townsite really did name its own grid: South 8th Street is
        23% inside Boise City Original Townsite of 1867 and 12% inside a 1986
        subdivision, and North Center Street is 55% inside the Townsite of Star.
        Where the old plat holds more, it keeps its claim.
        """
        material = [p for p in scored[pid] if p["material"]]
        if not material or platted_share(measures[pid]) < a.min_platted:
            return None
        old = [p for p in material
               if p["recorded"] and int(p["recorded"][:4]) < THEMELESS_BEFORE]
        modern = [p for p in material if p not in old]
        if modern and (not old or max(p["inside_m"] for p in modern)
                       >= max(p["inside_m"] for p in old)):
            material = modern
        return min(material, key=lambda p: (p["recorded"] or "9999", -p["inside_m"]))

    # Settle every naming plat before any peer list is built. Peers are places
    # named by the SAME act, so the test has to be against the other place's
    # naming plat -- not against its largest, which differs on 9% of places and
    # silently dropped them from each other's peers.
    named = {pid: naming_plat(pid) for pid in measures}

    out = {}
    for pid, rec in measures.items():
        pls = scored[pid]
        laid_out = platted_share(rec)
        material = [p for p in pls if p["material"]]
        naming = named[pid]

        shared = set()
        for p in pls:
            shared |= members[p["base"]]
        shared -= {pid}
        peers = {q for q in shared
                 if named[q] and named[q]["base"] == naming["base"]} \
            if naming else set()

        out[pid] = {
            "core": rec["core"], "name": rec["name"], "analysed": rec["analysed"],
            "display": rec["display"], "plats": pls,
            "naming_plat": naming["name"] if naming else None,
            "naming_recorded": naming["recorded"] if naming else None,
            "naming_share": naming["share"] if naming else None,
            "naming_run_m": naming["run_m"] if naming else None,
            "naming_claim": naming["claim"] if naming else None,
            # How sure we are this subdivision laid the street out: how much of
            # the street is platted at all, times how much of the platted part
            # is THIS plat rather than a rival. West War Eagle Court is fully
            # platted but its namer holds a third of it against another plat's
            # two thirds, and reporting that as 1.00 is what let the model take
            # a theme off the wrong neighbours with medium confidence.
            "confidence": (round(min(CONFIDENCE_CAP, laid_out * naming["claim"]), 3)
                           if naming else None),
            # The same, damped by the plat's era: how much theme it may suggest.
            "theme_confidence": (
                round(min(CONFIDENCE_CAP,
                          laid_out * naming["claim"] * naming["era_weight"]), 3)
                if naming else None),
            # How many plats could plausibly be the one. 1 is unambiguous.
            "contenders": len(material),
            "platted_share": round(laid_out, 3),
            "naming_themeless_era": bool(
                naming and naming["recorded"]
                and int(naming["recorded"][:4]) < THEMELESS_BEFORE),
            "peers": sorted(peers),
            "same_plat": sorted(shared - peers),
            "attached": sorted(rec["attached"]),
            "near_unplatted": sorted(set(rec["near_unplatted"]) - shared),
        }

    # REPORTING ONLY. --dump prints one street for AP and stops without writing.
    if a.dump:
        pid = next((q for q, v in out.items() if key(a.dump) == v["core"]), None)
        if not pid:
            raise SystemExit(f"no place for {a.dump!r}")
        v = out[pid]
        print(f"\n=== {v['name']}  [{pid}]  analysed={v['analysed']}")
        for pl in v["plats"]:
            print(f"  plat {pl['name'][:26]:26s} "
                  f"{pl['recorded'][:4] if pl['recorded'] else '????'}"
                  f"  inside {pl['inside_m']:5.0f} of {pl['street_m']:5.0f} m"
                  f"  run {pl['run_m']:5.0f}  claim {pl['claim']:.2f}"
                  f"{'  MATERIAL' if pl['material'] else ''}")
        for bucket in ("peers", "same_plat", "attached", "near_unplatted"):
            print(f"  {bucket} ({len(v[bucket])}):")
            for q in v[bucket][:25]:
                print(f"      {out[q]['name']}")
        return

    path = data_path(OUT)
    path.write_text(json.dumps(out))
    path.chmod(0o664)

    an = [v for v in out.values() if v["analysed"]]

    def q(vals):
        vals = sorted(vals)
        return (f"median {vals[len(vals) // 2]}, p90 {vals[int(len(vals) * 0.9)]}, "
                f"max {vals[-1]}")

    named = sum(1 for v in an if v["naming_plat"])
    print(f"analysed places {len(an)}, with a naming plat {named} ({named/len(an):.1%})")
    for bucket in ("peers", "same_plat", "attached", "near_unplatted"):
        print(f"  {bucket:16} {q([len(v[bucket]) for v in an])}")
    tot = [sum(len(v[b]) for b in
               ("peers", "same_plat", "attached", "near_unplatted")) for v in an]
    print(f"  {'total context':16} {q(tot)}")
    conf = [v["confidence"] for v in an if v["confidence"] is not None]
    print(f"  confidence median {sorted(conf)[len(conf)//2]:.2f}, "
          f"under 0.5 {sum(1 for c in conf if c < 0.5)/len(conf):.1%}")
    amb = sum(1 for v in an if v["contenders"] > 1)
    print(f"  more than one plat could be the namer: {amb} ({amb/len(an):.1%})")
    print(f"-> {path}")


if __name__ == "__main__":
    main()
