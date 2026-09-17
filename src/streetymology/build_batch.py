"""Build the paid, county-wide run as Batch API requests. Sends nothing.

Replaces build_llm_batch.py, which was written for the old task of judging one
proposed candidate yes or no, against neighbour lists from the retired
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
import random
import re

from streetymology.config import ARTIFACTS_DIR, data_path
from streetymology.prompt import HEADER, candidate_lines, load_context, render

# AP's three runs over labelled streets were answered by Sonnet 5 in the desktop
# app. The measured agreement and confidence calibration describe this model and
# no other, so changing it invalidates them. /v1/models offers no dated snapshot
# for it, so the moving alias is the only id available.
MODEL_DEFAULT = "claude-sonnet-5"

# Verify against current pricing before trusting any estimate.
# USD per million tokens, (input, output).
PRICES = {
    # Sonnet 5 from the pricing page on 2026-09-10, base input and output only.
    # The cache columns do not apply: nothing here sets cache_control.
    "claude-sonnet-5": (2.0, 10.0),
}


# 40 is not a validated figure. It was picked to fit a fresh chat window; AP has
# run 240 items in one desktop prompt with no degradation down the output, so the
# real ceiling is higher and unmeasured. Chunk size moves input cost by cents --
# the header is 6.1% of input here. The only open question is whether a
# request has a fixed thinking overhead that fewer, larger requests amortise.
CHUNK_DEFAULT = 40

# Measured on the 2026-09-10 trial: 44,501 prompt chars came back as 18,763
# input tokens. The 4.0 rule of thumb this file used undercounts by 1.69x.
CHARS_PER_TOKEN = 2.37

# Sonnet 5 thinks by default, and rejects the explicit `budget_tokens` form that
# earlier models take. It requires adaptive thinking with an effort level. The API
# said so itself after the second trial errored --
#   "thinking.type.enabled is not supported for this model. Use
#    thinking.type.adaptive and output_config.effort"
# and named the levels: low, medium, high, xhigh, max. The desktop runs,
# which is what the labels and the calibration were measured against, were high.
EFFORTS = ("low", "medium", "high", "xhigh", "max")
EFFORT_DEFAULT = "high"

# max_tokens covers thinking and answer together. The first trial set 8,000, the
# model spent all of it reasoning, and no table came back at all. A success by
# the API's reckoning and worthless here. Unspent headroom is never generated and
# never billed, and a batch request has no client-side timeout to hit, so there is
# nothing to trade off. This is well above any plausible need. The model's
# ceiling is 128,000.
MAX_TOKENS_DEFAULT = 64000

# For pricing only; never sent. Adaptive thinking names no budget, so a run
# cannot be bounded in advance. This is measured, not a ceiling.
#
# Per item, not per request: chunk size barely moves it. Six unlabelled draws on
# 2026-09-10 gave 208-250 with sd 15. Labelled places came in near 190, which is
# why this is the unlabelled figure. The county is mostly unlabelled and the
# labelled streets need about 20% less thinking than ordinary ones.
THINKING_PER_ITEM = 231


def build_items(limit=None, only=None, exclude=None, sample=None, seed=0):
    """(place id, street, rendered block) for every place worth asking about.

    `only` restricts the run to a list of place ids, which is how a subset gets
    re-asked after a change to the context. `exclude` drops places that already
    have an answer, so a trial run is not paid for a second time when the rest of
    the county goes out. `sample` takes a reproducible random subset, which is
    how token usage gets measured on inputs that look like the county rather
    than on whichever places happen to sort first.

    Selection happens before rendering, so item numbers always run 1..N and a
    sampled batch is indistinguishable in shape from a whole one.
    """
    ctx, by_core = load_context()
    cands = json.loads(data_path("candidates.json").read_text())

    eligible, skipped_no_cands = [], 0
    for pid, rec in sorted(ctx.items()):
        if only is not None and pid not in only:
            continue
        if exclude and pid in exclude:
            continue
        lines = candidate_lines(cands.get(pid.split("#")[0], []))
        if not lines:
            skipped_no_cands += 1
            continue
        eligible.append((pid, rec, lines))

    if sample and sample < len(eligible):
        chosen = random.Random(seed).sample(eligible, sample)
        eligible = sorted(chosen, key=lambda e: e[0])
    if limit:
        eligible = eligible[:limit]

    items = []
    for n, (pid, rec, lines) in enumerate(eligible, 1):
        block = render(n, rec.get("name") or rec["display"], lines,
                       rec, ctx, by_core)
        items.append({"place": pid, "street": rec.get("name"), "n": n,
                      "block": block})
    return items, skipped_no_cands


def chunk_requests(items, model, chunk, max_tokens, effort=None):
    out = []
    for start in range(0, len(items), chunk):
        group = items[start:start + chunk]
        body = "\n\n".join(g["block"] for g in group)
        prompt = (HEADER.replace("240 items", f"{len(group)} items")
                  .replace("## Items (240)", f"## Items ({len(group)})")
                  + "\n" + body + "\n")
        params = {"model": model, "max_tokens": max_tokens,
                  "messages": [{"role": "user", "content": prompt}]}
        if effort:
            params["thinking"] = {"type": "adaptive"}
            params["output_config"] = {"effort": effort}
        out.append({"custom_id": f"batch-{start // chunk:04d}", "params": params})
    return out


def estimate(requests, n_items, model, out_tokens_per_item=60, discount=0.5,
             thinking_per_item=0):
    """A ceiling, not a forecast. Batch API is half price at time of writing.

    Output assumes every request spends its whole thinking budget. It will not:
    the model stops reasoning when it is done, and unspent budget is never
    generated or billed. Read `usd` as the most this can cost.

    PRICES is keyed by alias, so a dated model id is stripped back to one before
    the lookup. `priced` distinguishes an unpriced model from a free one, since
    a bare $0.00 reads as free rather than as unknown.
    """
    inp = sum(len(r["params"]["messages"][0]["content"])
              for r in requests) / CHARS_PER_TOKEN
    think = thinking_per_item * n_items
    outp = n_items * out_tokens_per_item + think
    base = re.sub(r"-\d{8}$", "", model)
    pin, pout = PRICES.get(base, (0.0, 0.0))
    return {"input_tokens": int(inp), "output_tokens": int(outp),
            "priced": base in PRICES,
            "usd": round((inp / 1e6 * pin + outp / 1e6 * pout) * discount, 2)}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only", help="JSON file holding a list of place ids")
    ap.add_argument("--exclude", action="append", default=[],
                    metavar="ANSWERS.CSV",
                    help="skip places already answered in this file. Repeatable.")
    ap.add_argument("--sample", type=int,
                    help="a random subset of eligible places, for measurement")
    ap.add_argument("--seed", type=int, default=0,
                    help="sample seed. Change it to draw a different subset.")
    ap.add_argument("--model", default=MODEL_DEFAULT)
    ap.add_argument("--chunk", type=int, default=CHUNK_DEFAULT)
    ap.add_argument("--max-tokens", type=int, default=MAX_TOKENS_DEFAULT)
    ap.add_argument("--effort", choices=EFFORTS, default=EFFORT_DEFAULT,
                    help="how hard the model thinks. There is no way to turn it "
                         "off: Sonnet 5 thinks whether or not the parameter is "
                         "sent, as the first trial found out.")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    only = set(json.loads(pathlib.Path(a.only).read_text())) if a.only else None

    exclude = set()
    for f in a.exclude:
        with open(f, newline="") as fh:
            exclude |= {r["place"] for r in csv.DictReader(fh) if r.get("place")}

    items, no_cands = build_items(a.limit, only, exclude, a.sample, a.seed)
    reqs = chunk_requests(items, a.model, a.chunk, a.max_tokens, a.effort)
    cost = estimate(reqs, len(items), a.model,
                    thinking_per_item=THINKING_PER_ITEM)

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
    if a.sample:
        print(f"random sample      : {a.sample} at seed {a.seed}")
    print(f"places asked about : {len(items)}")
    print(f"skipped, no candidate left : {no_cands}")
    print(f"requests           : {len(reqs)} of up to {a.chunk} items")
    print(f"thinking           : {a.effort}, adaptive, "
          f"max_tokens {a.max_tokens:,}")
    print(f"model              : {a.model}")
    print(f"estimated tokens   : {cost['input_tokens']:,} in, "
          f"{cost['output_tokens']:,} out")
    print(f"estimated cost     : ${cost['usd']} at batch pricing, GUESS"
          if cost["priced"] else
          f"estimated cost     : UNKNOWN, no price on file for {a.model}")
    print("\nNOTHING WAS SENT. To send, enable billing and run python -m streetymology.run_batch")
    print(f"wrote {out}\nwrote {idx}")


if __name__ == "__main__":
    main()
