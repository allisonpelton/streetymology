"""Theme context for every place, under AP's causal model of street naming.

Her rule, and the reason each bucket exists: a street's theme comes from the
subdivision that platted it, or from a street it is ATTACHED to, or from a
street it is merely near that belongs to no subdivision at all. Everything else
within some radius is noise, and the old 200 m union of it is what let the model
read a British theme off streets in another plat.

Buckets, in the order the prompt should trust them:

  peers     places sharing the naming plat, matched on `base_name` so
            "SUTTERS MILL SUB NO 01" and "NO 02" are one act, not two;
  attached  places sharing an OSM node, i.e. a real intersection. Exact, from
            way node ids, which the old distance index discarded;
  unplatted places within NEAR_M that fall in no plat, which is the only case
            where proximity alone is evidence.

The naming plat is the EARLIEST RecordedDate covering the place, not the largest
polygon. Membership share travels with it: AP's constraint is that the prompt may
not assert membership at full confidence, because a street can run the boundary
of the plat that named it.
"""
import argparse, collections, json

from shapely.geometry import LineString

from streetymology import places as P
from streetymology.config import data_path
from streetymology.plats import PlatIndex, pretty
from streetymology.normalize import key

WAYS = "osm_ways_geom.json"
PLATS = "street_plats.json"
OUT = "place_context.json"
NEAR_M = 200.0
# A plat only NAMED a street if it materially contains it. Measured on this
# data: in 22.1% of analysed places the earliest plat is not the largest, and
# where it loses it holds a median 0.14 of the street -- a clipped corner of an
# 1900s acreage filing that was re-platted decades later. Above this share the
# earliest plat is taken as the naming act; below it, nothing old enough
# materially contains the street and the largest share wins.
# The naming plat is the OLDEST plat holding at least RUN_MIN_M of UNBROKEN
# street. Three earlier attempts failed for reasons worth keeping:
#   - share of the whole street: a street can cross three plats and be named by
#     the one holding a third of it;
#   - share of a WAY: OSM way splits are arbitrary, so this measured mapping
#     accidents, and a 0.9 threshold demanded a whole way inside one plat;
#   - earliest date alone: pre-1950 acreage plats own the dirt, not the name.
# Metres of unbroken run survive all three problems. A plat that laid out a
# street contains a long continuous piece of it; a plat that merely clips a
# corner holds a few metres.
RUN_MIN_M = 60.0
# ... and at least this fraction of the LONGEST run any plat holds. An absolute
# floor alone let an old plat clipping one block outvote the plat that built the
# street: Avimor Drive went to Mcafee (2007, 93 m) over Avimor (2008, 831 m).
# Age only decides between plats that both plausibly laid the street out.
RUN_RATIO = 0.5
# A street can leave a plat and come straight back: the boundary detours around
# a park parcel or a phase line. Pieces whose ends are this close count as one
# run, so a re-entry does not halve the evidence.
BRIDGE_M = 60.0
# ... and the plat must hold at least this much of the whole street. Measured by
# length band: streets under 300 m sit almost wholly inside their plat (median
# share 1.00, 0.1% below this floor), while streets over 3 km do not (median
# 0.17, 71.7% below it). Those long ones are section-line and rural roads that
# predate the plats along them -- Eisenman, Homer, Horseshoe Bend -- and a plat
# holding 110 m of a 4.6 km road did not name it.
SHARE_MIN = 0.25
# A street can cross many plats without any of them having laid it out: Boise's
# numbered grid streets run through additions filed piecemeal over decades, each
# holding a slice. Union coverage does not catch this -- numbered streets are
# 0.97 platted at the median, like everything else -- so the test is that no
# single plat OWNS the platted length. Named 29th Street after Cruzen's 1906
# addition before this existed.
CROSSING_PLATS = 5
DOMINANCE_MIN = 0.6
# Plats older than this predate themed developer naming. AP: expect trees,
# presidents and family names, and fall back to the name itself and neighbours.
THEMELESS_BEFORE = 1950


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--near", type=float, default=NEAR_M)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--dump", help="print the context of one street and stop")
    ap.add_argument("--dominance-min", type=float, default=None,
                    help="share of the PLATTED length the naming plat must hold "
                         "when the street crosses many plats")
    ap.add_argument("--share-min", type=float, default=None,
                    help="fraction of the whole street the naming plat must hold")
    ap.add_argument("--bridge", type=float, default=None,
                    help="metres of excursion tolerated before a street leaving "
                         "and re-entering a plat counts as two runs")
    ap.add_argument("--run-ratio", type=float, default=None,
                    help="fraction of the longest run a plat must also hold")
    ap.add_argument("--run-min", type=float, default=None,
                    help="metres of unbroken street a plat must hold to count "
                         "as having laid the street out")
    a = ap.parse_args()

    global RUN_MIN_M, RUN_RATIO, BRIDGE_M, SHARE_MIN, DOMINANCE_MIN
    if a.dominance_min is not None:
        DOMINANCE_MIN = a.dominance_min
    if a.share_min is not None:
        SHARE_MIN = a.share_min
    if a.bridge is not None:
        BRIDGE_M = a.bridge
    if a.run_min is not None:
        RUN_MIN_M = a.run_min
    if a.run_ratio is not None:
        RUN_RATIO = a.run_ratio

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
        place_plats[p.id] = sorted(
            ({**v, "inside_m": round(v["inside_m"]), "run_m": round(v["run_m"]),
              "share": round(v["inside_m"] / street_m, 3),
              "street_m": round(street_m)} for v in acc.values()),
            key=lambda v: -v["run_m"])

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
        # Three independent tests, each earning its place from a failure:
        #   run     -- a plat that laid a street out holds an unbroken piece of
        #              it. Capped for short streets: a 54 m cul-de-sac cannot
        #              hold 60 m of anything (Copenhagen Lane abstained).
        #   inside  -- and holds most of what any plat holds. Compared on TOTAL
        #              metres, not on the bridged run: bridging joined Mcafee's
        #              fragments into a 505 m run that beat Avimor's 831 m.
        #   share   -- and holds a real fraction of the street, which is what
        #              rules out rural roads no plat named.
        best_inside = max((x["inside_m"] for x in pls), default=0.0)
        street_m = pls[0]["street_m"] if pls else 0.0
        need_run = min(RUN_MIN_M, 0.8 * street_m)
        laid_out = [x for x in pls if x["run_m"] >= need_run
                    and x["inside_m"] >= RUN_RATIO * best_inside
                    and x["share"] >= SHARE_MIN]
        # Date first, then the longer run: two plats recorded the same year are
        # not ordered by date at all, and Inspirado Drive went to Starpointe
        # (443 m) over Inspirado (602 m) on that coin flip.
        # No fallback to "whatever plat is nearest". A street that merely grazes
        # a boundary -- run 0 m, inside 0 m -- was not laid out by that plat, and
        # naming it anyway invents an etymology. Abstain instead: the plats stay
        # in the record as weak context, but nothing is asserted.
        naming = (min(laid_out, key=lambda x: (x["recorded"] or "9999", -x["run_m"]))
                  if laid_out else None)
        if naming and len(pls) >= CROSSING_PLATS:
            covered = (platted_share.get(p.id) or 0) * street_m
            dominance = naming["inside_m"] / covered if covered > 0 else 0.0
            if dominance < DOMINANCE_MIN:
                naming = None
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
            "plats": pls,
            "naming_plat": naming["name"] if naming else None,
            "naming_recorded": naming["recorded"] if naming else None,
            "naming_share": naming["share"] if naming else None,
            # False means no plat holds RUN_MIN_M of unbroken street: the whole
            # street is short or is cut up, and the longest run was taken.
            "platted_share": platted_share.get(p.id),
            "naming_run_m": naming["run_m"] if naming else None,
            "naming_laid_out": bool(naming and naming["run_m"] >= RUN_MIN_M),
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
            print(f"  plat {pl['name']:30s} {pl['recorded'][:4] if pl['recorded'] else '????'}"
                  f"  run {pl['run_m']:5.0f} m  inside {pl['inside_m']:5.0f} m"
                  f"  of {pl['street_m']:5.0f} m")
        for bucket in ("peers", "same_plat", "attached", "near_unplatted"):
            print(f"  {bucket} ({len(v[bucket])}):")
            for q in v[bucket][:25]:
                print(f"      {out[q]['name']}")
        return

    path = data_path(a.out)
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
    laid = sum(1 for v in an if v.get("naming_laid_out"))
    print(f"  naming plat holds >={RUN_MIN_M:.0f} m of unbroken street: {laid}"
          f"  ({laid/len(an):.1%})")
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


if __name__ == "__main__":
    main()
