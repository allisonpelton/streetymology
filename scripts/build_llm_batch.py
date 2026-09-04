"""Assemble the LLM judging workload and write Batch API requests to disk.

Sends nothing. Produces a .jsonl ready for the Batch API plus a cost estimate,
so the spend is known before billing is enabled.

Usage:
  python scripts/build_llm_batch.py               # all matched streets
  python scripts/build_llm_batch.py --limit 500   # a slice
  python scripts/build_llm_batch.py --model claude-haiku-4-5
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from streetymology.config import DATA_DIR
from streetymology import gazetteer as g, match, themes, llm
from streetymology.streets import osm_cores
from streetymology.normalize import key

MAX_NEIGHBOURS = 25


def strip_dir(name: str) -> str:
    p = name.split(" ", 1)
    return p[1] if p[0] in ("North", "South", "East", "West") and len(p) > 1 else name


def build_items(limit=None) -> list[llm.Item]:
    assign = themes.load()
    meta = json.loads((DATA_DIR / "meta_candidates.json").read_text())
    locs = json.loads((DATA_DIR / "meta_location.json").read_text()) if (
        DATA_DIR / "meta_location.json").exists() else {}
    idx = match.build_indexes(g.available(), g.index)
    m = {k: {c.domain for c in match.match(v["name"], idx)} for k, v in assign.items()}
    tm = themes.ThemeModel(assign, m)

    items, n = [], 0
    for k, orig in sorted(osm_cores().items()):
        cands = match.match(orig, idx, fallback_domains=g.FALLBACK_DOMAINS)
        if not cands:
            continue                       # nothing proposed; nothing to judge
        best = cands[0]
        subs = tm.subdivisions_of(k, assign)
        sub = max(subs, key=lambda s: len(tm.members.get(s, ())), default="")
        peers = sorted(tm.members.get(sub, set()) - {k}) if sub else []
        names = sorted({strip_dir(assign[p]["name"]) for p in peers})[:MAX_NEIGHBOURS]
        md = meta.get(best.qid, {})
        n += 1
        items.append(llm.Item(n, orig, best.domain, best.qid, best.name,
                              md.get("description", ""), locs.get(best.qid, ""),
                              sub, names))
        if limit and n >= limit:
            break
    return items


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--model", default=llm.MODEL_DEFAULT)
    ap.add_argument("--chunk", type=int, default=40)
    a = ap.parse_args()

    items = build_items(a.limit)
    reqs = llm.build_requests(items, model=a.model, chunk=a.chunk)
    est = llm.estimate_cost(reqs, model=a.model)

    out = DATA_DIR / f"llm_batch_{a.model}.jsonl"
    with out.open("w") as f:
        for r in reqs:
            f.write(json.dumps({k: v for k, v in r.items() if k != "_items"}) + "\n")
    (DATA_DIR / "llm_batch_index.json").write_text(json.dumps(
        {r["custom_id"]: r["_items"] for r in reqs}))

    print(f"items       : {est['items']}")
    print(f"requests    : {est['requests']} (chunk={a.chunk})")
    print(f"input tok   : {est['input_tokens']:,}")
    print(f"output tok  : {est['output_tokens']:,} (estimated)")
    print(f"model       : {est['model']}")
    print(f"COST EST    : ${est['usd_estimate']}  (Batch API 50% discount applied)")
    print(f"\nwrote {out}")
    print("Nothing was sent. Verify pricing in llm.PRICES before trusting this figure.")
