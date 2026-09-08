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
# --- how likely is each plat to be the one that named the street ------------
#
# Every hard threshold tried here failed on some real street, so plats are
# SCORED and the score is kept in the output. Three signals, each catching a
# failure the others missed:
#
#   cover      metres of street inside the plat over the street's length.
#   continuity longest unbroken run over the metres inside. Pieces whose ends
#              are within BRIDGE_M count as one run: 40% of naming plats are
#              entered more than once, because boundaries detour round parks.
#   dominance  metres inside over the street's PLATTED metres. This is what a
#              grid street fails -- Boise's numbered streets are 0.97 platted,
#              but no single addition owns them.
#
# Age is a preference, not a signal: among plats scoring close to the best, the
# oldest is taken. It cannot override a much better-scoring plat, because
# pre-1950 acreage filings own the dirt and not the name.
BRIDGE_M = 60.0
AGE_BAND = 0.8      # a plat scoring this fraction of the best counts as equal
MIN_SCORE = 0.15    # below this, no plat plausibly laid the street out

# Plats older than this predate themed developer naming: expect trees,
# presidents, surnames. AP adds two cautions about plat NAMES generally, which
# is why the name is membership evidence and not theme evidence:
#   - the recorded name is often a bare given name or surname while the
#     subdivision's sign carries the name people actually use;
#   - name-only plats are common before 1950 and, today, mostly divide farmland
#     where there are no streets and nothing to derive.
THEMELESS_BEFORE = 1950


# Age used as a WEIGHT rather than a cutoff. AP's rule: a plat recorded before
# about 1950 is never a source of theme -- the exceptions, trees and presidents,
# are self-evident from the street name and need no subdivision. Such a plat is
# still wanted for membership, which is why this weight scales the theme
# confidence and never the geometric score or the choice of plat.
#
# It also does the work six geometric hypotheses could not: Boise's grid streets
# are covered by 1900s additions, so their theme confidence collapses, while
# Retort Avenue's 2007 plat keeps its own. Graded, so a 1946 plat is damped
# rather than discarded -- Chester's The Glenn is a correct answer.
THEME_ERA_FLOOR = 0.15      # weight given to the oldest plats
THEME_ERA_START = 1915      # at or below this year, the floor
THEME_ERA_FULL = 1965       # at or above this year, full weight


def era_weight(year):
    """0.15-1.0 by recording year. See the note above; not a cutoff."""
    if not year:
        return THEME_ERA_FLOOR
    if year >= THEME_ERA_FULL:
        return 1.0
    if year <= THEME_ERA_START:
        return THEME_ERA_FLOOR
    f = (year - THEME_ERA_START) / (THEME_ERA_FULL - THEME_ERA_START)
    return round(THEME_ERA_FLOOR + f * (1.0 - THEME_ERA_FLOOR), 3)


def plat_score(inside_m, run_m, street_m, covered_m):
    """0-1 likelihood that this plat laid the street out."""
    if street_m <= 0 or inside_m <= 0:
        return 0.0
    cover = min(1.0, inside_m / street_m)
    continuity = min(1.0, run_m / inside_m)
    dominance = min(1.0, inside_m / covered_m) if covered_m else 0.0
    return cover * (0.5 + 0.5 * continuity) * (0.5 + 0.5 * dominance)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--near", type=float, default=NEAR_M)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--dump", help="print the context of one street and stop")
    ap.add_argument("--min-score", type=float, default=None,
                    help="score below which no plat is named")
    ap.add_argument("--bridge", type=float, default=None,
                    help="metres of excursion tolerated before a street leaving "
                         "and re-entering a plat counts as two runs")

    a = ap.parse_args()

    global BRIDGE_M, MIN_SCORE
    if a.bridge is not None:
        BRIDGE_M = a.bridge
    if a.min_score is not None:
        MIN_SCORE = a.min_score

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
        for v in acc.values():
            scored.append({**v, "inside_m": round(v["inside_m"]),
                           "run_m": round(v["run_m"]),
                           "share": round(v["inside_m"] / street_m, 3),
                           "street_m": round(street_m),
                           "score": round(plat_score(v["inside_m"], v["run_m"],
                                                     street_m, covered_m), 3)})
        tot_score = sum(x["score"] for x in scored) or 1.0
        for x in scored:
            x["confidence"] = round(x["score"] / tot_score, 3)
            x["era_weight"] = era_weight(int(x["recorded"][:4])
                                         if x["recorded"] else None)
            # How much this plat should be allowed to suggest a THEME, as
            # opposed to membership: geometric confidence damped by age.
            x["theme_confidence"] = round(x["confidence"] * x["era_weight"], 3)
        place_plats[p.id] = sorted(scored, key=lambda v: -v["score"])

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
        best = pls[0]["score"] if pls else 0.0
        contenders = [x for x in pls if x["score"] >= AGE_BAND * best]
        naming = (min(contenders, key=lambda x: (x["recorded"] or "9999", -x["score"]))
                  if best >= MIN_SCORE else None)

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
            "naming_run_m": naming["run_m"] if naming else None,
            "naming_score": naming["score"] if naming else None,
            "naming_confidence": naming["confidence"] if naming else None,
            "naming_theme_confidence": (naming["theme_confidence"]
                                        if naming else None),
            # How far clear the winner is. Small means the choice is contested.
            "margin": (round(pls[0]["score"] - pls[1]["score"], 3)
                       if len(pls) > 1 else None),
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
                  f"  score {pl['score']:.2f} conf {pl['confidence']:.2f}"
                  f"  run {pl['run_m']:5.0f} inside {pl['inside_m']:5.0f}"
                  f" of {pl['street_m']:5.0f} m")
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
    sc = sorted(v["naming_score"] for v in an if v["naming_score"] is not None)
    if sc:
        print(f"  naming plat score: median {sc[len(sc)//2]:.2f}, "
              f"p10 {sc[len(sc)//10]:.2f}")
    tc = sorted(v["naming_theme_confidence"] for v in an
                if v.get("naming_theme_confidence") is not None)
    if tc:
        print(f"  theme confidence: median {tc[len(tc)//2]:.2f}, "
              f"under 0.25: {sum(1 for x in tc if x < 0.25)/len(tc):.1%}")
    close = [v for v in an if v.get("margin") is not None and v["margin"] < 0.05
             and v["naming_plat"]]
    print(f"  contested, top two within 0.05: {len(close)}"
          f"  ({len(close)/len(an):.1%})")
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
