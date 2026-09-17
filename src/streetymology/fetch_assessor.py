"""Download Ada County Assessor subdivision polygons.

Replaces OSM `landuse=residential` as the subdivision source. The assessor layer
is the authority: it is the plat record itself, it covers non-residential plats,
and every feature carries `RecordedDate` and `InitialTaxYear`, so the earliest
plat to cover a street can decide which subdivision named it. OSM's polygons
were a proxy for exactly this and were hand-traced from plat scans.

Layer: External/ExternalMap/MapServer/18 ("Subdivisions"), 8,000 features.
`maxRecordCount` is 1000, so features are fetched in OBJECTID batches.

Writes `raw/assessor_subdivisions.json`: one record per feature with attributes
and WGS84 rings. Raw download, no interpretation.
"""
import argparse
import functools
import time

from streetymology.config import data_path, session, write_json

URL = ("http://www.adacountyassessor.org/arcgis/rest/services/External/"
       "ExternalMap/MapServer/18/query")
OUT = "assessor_subdivisions.json"
BATCH = 200


@functools.cache
def _s():
    """One pooled session, built on first use rather than at import."""
    return session()


def get(params):
    """POST because an OBJECTID batch makes a GET query string long enough that
    the server answers 404. Transport and 5xx retries come from the session; an
    error in the body means the request itself was wrong, so it is not retried.
    """
    r = _s().post(URL, data=params, timeout=120)
    r.raise_for_status()
    d = r.json()
    if "error" in d:
        raise RuntimeError(d["error"])
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=BATCH)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    ids = sorted(get({"where": "1=1", "returnIdsOnly": "true", "f": "json"})["objectIds"])
    print(f"{len(ids)} features")

    feats = []
    for i in range(0, len(ids), a.batch):
        chunk = ids[i:i + a.batch]
        d = get({"objectIds": ",".join(map(str, chunk)), "outFields": "*",
                 "outSR": "4326", "returnGeometry": "true", "f": "json"})
        feats.extend(d.get("features", []))
        print(f"  {len(feats):5d}/{len(ids)}")
        time.sleep(0.3)

    path = write_json(data_path(a.out),
                      {"source": URL, "fetched": time.strftime("%Y-%m-%d"),
                       "features": feats})
    print(f"-> {path}  ({path.stat().st_size/1e6:.1f} MB)")

    named = sum(1 for f in feats if (f["attributes"].get("SubdivisionName") or "").strip())
    dated = sum(1 for f in feats if f["attributes"].get("RecordedDate"))
    print(f"named {named}, with RecordedDate {dated}")


if __name__ == "__main__":
    main()
