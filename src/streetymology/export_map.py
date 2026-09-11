"""Join answers to street geometry and write GeoJSON for the web map.

Nothing else emits a street-to-QID result, which is why this exists.

The geometry is not in `derived/`. `street_measures.json` and
`place_context.json` carry measurements and context, never coordinates, so a
place's ways have to be rebuilt from the raw OSM extract by the same code that
built them in the first place -- `measure_streets.load_places`. That keeps one
definition of what a place is; a second one here would drift.

Coordinates come from the raw extract in lon/lat. `Place.points` is projected to
UTM for measuring and is not what GeoJSON wants.

One Feature per place, geometry MultiLineString, whether or not it has an
answer. A street nobody asked about is still a street on the map, and 918 of
them were never asked because no Wikidata candidate survived filtering -- which
is a fact about the pipeline, not about the street. `status` says which.

  python -m streetymology.export_map data/artifacts/*.answers.csv
  python -m streetymology.export_map <csv> --out site/streets.geojson
  python -m streetymology.export_map <csv> --min-confidence high
"""
import argparse
import csv
import json
import pathlib

from streetymology.config import data_path, ARTIFACTS_DIR
from streetymology.measure_streets import load_places
from streetymology.geo import LINK_M, SPLIT_M

WAYS = "osm_ways_geom.json"

# OSM stores 7 decimal places, about a centimetre, on data whose real accuracy
# is metres. Five is about a metre and costs nothing visible. Measured on the
# county extract: 8.25 MB -> 7.57 MB raw, 1.70 MB -> 1.24 MB over the wire.
PRECISION = 5

# What a reader of the map is entitled to know about a street. `reasoning` is
# the model's own sentence, shown as its justification, not as fact.
FIELDS = ("street", "choice", "qid", "label", "confidence", "theme", "reasoning")


def load_answers(paths):
    """place id -> answer row. Later files win, so a recheck can supersede."""
    out = {}
    for p in paths:
        with open(p, newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("place"):
                    out[r["place"]] = r
    return out


def place_lines(ways_raw):
    """OSM way id -> [[lon, lat], ...], straight from the extract."""
    out = {}
    for e in ways_raw["elements"]:
        g = e.get("geometry")
        if g:
            out[e["id"]] = [[round(pt["lon"], PRECISION), round(pt["lat"], PRECISION)]
                            for pt in g]
    return out


def features(answers):
    ways_raw = json.loads(data_path(WAYS).read_text())
    lines = place_lines(ways_raw)
    built, _ = load_places(ways_raw, LINK_M, SPLIT_M)

    cands = json.loads(data_path("candidates.json").read_text())
    per_core = {c: len(ps) for c, ps in built.items()}
    feats, no_geom = [], 0
    for places in built.values():
        for place in places:
            row = answers.get(place.id)
            coords = [lines[w["id"]] for w in place.ways if w["id"] in lines]
            if not coords:
                no_geom += 1
                continue
            props = {k: (row or {}).get(k, "") for k in FIELDS}
            props["status"] = "answered" if row else "not_asked"
            if row is None:
                # Two different silences. One means the pipeline found nothing
                # to ask about; the other means the question was never put.
                props["street"] = place.name
                props["not_asked_because"] = ("no_wikidata_candidate"
                                              if not cands.get(place.core)
                                              else "not_in_a_run_yet")
            props["place"] = place.id
            # Clicking highlights the place, which already holds every segment
            # of that street in that location. `core` exists for search: 150
            # cores sit in more than one place, and those are duplicates --
            # the same word chosen twice -- so they are listed separately
            # rather than lit up together.
            props["core"] = place.core
            props["places_with_core"] = per_core[place.core]
            # A letter answer resolved to a QID; the three others did not, and
            # the map needs to say which without the reader knowing the codes.
            props["has_entity"] = bool((row or {}).get("qid"))
            feats.append({"type": "Feature",
                          "properties": props,
                          "geometry": {"type": "MultiLineString",
                                       "coordinates": coords}})
    return feats, no_geom


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("answers", nargs="+", help="one or more answers CSVs")
    ap.add_argument("--out", default=None)
    ap.add_argument("--min-confidence", choices=("high", "medium", "low"),
                    help="drop answers below this band")
    a = ap.parse_args()

    answers = load_answers(a.answers)
    if a.min_confidence:
        keep = {"low": {"low", "medium", "high"},
                "medium": {"medium", "high"},
                "high": {"high"}}[a.min_confidence]
        answers = {k: v for k, v in answers.items() if v.get("confidence") in keep}

    feats, no_geom = features(answers)
    out = pathlib.Path(a.out or ARTIFACTS_DIR / "streets.geojson")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    out.chmod(0o664)

    mix = {}
    for f in feats:
        if f["properties"]["status"] != "answered":
            continue
        c = f["properties"]["choice"]
        k = c if c in ("NONE", "INVENTED", "PERSONAL") else "entity"
        mix[k] = mix.get(k, 0) + 1
    asked = sum(1 for f in feats if f["properties"]["status"] == "answered")
    print(f"answers read     : {len(answers):,}")
    print(f"features written : {len(feats):,}  ({asked:,} answered, "
          f"{len(feats)-asked:,} not asked)")
    if no_geom:
        print(f"answered but no geometry in the extract : {no_geom}")
    print(f"mix              : {sorted(mix.items(), key=lambda kv: -kv[1])}")
    print(f"size             : {out.stat().st_size / 1e6:.1f} MB")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
