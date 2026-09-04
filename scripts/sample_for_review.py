"""Emit a stratified sample of matches for manual labelling.

Deliberately does NOT include our computed signal scores. Showing them would
anchor the labeller and make the resulting evaluation circular -- the whole
point is to test the signals against a judgement formed independently of them.
"""
import csv, json, random, sys, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from streetymology.config import DATA_DIR, LABELS_DIR
from streetymology import gazetteer as g, match
from streetymology.streets import osm_cores
from streetymology.signals import proximity, distance_to_ada, notability

N = 200
SEED = 20260904
GNIS = {"us_river", "us_lake", "us_mountain"}   # enwiki-only, per author
ARTIFACTS = DATA_DIR / "artifacts"; ARTIFACTS.mkdir(exist_ok=True)


def collect():
    """One row per (street, domain) -- not per QID.

    Same-domain duplicates (four orchid species for one street) are collapsed:
    the labeller judges the CATEGORY, and marks 'w' if the category is right but
    the specific item is wrong. Competing domains are listed inline so no row is
    judged blind to its alternatives.
    """
    meta = json.loads((DATA_DIR / "meta_candidates.json").read_text())
    coords = json.loads((DATA_DIR / "meta_coords.json").read_text())
    cores = osm_cores()
    idx = match.build_indexes(g.available(), g.index)
    rows = []
    for k, orig in cores.items():
        cands = match.match(orig, idx)
        if not cands:
            continue
        eligible = [c for c in cands
                    if not (c.domain in GNIS and not meta.get(c.qid, {}).get("enwiki"))]
        if not eligible:
            continue
        by_domain = collections.defaultdict(list)
        for c in eligible:
            by_domain[c.domain].append(c)
        others = sorted(by_domain)
        for dom, group in by_domain.items():
            # Rank within domain: nearest first where coordinates exist, then
            # best-documented. Picks Idaho's Salmon River over Connecticut's.
            def rank(c):
                # A place is plausible if it is NEARBY or FAMOUS -- not both.
                # Obscure-but-local (Lucky Peak) and distant-but-famous
                # (Denmark, Turnberry) are each valid; obscure-and-distant
                # (Chimney Peak, Alabama) is not. So combine as max, not product.
                sl = meta.get(c.qid, {}).get("sitelinks", 0)
                pr = proximity(distance_to_ada(coords.get(c.qid)))
                return (max(pr or 0.0, notability(sl)), sl)
            best = max(group, key=rank)
            m = meta.get(best.qid, {})
            dist = distance_to_ada(coords.get(best.qid))
            rows.append({
                "street": orig, "domain": dom, "qid": best.qid,
                "wikidata_label": best.name, "description": m.get("description", ""),
                "sitelinks": m.get("sitelinks", 0),
                "km_from_ada_county": "" if dist is None else round(dist),
                "same_name_items_in_domain": len(group),
                "other_domains": ", ".join(d for d in others if d != dom) or "-",
                "via": best.via,
                "url": f"https://www.wikidata.org/wiki/{best.qid}",
                "verdict__y_n_w_q": "",
                "notes": "",
            })
    return rows


def stratify(rows, n, seed=SEED):
    """Allocate proportional to sqrt(size) so small domains stay represented."""
    rng = random.Random(seed)
    by = collections.defaultdict(list)
    for r in rows:
        by[r["domain"]].append(r)
    weights = {d: len(v) ** 0.5 for d, v in by.items()}
    total = sum(weights.values())
    picked = []
    for d, v in by.items():
        take = min(len(v), max(2, round(n * weights[d] / total)))
        picked += rng.sample(v, take)
    rng.shuffle(picked)
    return picked[:n]


if __name__ == "__main__":
    rows = collect()
    print(f"eligible match rows: {len(rows)}")
    by = collections.Counter(r["domain"] for r in rows)
    sample = stratify(rows, N)
    got = collections.Counter(r["domain"] for r in sample)
    print(f"{'domain':18} {'pool':>6} {'sampled':>8}")
    for d, c in by.most_common():
        print(f"  {d:18} {c:>6} {got.get(d,0):>8}")
    out = LABELS_DIR / "pass1_review.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sample[0].keys()))
        w.writeheader(); w.writerows(sample)
    print(f"\n{len(sample)} rows -> {out}")
