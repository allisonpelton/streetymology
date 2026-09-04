"""Emit a stratified sample of matches for manual labelling.

Deliberately does NOT include our computed signal scores. Showing them would
anchor the labeller and make the resulting evaluation circular -- the whole
point is to test the signals against a judgement formed independently of them.
"""
import csv, json, random, sys, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from streetymology.config import DATA_DIR
from streetymology import gazetteer as g, match
from streetymology.streets import osm_cores

N = 200
SEED = 20260904
GNIS = {"us_river", "us_lake", "us_mountain"}   # enwiki-only, per author
ARTIFACTS = DATA_DIR / "artifacts"; ARTIFACTS.mkdir(exist_ok=True)


def collect():
    meta = json.loads((DATA_DIR / "meta_candidates.json").read_text())
    cores = osm_cores()
    idx = match.build_indexes(g.available(), g.index)
    rows, seen = [], set()
    for k, orig in cores.items():
        cands = match.match(orig, idx)
        ndom = len({c.domain for c in cands})
        for c in cands:
            if (orig, c.qid, c.domain) in seen:
                continue
            seen.add((orig, c.qid, c.domain))
            m = meta.get(c.qid, {})
            if c.domain in GNIS and not m.get("enwiki"):
                continue                      # author's rule: GNIS needs an article
            rows.append({
                "street": orig, "domain": c.domain, "qid": c.qid,
                "wikidata_label": c.name, "description": m.get("description", ""),
                "via": c.via, "domains_matched": ndom,
                "url": f"https://www.wikidata.org/wiki/{c.qid}",
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
    out = ARTIFACTS / "review_sample.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sample[0].keys()))
        w.writeheader(); w.writerows(sample)
    print(f"\n{len(sample)} rows -> {out}")
