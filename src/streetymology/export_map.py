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
import logging
import pathlib

from streetymology.config import data_path, log_to_stderr, ARTIFACTS_DIR
from streetymology.measure_streets import load_places
from streetymology.prompt import load_context
from streetymology.geo import LINK_M, SPLIT_M

log = logging.getLogger(__name__)

WAYS = "osm_ways_geom.json"

# OSM stores 7 decimal places, about a centimetre, on data whose real accuracy
# is metres. Five is about a metre and costs nothing visible. Measured on the
# county extract: 8.25 MB -> 7.57 MB raw, 1.70 MB -> 1.24 MB over the wire.
PRECISION = 5

# What a reader of the map is entitled to know about a street. `reasoning` is
# the model's own sentence, shown as its justification, not as fact.
FIELDS = ("street", "choice", "qid", "label", "confidence", "theme", "reasoning")

# `choice` is the raw answer and for an entity pick it is a candidate LETTER --
# meaningless outside the prompt that produced it, and useless to style on. It
# is kept for fidelity; `category` is the field a map should colour by.
CATEGORIES = ("ENTITY", "PERSONAL", "INVENTED", "NONE", "NOT_ASKED")

# A second way to colour the map, owing nothing to the model being right: when
# the subdivision that named the street was recorded. 95% of places have a year,
# and the buckets are chosen to be roughly comparable in size on Ada County
# rather than to be round numbers. Five, because five is what a line legend can
# carry.
ERAS = ((1940, "pre-1940"), (1970, "1940-1969"), (1990, "1970-1989"),
        (2010, "1990-2009"), (9999, "2010-"))


def era_of(year):
    for cutoff, label in ERAS:
        if year < cutoff:
            return label
    return ""


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
    ctx, _ = load_context()
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
            # Always the place's own name, never the answers CSV's copy. That
            # copy is the label as it stood when the prompt was rendered, and it
            # goes stale the moment naming changes -- which it just did.
            props["street"] = place.name
            # Every feature carries every key. Emitting a key only sometimes
            # makes an expression read null on one feature and "" on another,
            # which is a branch nobody remembers to write.
            props["not_asked_because"] = ""
            if row is None:
                # Two different silences. One means the pipeline found nothing
                # to ask about; the other means the question was never put.
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
            rec = ctx.get(place.id, {})
            # Three views of one answer, because they answer different
            # questions. `subdivision` is the earliest phase clipping this
            # street -- when it was specifically named. `subdivision_merged`
            # is the naming act those phases belong to, which is what asserts
            # a common etymology. `subdivision_recorded` is the assessor's
            # string, kept because the friendly form deliberately does not
            # match the legal description.
            #
            # "" is a finding, not missing data: no plat held enough of the
            # street to claim it. That is the same street the prompt describes
            # as "no subdivision appears to have named this street". It does
            # not distinguish that from a street absent from the plat data
            # altogether -- if the map ever needs to say which, that is a
            # second key, not a second meaning for this one.
            props["subdivision"] = rec.get("naming_phase") or ""
            props["subdivision_merged"] = rec.get("naming_plat") or ""
            props["subdivision_recorded"] = rec.get("naming_phase_recorded") or ""
            # Every subdivision the place falls inside, most metres first. A
            # street can run through several; only one of them named it.
            seen, falls = set(), []
            for pl in sorted(rec.get("plats", ()), key=lambda q: -q["inside_m"]):
                if pl["name"] and pl["name"] not in seen:
                    seen.add(pl["name"])
                    falls.append(pl["name"])
            props["subdivisions"] = falls
            raw = str(rec.get("naming_recorded") or "")[:4]
            props["plat_year"] = int(raw) if raw.isdigit() else ""
            props["plat_era"] = era_of(props["plat_year"]) if raw.isdigit() else ""
            props["category"] = ("NOT_ASKED" if row is None
                                 else "ENTITY" if props["has_entity"]
                                 else props["choice"])
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
        k = f["properties"]["category"]
        mix[k] = mix.get(k, 0) + 1
    unknown = {k for k in mix} - set(CATEGORIES)
    if unknown:
        log.warning("categories not in CATEGORIES: %s — a map styling on them "
                    "would drop these features to a fallback colour", unknown)
    asked = sum(1 for f in feats if f["properties"]["status"] == "answered")
    print(f"answers read     : {len(answers):,}")
    print(f"features written : {len(feats):,}  ({asked:,} answered, "
          f"{len(feats)-asked:,} not asked)")
    if no_geom:
        print(f"answered but no geometry in the extract : {no_geom}")
    print(f"mix              : {sorted(mix.items(), key=lambda kv: -kv[1])}")
    eras = {}
    for f in feats:
        e = f["properties"]["plat_era"] or "(no year)"
        eras[e] = eras.get(e, 0) + 1
    print(f"plat era         : {sorted(eras.items())}")
    named = sum(1 for f in feats if f["properties"]["subdivision"])
    multi = sum(1 for f in feats if len(f["properties"]["subdivisions"]) > 1)
    print(f"subdivision      : {named:,} named, {len(feats)-named:,} none")
    print(f"falls inside >1  : {multi:,}")
    print(f"size             : {out.stat().st_size / 1e6:.1f} MB")
    print(f"wrote {out}")


if __name__ == "__main__":
    log_to_stderr()
    main()
