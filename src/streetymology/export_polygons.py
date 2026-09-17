"""Write the subdivision polygons the map draws, in two layers.

They answer different questions and are toggled separately. The merged layer is
one polygon per naming act, and asserts that the streets it named share an
etymology. The phase layer is one polygon per filing, and says when a street was
specifically named.

An amendment is unioned into the plat it amends rather than drawn on its own.
Measured 2026-09-13: 944 of 945 original/amendment pairs are disjoint and 52 of
138 originals carry a hole, so an amendment fills a cutout. Drawn apart the pair
reads as a donut and a patch. `platnames.display_name` strips AMD, so plats sharing a
rendered name are the same filing and group together without a second rule.

Geometry is projected to UTM on the way in, so it has to come back out.

  python -m streetymology.export_polygons
  python -m streetymology.export_polygons --answers data/artifacts/answers_rekeyed.csv
"""
import argparse
import collections
import csv
import json
import pathlib
import re

import pyproj
import shapely
import shapely.ops

from streetymology import config
from streetymology.plats import PlatIndex

_VACATED = re.compile(r"\bVACATED\b|\bRESCINDED\b", re.I)
_TO_WGS = pyproj.Transformer.from_crs("EPSG:32611", "EPSG:4326", always_xy=True)

# Same reasoning as export_map: five decimals is about a metre, on data whose
# real accuracy is metres, and plat polygons are the bulk of the payload.
PRECISION = 5
# Below this a subdivision has not named enough streets to infer a theme.
MIN_THEME_STREETS = 5
# Words the model reaches for that carry no theme.
_NO_THEME = {"", "none", "unclear", "no theme", "n/a", "unknown"}
_STOP = {"names", "name", "theme", "themed", "mixed", "generic", "weak", "related",
         "words", "terms", "compounds", "various", "no", "and", "or", "of", "the",
         "style", "possible", "possibly", "unrelated", "some", "other", "based"}


def _stem(w):
    for suf in ("ies", "ing", "ary", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[:-len(suf)]
    return w


def _theme_words(t):
    return {_stem(w) for w in re.sub(r"[^a-z ]", " ", (t or "").lower()).split()
            if w not in _STOP and len(w) > 2}


def one_theme(themes):
    """The theme these streets share, or "" if they do not share one.

    Free text from the model, so "bird species" and "birds" are one theme and
    only look like two. Themes that share no content word are genuinely
    different, which is Memory Ranch: virtue words for five phases and Texas
    towns after that.
    """
    live = [t for t in themes if t.strip().lower() not in _NO_THEME]
    if len(live) < MIN_THEME_STREETS:
        return ""
    items = [(t, _theme_words(t)) for t in live]
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i][1] & items[j][1]:
                parent[find(i)] = find(j)
    groups = collections.defaultdict(list)
    for i, (t, _) in enumerate(items):
        groups[find(i)].append(t)
    ranked = sorted(groups.values(), key=len, reverse=True)
    if len(ranked) > 1 and len(ranked[1]) >= 3:
        return ""                      # phases disagree; say nothing
    return collections.Counter(ranked[0]).most_common(1)[0][0]


def natural(label):
    """Sort key that puts Phase 2 before Phase 10."""
    return [int(x) if x.isdigit() else x.lower()
            for x in re.split(r"(\d+)", label or "")]


def to_wgs(geom):
    return shapely.ops.transform(_TO_WGS.transform, geom)


def rings(geom):
    def ring(coords):
        return [[round(x, PRECISION), round(y, PRECISION)] for x, y in coords]
    polys = shapely.get_parts(geom)
    return [[ring(p.exterior.coords)] + [ring(i.coords) for i in p.interiors]
            for p in polys if not p.is_empty]


def feature(geom, props):
    rs = rings(geom)
    if not rs:
        return None
    return {"type": "Feature", "properties": props,
            "geometry": ({"type": "Polygon", "coordinates": rs[0]} if len(rs) == 1
                         else {"type": "MultiPolygon", "coordinates": rs})}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--answers", default=str(config.ARTIFACTS_DIR / "answers_rekeyed.csv"))
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args()

    idx = PlatIndex()
    ctx = json.loads(config.data_path("place_context.json").read_text())
    theme_of = {}
    if pathlib.Path(a.answers).exists():
        with open(a.answers, newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("place"):
                    theme_of[row["place"]] = row.get("theme", "")

    # what each family and each phase named
    named_by_family = collections.defaultdict(list)
    named_by_phase = collections.defaultdict(list)
    through_family = collections.defaultdict(set)
    through_phase = collections.defaultdict(set)
    for pid, r in ctx.items():
        namer = r.get("naming_plat")
        if namer:
            named_by_family[namer].append(pid)
            if r.get("naming_phase"):
                named_by_phase[(namer, r["naming_phase"])].append(pid)
        for pl in r.get("plats", ()):
            if pl["name"] and pl["name"] != namer:
                through_family[pl["name"]].add(pid)
            # Both layers answer "which streets run through this" from the same
            # measurement. The phase layer used to re-derive it from a fresh
            # STRtree, where a bare `intersects` counts a street that only
            # touches the boundary: 5,105 more pairs than measure_streets found,
            # and never fewer. A street running along a plat edge is not in it.
            if pl.get("phase"):
                through_phase[pl["phase"]].add(pid)

    # A vacated or rescinded plat is not a subdivision anyone can visit, so it
    # is not drawn. It stays in the naming data: AP confirmed Syringa Park was
    # vacated in 1908 and Syringa Avenue is still on it, so a vacated plat can
    # be why a street is called what it is.
    fams = collections.defaultdict(list)
    drawn = 0
    for p in idx.plats:
        if _VACATED.search(p.name):
            continue
        drawn += 1
        fams[p.family].append(p)
    print(f"plats drawn: {drawn:,} of {len(idx.plats):,} "
          f"({len(idx.plats) - drawn} vacated or rescinded, kept for naming)")

    merged, phases = [], []
    for plats in fams.values():
        label = idx.family_name(min(plats, key=lambda q: str(q.recorded or "9999")))
        geom = shapely.unary_union([p.geom for p in plats])
        # phases: plats rendering to one name are one filing, amendments included
        groups = collections.defaultdict(list)
        for p in plats:
            groups[idx.label(p)].append(p)
        phase_labels = sorted(groups, key=natural)
        ns = named_by_family.get(label, [])
        years = sorted(p.recorded.year for p in plats if p.recorded)
        merged.append(feature(to_wgs(geom), {
            "subdivision": label,
            "phases": phase_labels,
            "phase_count": len(groups),
            "named": sorted(ctx[p]["name"] for p in ns),
            "named_count": len(ns),
            "through": sorted(ctx[p]["name"] for p in through_family.get(label, ())),
            "theme": one_theme([theme_of.get(p, "") for p in ns]),
            "recorded_from": years[0] if years else "",
            "recorded_to": years[-1] if years else "",
        }))
        for full, ps in groups.items():
            short = full[len(label):].lstrip(", ") if full.startswith(label) else full
            pg = shapely.unary_union([q.geom for q in ps])
            pn = named_by_phase.get((label, full), [])
            pyears = sorted(q.recorded.year for q in ps if q.recorded)
            crossing = through_phase.get(full, set())
            phases.append(feature(to_wgs(pg), {
                "subdivision": label,
                "phase": short or full,
                "phase_full": full,
                "recorded": pyears[0] if pyears else "",
                "plats": sorted(q.name for q in ps),
                "named": sorted(ctx[p]["name"] for p in pn),
                "named_count": len(pn),
                "through": sorted(ctx[p]["name"] for p in crossing - set(pn)
                                  if p in ctx),
                "theme": one_theme([theme_of.get(p, "") for p in pn]),
            }))

    out = pathlib.Path(a.out_dir or config.ARTIFACTS_DIR)
    out.mkdir(parents=True, exist_ok=True)
    for name, feats in (("subdivisions", merged), ("subdivision_phases", phases)):
        feats = [f for f in feats if f]
        path = out / f"{name}.geojson"
        config.write_json(path, {"type": "FeatureCollection", "features": feats})
        themed = sum(1 for f in feats if f["properties"]["theme"])
        print(f"{name:20} {len(feats):6,} polygons  {themed:5,} with a theme  "
              f"{path.stat().st_size / 1e6:5.1f} MB")


if __name__ == "__main__":
    config.log_to_stderr()
    main()
