"""Turn the downloaded data into `place_context.json`, in three phases.

Run in order, and the last phase is the one anyone tunes:

  places   chain OSM ways into places -- a street name in ONE location
  plats    score every recorded plat's claim on every street and name the winner
  context  the four buckets of neighbouring streets, with the two confidences

Was three scripts. They only ever ran back to back, each reading the previous
one's file, and the parameters worth experimenting with all live in phase three:
NEAR_M, BRIDGE_M, MATERIAL_RATIO, MIN_PLATTED and the era-weight curve.

  python -m streetymology.build_context             # all three
  python -m streetymology.build_context --phase context
"""
import argparse
import collections
import json
import math

from shapely.geometry import LineString

from streetymology import geo
from streetymology.config import data_path
from streetymology.geo import PlatIndex, base_name, pretty
from streetymology.normalize import key, normalize

# `places` merged into geo; both names kept so the phase bodies read unchanged.
places = P = geo

WAYS = "osm_ways_geom.json"

# ----------------------------------------------------------------------
# Phase 1: places
# ----------------------------------------------------------------------

OUT_PLACES = "street_places.json"


def build_places():
    ap = argparse.ArgumentParser()
    ap.add_argument("--link", type=float, default=places.LINK_M)
    ap.add_argument("--split", type=float, default=places.SPLIT_M)
    ap.add_argument("--out", default=None)
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
    path = data_path(a.out or OUT_PLACES)
    path.write_text(json.dumps(out))
    path.chmod(0o664)
    print(f"-> {path}")

# ----------------------------------------------------------------------
# Phase 2: plat assignment
# ----------------------------------------------------------------------




OUT_PLATS = "street_plats.json"
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


def assign_plats():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
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

    path = data_path(a.out or OUT_PLATS)
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

# ----------------------------------------------------------------------
# Phase 3: context
# ----------------------------------------------------------------------



PLATS = "street_plats.json"
OUT_CONTEXT = "place_context.json"
NEAR_M = 200.0
# A plat only NAMED a street if it materially contains it. Measured on this
# data: in 22.1% of analysed places the earliest plat is not the largest, and
# where it loses it holds a median 0.14 of the street -- a clipped corner of an
# 1900s acreage filing that was re-platted decades later. Above this share the
# earliest plat is taken as the naming act; below it, nothing old enough
# materially contains the street and the largest share wins.
# --- two questions, answered separately -------------------------------------
#
# 1. WAS THIS STREET LAID OUT_CONTEXT BY PLATS AT ALL?  `laid_out` is the fraction of
#    the street lying inside any plat. East Meadow View Road is a farm road at
#    0.15; Retort Avenue is 1.00. This is the confidence, on its own.
#
# 2. WHICH PLAT NAMED IT?  The oldest plat with a material claim -- one holding
#    at least MATERIAL_RATIO of the metres the leading plat holds. Ambiguity
#    here says nothing about question 1: Retort is one of three plats at a third
#    each, and is no less certainly a platted street for that.
#
# The previous version multiplied cover, continuity and dominance together with
# 0.5 floors on two of them. It double-counted -- dominance equals cover
# whenever a street is fully platted -- so Retort was penalised twice for the
# single fact of sharing its street with two neighbours. The floors were the
# least defensible numbers in the tree and are gone with it.
BRIDGE_M = 60.0          # excursion tolerated before a re-entry counts as a break
MATERIAL_RATIO = 0.5     # of the leading plat's metres, to be a candidate
MIN_PLATTED = 0.25       # below this the street is not a platted street

# Age used as a WEIGHT rather than a cutoff. AP's rule: a plat recorded before
# about 1950 is never a source of theme -- the exceptions, trees and presidents,
# are self-evident from the street name and need no subdivision. Such a plat is
# still wanted for membership, which is why this weight scales theme confidence
# and never the choice of plat.
#
# It also does the work six geometric hypotheses could not: Boise's grid streets
# are covered by 1900s additions, so their theme confidence collapses, while
# Retort Avenue's 2007 plat keeps its own.
THEME_ERA_FLOOR = 0.15
THEME_ERA_START = 1915
THEME_ERA_FULL = 1965
THEMELESS_BEFORE = 1950


def era_weight(year):
    """0.15-1.0 by recording year. A weight, not a cutoff."""
    if not year:
        return THEME_ERA_FLOOR
    if year >= THEME_ERA_FULL:
        return 1.0
    if year <= THEME_ERA_START:
        return THEME_ERA_FLOOR
    f = (year - THEME_ERA_START) / (THEME_ERA_FULL - THEME_ERA_START)
    return round(THEME_ERA_FLOOR + f * (1.0 - THEME_ERA_FLOOR), 3)


def build_context():
    ap = argparse.ArgumentParser()
    ap.add_argument("--near", type=float, default=NEAR_M)
    ap.add_argument("--out", default=None)
    ap.add_argument("--dump", help="print the context of one street and stop")
    ap.add_argument("--min-platted", type=float, default=None,
                    help="fraction of a street that must lie in plats at all")
    ap.add_argument("--bridge", type=float, default=None,
                    help="metres of excursion tolerated before a street leaving "
                         "and re-entering a plat counts as two runs")

    a = ap.parse_args()

    global BRIDGE_M, MIN_PLATTED
    if a.bridge is not None:
        BRIDGE_M = a.bridge
    if a.min_platted is not None:
        MIN_PLATTED = a.min_platted

    doc = json.loads((data_path(WAYS)).read_text())
    by_core = collections.defaultdict(list)
    for e in doc["elements"]:
        t = e.get("tags", {})
        k = key(t.get("name") or "")
        if not k or not e.get("geometry"):
            continue
        by_core[k].append({"id": e["id"], "name": t["name"],
                           "highway": t.get("highway"), "nodes": e.get("nodes", []),
                           "points": [(g["lat"], g["lon"]) for g in e["geometry"]]})
    built = P.build(by_core)
    allp = [p for ps in built.values() for p in ps]
    print(f"{len(allp)} places, {sum(1 for p in allp if p.analysed)} analysed")

    wayplats = json.loads((data_path(PLATS)).read_text())

    # --- plats per place, length-weighted over its ways -------------------
    place_plats, place_of_way, node_places = {}, {}, collections.defaultdict(set)
    platted_share = {}
    pi = PlatIndex()
    for p in allp:
        lines = [LineString([(lon, lat) for lat, lon in w["points"]])
                 for w in p.ways if len(w["points"]) > 1]
        for w in p.ways:
            place_of_way[w["id"]] = p.id
            for n in w["nodes"]:
                node_places[n].add(p.id)
        if not lines:
            place_plats[p.id] = []
            continue
        street_m = sum(P.metres(a, b) for w in p.ways
                       for a, b in zip(w["points"], w["points"][1:])) or 1.0
        covered_m, _ = pi.covered_metres(lines)
        platted_share[p.id] = round(covered_m / street_m, 3)
        acc = {}
        for plat, (inside_m, run_m, n_pieces) in pi.runs_inside(
                lines, BRIDGE_M).items():
            # Phases of one plat are one naming act: keep the earliest date and
            # add their runs together, but keep the longest single run as the
            # evidence of laying-out.
            cur = acc.setdefault(plat.base, {
                "base": plat.base, "name": pretty(plat.name),
                "recorded": plat.recorded.isoformat() if plat.recorded else None,
                "inside_m": 0.0, "run_m": 0.0, "pieces": 0})
            cur["inside_m"] += inside_m
            cur["run_m"] = max(cur["run_m"], run_m)
            cur["pieces"] += n_pieces
            rec = plat.recorded.isoformat() if plat.recorded else None
            if rec and (not cur["recorded"] or rec < cur["recorded"]):
                cur["recorded"] = rec
                cur["name"] = pretty(plat.name)
        scored = []
        best_inside = max((v["inside_m"] for v in acc.values()), default=0.0)
        for v in acc.values():
            scored.append({**v, "inside_m": round(v["inside_m"]),
                           "run_m": round(v["run_m"]),
                           "street_m": round(street_m),
                           # of the street, and of the street's PLATTED part
                           "share": round(v["inside_m"] / street_m, 3),
                           "claim": round(v["inside_m"] / covered_m, 3)
                           if covered_m else 0.0,
                           "material": v["inside_m"] >= MATERIAL_RATIO * best_inside,
                           "era_weight": era_weight(int(v["recorded"][:4])
                                                    if v["recorded"] else None)})
        place_plats[p.id] = sorted(scored, key=lambda v: -v["inside_m"])

    # --- membership of a plat, by base name -------------------------------
    members = collections.defaultdict(set)
    for pid, pls in place_plats.items():
        for pl in pls:
            members[pl["base"]].add(pid)

    # --- attachment, from shared nodes ------------------------------------
    attached = collections.defaultdict(set)
    for n, pids in node_places.items():
        if len(pids) < 2:
            continue
        for x in pids:
            attached[x] |= (pids - {x})

    # --- proximity, only used for places in no plat -----------------------
    unplatted = {pid for pid, pls in place_plats.items() if not pls}
    grid = collections.defaultdict(list)
    cell = a.near / 111_320.0
    byid = {p.id: p for p in allp}
    for pid in unplatted:
        for pt in P._thin(byid[pid].points, 40.0):
            grid[(int(pt[0] / cell), int(pt[1] / cell))].append((pid, pt))
    near_unplatted = collections.defaultdict(set)
    for p in allp:
        for pt in P._thin(p.points, 40.0):
            gy, gx = int(pt[0] / cell), int(pt[1] / cell)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    for pid2, pt2 in grid.get((gy + dy, gx + dx), ()):
                        if pid2 != p.id and P.metres(pt, pt2) <= a.near:
                            near_unplatted[p.id].add(pid2)

    out = {}
    for p in allp:
        pls = place_plats[p.id]
        laid_out = platted_share.get(p.id) or 0.0
        material = [x for x in pls if x["material"]]
        naming = (min(material, key=lambda x: (x["recorded"] or "9999",
                                               -x["inside_m"]))
                  if material and laid_out >= MIN_PLATTED else None)

        # Two tiers. A place whose naming plat is the same was named by the same
        # act; a place that merely shares a plat may have been named by an
        # earlier or later one. Both are evidence, not equally.
        peers, shared = set(), set()
        for pl in pls:
            shared |= members[pl["base"]]
        shared -= {p.id}
        if naming:
            peers = {q for q in shared
                     if place_plats.get(q) and place_plats[q][0]["base"] == naming["base"]}
        out[p.id] = {
            "core": p.core, "name": p.name, "analysed": p.analysed,
            # What a neighbour list should print. Directional and post-type
            # carry no etymology and cost prompt budget that names need:
            # "West Bayhorse Street" -> "Bayhorse".
            "display": normalize(p.name),
            "plats": pls,
            "naming_plat": naming["name"] if naming else None,
            "naming_recorded": naming["recorded"] if naming else None,
            "naming_share": naming["share"] if naming else None,
            "naming_run_m": naming["run_m"] if naming else None,
            "naming_claim": naming["claim"] if naming else None,
            # Question 1: how sure are we a plat named this street at all.
            "confidence": round(laid_out, 3) if naming else None,
            # Question 1 damped by the plat's era: how much theme it may suggest.
            "theme_confidence": (round(laid_out * naming["era_weight"], 3)
                                 if naming else None),
            # How many plats could plausibly be the one. 1 is unambiguous.
            "contenders": len(material),
            "platted_share": platted_share.get(p.id),
            "naming_themeless_era": bool(
                naming and naming["recorded"]
                and int(naming["recorded"][:4]) < THEMELESS_BEFORE),
            "peers": sorted(peers),
            "same_plat": sorted(shared - peers),
            "attached": sorted(attached.get(p.id, ())),
            "near_unplatted": sorted(near_unplatted.get(p.id, set()) - shared),
        }

    if a.dump:
        pid = next((q.id for q in allp if key(a.dump) == q.core), None)
        if not pid:
            raise SystemExit(f"no place for {a.dump!r}")
        v = out[pid]
        print(f"\n=== {v['name']}  [{pid}]  analysed={v['analysed']}")
        for pl in v["plats"]:
            print(f"  plat {pl['name'][:26]:26s} {pl['recorded'][:4] if pl['recorded'] else '????'}"
                  f"  inside {pl['inside_m']:5.0f} of {pl['street_m']:5.0f} m"
                  f"  claim {pl['claim']:.2f}"
                  f"{'  MATERIAL' if pl['material'] else ''}")
        for bucket in ("peers", "same_plat", "attached", "near_unplatted"):
            print(f"  {bucket} ({len(v[bucket])}):")
            for q in v[bucket][:25]:
                print(f"      {out[q]['name']}")
        return

    path = data_path(a.out or OUT_CONTEXT)
    path.write_text(json.dumps(out))
    path.chmod(0o664)

    an = [v for v in out.values() if v["analysed"]]

    def q(vals):
        vals = sorted(vals)
        return (f"median {vals[len(vals)//2]}, p90 {vals[int(len(vals)*0.9)]}, "
                f"max {vals[-1]}")

    print(f"\nanalysed places {len(an)}")
    print(f"  with a naming plat   {sum(1 for v in an if v['naming_plat']):5d}"
          f"  {sum(1 for v in an if v['naming_plat'])/len(an):5.1%}")
    print(f"  peers, same naming plat {q([len(v['peers']) for v in an])}")
    print(f"  share a plat, not named by it {q([len(v['same_plat']) for v in an])}")
    print(f"  attached             {q([len(v['attached']) for v in an])}")
    print(f"  near unplatted       {q([len(v['near_unplatted']) for v in an])}")
    tot = [len(v["peers"]) + len(v["same_plat"]) + len(v["attached"])
           + len(v["near_unplatted"]) for v in an]
    print(f"  total context        {q(tot)}")
    print(f"  over 22              {sum(1 for t in tot if t > 22)}"
          f"  ({sum(1 for t in tot if t > 22)/len(an):.1%})")
    print(f"  no context at all    {sum(1 for t in tot if t == 0)}"
          f"  ({sum(1 for t in tot if t == 0)/len(an):.1%})")
    conf = sorted(v["confidence"] for v in an if v.get("confidence") is not None)
    if conf:
        print(f"  confidence (street was platted): median {conf[len(conf)//2]:.2f}, "
              f"under 0.5: {sum(1 for x in conf if x < 0.5)/len(conf):.1%}")
    tc = sorted(v["theme_confidence"] for v in an
                if v.get("theme_confidence") is not None)
    if tc:
        print(f"  theme confidence: median {tc[len(tc)//2]:.2f}, "
              f"under 0.25: {sum(1 for x in tc if x < 0.25)/len(tc):.1%}")
    amb = [v for v in an if v.get("contenders", 0) > 1]
    print(f"  more than one plat could be the namer: {len(amb)}"
          f"  ({len(amb)/len(an):.1%})")
    abstain = [v for v in an if v["plats"] and not v["naming_plat"]]
    print(f"  plats cover it but none laid it out: {len(abstain)}"
          f"  ({len(abstain)/len(an):.1%})  <- no naming plat asserted")
    reentry = sum(1 for v in an if v["naming_plat"]
                  and next(p for p in v["plats"] if p["name"] == v["naming_plat"])
                  ["pieces"] > 1)
    print(f"  naming plat entered more than once: {reentry}"
          f"  ({reentry/max(1, len(an) - len(abstain)):.1%})"
          f"  <- bridged at {BRIDGE_M:.0f} m")
    runs = sorted(v["naming_run_m"] for v in an if v.get("naming_run_m") is not None)
    print(f"  that run: median {runs[len(runs)//2]:.0f} m, "
          f"p10 {runs[len(runs)//10]:.0f} m")
    print(f"-> {path}")

PHASES = {"places": build_places, "plats": assign_plats, "context": build_context}


def main():
    ap = argparse.ArgumentParser(description="Build place_context.json.")
    ap.add_argument("--phase", choices=list(PHASES),
                    help="run one phase; default runs all three in order")
    a, rest = ap.parse_known_args()
    import sys
    sys.argv = [sys.argv[0]] + rest
    for name, fn in PHASES.items():
        if a.phase and name != a.phase:
            continue
        print(f"--- {name}")
        fn()


if __name__ == "__main__":
    main()
