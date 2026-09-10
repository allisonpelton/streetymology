"""Build the paid, county-wide run as Batch API requests. Sends nothing.

Replaces build_llm_batch.py, which was written for the old task -- judge one
proposed candidate, yes or no -- against neighbour lists from the retired
landuse modules, and had stopped running at all.

This asks the current question instead: choose among the Wikidata candidates, or
answer NONE, INVENTED or PERSONAL. Items are rendered by `streetymology.prompt`,
the same code that renders the 240-item chat prompt, so the paid run cannot
quietly diverge from the version that was checked by hand.

Candidates come from `filter_candidates`, so bare personal names are already
gone and this stage only letters and renders them.

Output is a .jsonl of request payloads and a CSV index mapping every item back to
its place id, which is what a result parser needs to write answers home.

  python -m streetymology.build_batch                 # every place with a candidate
  python -m streetymology.build_batch --limit 200     # a slice, to price it first
  python -m streetymology.build_batch --chunk 25
"""
import argparse
import csv
import json
import pathlib

from streetymology.config import data_path, ARTIFACTS_DIR
from streetymology.prompt import (HEADER, candidate_lines, load_context,
                                  load_merges, render)

MODEL_DEFAULT = "claude-sonnet-4-5"     # feasibility winner; verify exact id at call time
MODEL_ESCALATE = "claude-opus-4-1"      # for low-confidence rows

# Verify against current pricing before trusting any estimate.
# USD per million tokens, (input, output).
PRICES = {
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-opus-4-1": (15.0, 75.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


# 40 items per request is what the feasibility test validated. Bigger chunks are
# untested, and a chunk that overruns max_tokens loses every item in it.
CHUNK_DEFAULT = 40


def build_items(limit=None, only=None, exclude=None):
    """(place id, street, rendered block) for every place worth asking about.

    `only` restricts the run to a list of place ids, which is how a subset gets
    re-asked after a change to the context. `exclude` drops places that already
    have an answer, so a trial run is not paid for a second time when the rest of
    the county goes out.
    """
    ctx, by_core = load_context()
    merges = load_merges()
    cands = json.loads(data_path("candidates.json").read_text())

    items, skipped_no_cands = [], 0
    for pid, rec in sorted(ctx.items()):
        if only is not None and pid not in only:
            continue
        if exclude and pid in exclude:
            continue
        core = pid.split("#")[0]
        lines = candidate_lines(cands.get(core, []))
        if not lines:
            skipped_no_cands += 1
            continue
        n = len(items) + 1
        block, _ = render(n, rec.get("name") or rec["display"], lines,
                          rec, ctx, by_core, merges)
        items.append({"place": pid, "street": rec.get("name"), "n": n,
                      "block": block})
        if limit and len(items) >= limit:
            break
    return items, skipped_no_cands


def chunk_requests(items, model, chunk, max_tokens):
    out = []
    for start in range(0, len(items), chunk):
        group = items[start:start + chunk]
        body = "\n\n".join(g["block"] for g in group)
        prompt = (HEADER.replace("240 items", f"{len(group)} items")
                  .replace("## Items (240)", f"## Items ({len(group)})")
                  + "\n" + body + "\n")
        out.append({
            "custom_id": f"batch-{start // chunk:04d}",
            "params": {"model": model, "max_tokens": max_tokens,
                       "messages": [{"role": "user", "content": prompt}]},
        })
    return out


def estimate(requests, n_items, model, out_tokens_per_item=60, discount=0.5):
    """Rough. 4 chars per token, and Batch API is half price at time of writing."""
    inp = sum(len(r["params"]["messages"][0]["content"]) for r in requests) / 4
    outp = n_items * out_tokens_per_item
    pin, pout = PRICES.get(model, (0.0, 0.0))
    return {"input_tokens": int(inp), "output_tokens": int(outp),
            "usd": round((inp / 1e6 * pin + outp / 1e6 * pout) * discount, 2)}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only", help="JSON file holding a list of place ids")
    ap.add_argument("--exclude", action="append", default=[],
                    metavar="ANSWERS.CSV",
                    help="skip places already answered in this file. Repeatable.")
    ap.add_argument("--model", default=MODEL_DEFAULT)
    ap.add_argument("--chunk", type=int, default=CHUNK_DEFAULT)
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    only = set(json.loads(pathlib.Path(a.only).read_text())) if a.only else None

    exclude = set()
    for f in a.exclude:
        with open(f, newline="") as fh:
            exclude |= {r["place"] for r in csv.DictReader(fh) if r.get("place")}

    items, no_cands = build_items(a.limit, only, exclude)
    reqs = chunk_requests(items, a.model, a.chunk, a.max_tokens)
    cost = estimate(reqs, len(items), a.model)

    out = pathlib.Path(a.out or (ARTIFACTS_DIR / f"batch_{a.model}.jsonl"))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        for r in reqs:
            fh.write(json.dumps(r) + "\n")

    idx = out.with_suffix(".index.csv")
    with idx.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["custom_id", "n", "place", "street"])
        w.writeheader()
        for i, r in enumerate(reqs):
            for g in items[i * a.chunk:(i + 1) * a.chunk]:
                w.writerow({"custom_id": r["custom_id"], "n": g["n"],
                            "place": g["place"], "street": g["street"]})

    if exclude:
        print(f"already answered, skipped : {len(exclude)}")
    print(f"places asked about : {len(items)}")
    print(f"skipped, no candidate left : {no_cands}")
    print(f"requests           : {len(reqs)} of up to {a.chunk} items")
    print(f"model              : {a.model}")
    print(f"estimated tokens   : {cost['input_tokens']:,} in, "
          f"{cost['output_tokens']:,} out")
    print(f"estimated cost     : ${cost['usd']} at batch pricing")
    print("\nNOTHING WAS SENT. To send, enable billing and run python -m streetymology.run_batch")
    print(f"wrote {out}\nwrote {idx}")


if __name__ == "__main__":
    main()
