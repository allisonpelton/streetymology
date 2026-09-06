"""Measure gazetteer match rate over Ada County street names. Writes an artifact."""
import json, collections, datetime
from streetymology.config import data_path, ARTIFACTS_DIR
from streetymology import gazetteer, match
from streetymology.normalize import key

ARTIFACTS = ARTIFACTS_DIR; ARTIFACTS.mkdir(exist_ok=True)


def osm_cores():
    els = json.loads((data_path("osm_named_ways.json")).read_text())["elements"]
    cores = {}
    for e in els:
        if e["tags"].get("highway") == "trunk":
            continue
        cores.setdefault(key(e["tags"]["name"]), e["tags"]["name"])
    cores.pop("", None)
    return cores


def run(allow_surname: bool, domains=None):
    cores = osm_cores()
    idx = match.build_indexes(domains or gazetteer.available(), gazetteer.index)
    hits, amb = collections.defaultdict(list), []
    for k, orig in cores.items():
        c = match.match(orig, idx, allow_surname=allow_surname, fallback_domains=gazetteer.FALLBACK_DOMAINS)
        if not c:
            continue
        (amb if match.is_ambiguous(c) else hits[c[0].domain]).append((orig, c[0]))
    total = sum(len(v) for v in hits.values()) + len(amb)
    return cores, hits, amb, total


if __name__ == "__main__":
    high = [d for d in gazetteer.available() if d in gazetteer.HIGH_PRECISION]
    alld = gazetteer.available()
    for label, doms in (("HIGH-PRECISION domains (headline)", high),
                        ("all domains incl. GNIS geography", alld)):
        cores, hits, amb, total = run(True, doms)
        print(f"\n=== {label} ===")
        for d, v in sorted(hits.items(), key=lambda x: -len(x[1])):
            print(f"  {d:14} {len(v):>5}")
        print(f"  {'AMBIGUOUS':14} {len(amb):>5}")
        print(f"  TOTAL {total} / {len(cores)} = {total/len(cores)*100:.1f}%")
    cores, hits, amb, total = run(True, high)
    rows = [{"street": s, "domain": c.domain, "qid": c.qid,
             "wikidata_name": c.name, "via": c.via, "confidence": c.confidence}
            for v in hits.values() for s, c in v]
    art = ARTIFACTS / "gazetteer_matches.json"
    art.write_text(json.dumps({
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "street_count": len(cores), "matched": total, "matches": sorted(rows, key=lambda r: r["street"]),
    }, indent=2))
    print(f"\nartifact -> {art}")
