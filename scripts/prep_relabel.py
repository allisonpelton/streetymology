"""Prepare a focused re-label pass over 'q' rows that are now answerable.

Three things changed since the first pass:
  1. candidate ranking now prefers nearby features over distant same-named ones
  2. we can show administrative location (P131), which 6 notes explicitly asked for
  3. we can show how many same-named items competed

Rows needing neighbouring-street context are deliberately excluded -- that
feature does not exist yet, so re-asking would waste the author's time.
"""
import csv, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from streetymology.config import DATA_DIR, LABELS_DIR
from streetymology.wikidata import query
from streetymology import gazetteer as g, match
from streetymology.signals import distance_to_ada, proximity, notability

ARTIFACTS = DATA_DIR / "artifacts"
LOC_CACHE = DATA_DIR / "meta_location.json"


def fetch_locations(qids):
    cache = json.loads(LOC_CACHE.read_text()) if LOC_CACHE.exists() else {}
    todo = [q for q in qids if q not in cache]
    for i in range(0, len(todo), 120):
        batch = todo[i:i + 120]
        q = """SELECT ?s ?admLabel ?stLabel WHERE {
          VALUES ?s {%s}
          OPTIONAL { ?s wdt:P131 ?adm }
          OPTIONAL { ?s wdt:P131+ ?st . ?st wdt:P31 wd:Q35657 }
          SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
        }""" % " ".join("wd:" + x for x in batch)
        for r in query(q, timeout=70):
            k = r["s"].rsplit("/", 1)[-1]
            parts = [p for p in (r.get("admLabel"), r.get("stLabel")) if p]
            seen, out = set(), []
            for p in parts:
                if p not in seen:
                    seen.add(p); out.append(p)
            cache[k] = ", ".join(out)
        for x in batch:
            cache.setdefault(x, "")
        LOC_CACHE.write_text(json.dumps(cache))
        time.sleep(1)
    return cache


if __name__ == "__main__":
    coords = json.loads((DATA_DIR / "meta_coords.json").read_text())
    meta = json.loads((DATA_DIR / "meta_candidates.json").read_text())
    idx = match.build_indexes(g.available(), g.index)
    rows = list(csv.DictReader((LABELS_DIR / "pass1_review.csv").open()))

    def rank(c):
        sl = meta.get(c.qid, {}).get("sitelinks", 0)
        return (max(proximity(distance_to_ada(coords.get(c.qid))) or 0.0, notability(sl)), sl)

    targets = []
    for r in rows:
        if r["verdict__y_n_w_q"].strip().lower() != "q":
            continue
        cands = [c for c in match.match(r["street"], idx, fallback_domains=g.FALLBACK_DOMAINS) if c.domain == r["domain"]]
        if not cands:
            continue
        ranked = sorted(cands, key=rank, reverse=True)
        best = ranked[0]
        alts = ranked[1:4]
        changed = best.qid != r["qid"]
        has_loc = coords.get(best.qid) is not None
        dup = int(r["same_name_items_in_domain"]) > 1
        if changed or has_loc or dup:
            targets.append((r, best, changed, len(cands), alts))

    need = {b.qid for _, b, _, _, _ in targets} | {a.qid for _, _, _, _, al in targets for a in al}
    locs = fetch_locations(sorted(need))
    out = LABELS_DIR / "pass2_relabel.csv"
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["street", "domain", "wikidata_label", "qid", "description",
                    "located_in", "sitelinks", "km_from_ada_county",
                    "same_name_items", "next_best_alternatives", "changed_since_first_pass",
                    "your_first_note", "verdict__y_n_w_q", "notes"])
        for r, b, changed, ncand, alts in targets:
            m = meta.get(b.qid, {})
            d = distance_to_ada(coords.get(b.qid))
            w.writerow([r["street"], r["domain"], b.name, b.qid, m.get("description", ""),
                        locs.get(b.qid, ""), m.get("sitelinks", 0),
                        "" if d is None else round(d), ncand,
                        " | ".join(
                            f"{a.name}"
                            + (f" ({locs.get(a.qid)})" if locs.get(a.qid) else "")
                            + (f" [{meta.get(a.qid, {}).get('description','')[:40]}]"
                               if not locs.get(a.qid) else "")
                            for a in alts) or "-",
                        "yes" if changed else "", r["notes"], "", ""])
    print(f"{len(targets)} rows -> {out}")
