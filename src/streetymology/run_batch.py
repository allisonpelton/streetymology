"""Submit a prepared batch to the Anthropic Batch API and poll for results.

UNTESTED -- written before billing was enabled. Verify against current SDK docs
before trusting it. Refuses to run without ANTHROPIC_API_KEY.

Usage:
  python -m streetymology.run_batch --submit  --model claude-sonnet-4-5
  python -m streetymology.run_batch --poll    <batch_id>
  python -m streetymology.run_batch --fetch   <batch_id>
"""
import argparse, json, sys, time
from streetymology.config import ANTHROPIC_API_KEY, ARTIFACTS_DIR, data_path
from streetymology.build_batch import MODEL_DEFAULT


def client():
    if not ANTHROPIC_API_KEY:
        sys.exit("ANTHROPIC_API_KEY is not set. Add it to .env (never commit it).")
    try:
        import anthropic
    except ImportError:
        sys.exit("pip install anthropic")
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def submit(model):
    path = ARTIFACTS_DIR / f"batch_{model}.jsonl"
    if not path.exists():
        sys.exit(f"{path} missing -- run python -m streetymology.build_batch --model {model}")
    reqs = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    c = client()
    batch = c.messages.batches.create(requests=reqs)
    print(f"submitted {len(reqs)} requests -> batch {batch.id}")
    (data_path("llm_batch_last_id.txt")).write_text(batch.id)
    return batch.id


def poll(batch_id, interval=30):
    c = client()
    while True:
        b = c.messages.batches.retrieve(batch_id)
        print(f"{time.strftime('%H:%M:%S')} {b.processing_status} {b.request_counts}")
        if b.processing_status == "ended":
            return b
        time.sleep(interval)


def fetch(batch_id):
    c = client()
    out = {}
    for res in c.messages.batches.results(batch_id):
        if res.result.type != "succeeded":
            print(f"  {res.custom_id}: {res.result.type}"); continue
        text = "".join(b.text for b in res.result.message.content if b.type == "text")
        out[res.custom_id] = text
    dest = data_path(f"llm_batch_results_{batch_id}.json")
    dest.write_text(json.dumps(out, indent=2))
    print(f"wrote {dest} ({len(out)} responses)")
    return dest


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--poll"); ap.add_argument("--fetch")
    ap.add_argument("--model", default=MODEL_DEFAULT)
    a = ap.parse_args()
    if a.submit:
        bid = submit(a.model); poll(bid); fetch(bid)
    elif a.poll:
        poll(a.poll)
    elif a.fetch:
        fetch(a.fetch)
    else:
        ap.print_help()
