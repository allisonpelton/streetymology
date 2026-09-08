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

from streetymology import places as P
from streetymology.config import data_path
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
# AP's rule: the naming plat is the OLDEST plat that some segment of the street
# falls CLEANLY inside. Share of the whole street is the wrong test -- a street
# can cross three plats and be named by the one holding a third of it -- but a
# way lying almost wholly within a plat was laid out by that plat.
CLEAN_SHARE = 0.9
# Plats older than this predate themed developer naming. AP: expect trees,
# presidents and family names, and fall back to the name itself and neighbours.
THEMELESS_BEFORE = 1950


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--near", type=float, default=NEAR_M)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--dump", help="print the context of one street and stop")
    ap.add_argument("--clean-share", type=float, default=None,
                    help="override how much of a segment must lie inside a plat "
                         "for that plat to count as having laid it out")
    a = ap.parse_args()

    global CLEAN_SHARE
    if a.clean_share is not None:
        CLEAN_SHARE = a.clean_share

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
    place_clean = {}
    for p in allp:
        acc, clean = {}, {}
        # Weight by METRES, not by ways. A place's short cul-de-sac must not
        # outvote its long through street.
        total_m = sum(wayplats.get(str(w["id"]), {}).get("length_m", 0.0)
                      for w in p.ways) or 1.0
        for w in p.ways:
            place_of_way[w["id"]] = p.id
            wlen = wayplats.get(str(w["id"]), {}).get("length_m", 0.0)
            for n in w["nodes"]:
                node_places[n].add(p.id)
            for pl in wayplats.get(str(w["id"]), {}).get("plats", []):
                cur = acc.setdefault(pl["base"], {"base": pl["base"],
                                                  "name": pl["name"],
                                                  "recorded": pl["recorded"],
                                                  "share": 0.0, "n": 0})
                cur["share"] += pl["share"] * wlen
                cur["n"] += 1
                # Phases of one act: the earliest recording is the naming date.
                if pl["share"] >= CLEAN_SHARE:
                    # A segment lying cleanly inside: this plat laid it out.
                    got = clean.get(pl["base"])
                    if not got or (pl["recorded"] or "9999") < got:
                        clean[pl["base"]] = pl["recorded"] or "9999"
                if pl["recorded"] and (not cur["recorded"]
                                       or pl["recorded"] < cur["recorded"]):
                    cur["recorded"] = pl["recorded"]
                    cur["name"] = pl["name"]
        place_clean[p.id] = clean
        place_plats[p.id] = sorted(
            ({**v, "share": round(v["share"] / total_m, 3)} for v in acc.values()),
            key=lambda v: (v["recorded"] or "9999", -v["share"]))

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
        clean = place_clean.get(p.id) or {}
        candidates = [x for x in pls if x["base"] in clean]
        naming = (min(candidates, key=lambda x: x["recorded"] or "9999")
                  if candidates
                  else (max(pls, key=lambda x: x["share"]) if pls else None))
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
            # False means no segment lay cleanly in any plat: the street crosses
            # boundaries throughout and the largest share was taken instead.
            "naming_clean": bool(naming and naming["base"] in (place_clean.get(p.id) or {})),
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
            print(f"  plat {pl['name']:32s} {pl['recorded']} share {pl['share']:.2f}")
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
    shares = [v["naming_share"] for v in an if v["naming_share"] is not None]
    shares.sort()
    print(f"  share of street inside its naming plat: median "
          f"{shares[len(shares)//2]:.2f}, p10 {shares[len(shares)//10]:.2f}, "
          f"under 0.5: {sum(1 for s in shares if s < 0.5)/len(shares):.1%}")
    print(f"-> {path}")


if __name__ == "__main__":
    main()
