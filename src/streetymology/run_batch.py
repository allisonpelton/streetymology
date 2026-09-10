"""Send a built batch to the Batch API, poll it, fetch results, parse answers.

The stage `build_batch` names and does not implement. `build_batch` writes
request payloads and an index; this submits them, waits, downloads the raw
result lines, and turns the markdown tables back into one row per place.

Money is spent here and nowhere else, so sending needs `--yes`. Without it
`submit` prices the file and stops, the same contract `build_batch` has.

A submitted batch outlives this process. The run record in
`artifacts/batch_runs/<batch_id>.json` is written *before* the response is
parsed, so a crash between sending and printing cannot lose the id of a batch
that is already costing money. Every later subcommand works from that record,
and `--id` overrides it.

Uses `requests` through `config.session`, not the `anthropic` SDK: the retry and
backoff behaviour every fetch stage relies on is already there, the Batch API is
four plain HTTP calls, and a paid run is a poor place to debut a dependency that
is not currently installed.

  python -m streetymology.run_batch submit data/artifacts/batch_<model>.jsonl
  python -m streetymology.run_batch submit <file> --yes      # spends money
  python -m streetymology.run_batch status --watch
  python -m streetymology.run_batch fetch
  python -m streetymology.run_batch parse
"""
import argparse
import collections
import csv
import hashlib
import datetime as dt
import json
import pathlib
import re
import sys
import time

from streetymology.config import ANTHROPIC_API_KEY, ARTIFACTS_DIR, data_path
from streetymology.build_batch import estimate, MODEL_DEFAULT
from streetymology.prompt import LETTERS

API = "https://api.anthropic.com/v1/messages/batches"
MODELS_API = "https://api.anthropic.com/v1/models"
API_VERSION = "2023-06-01"

RUNS_DIR = ARTIFACTS_DIR / "batch_runs"
LATEST = RUNS_DIR / "latest.json"

# Written before the POST and removed after the id is safely on disk. Its
# presence means a submit did not confirm, so a batch may exist on the server
# that nothing here knows about. `reconcile` is the only way out.
PENDING = RUNS_DIR / "pending.json"

# A file holding more requests than this will not be sent without raising it.
# The county is 156; anything larger is a mistake until proven otherwise.
MAX_REQUESTS = 200

# Answers the prompt offers besides a candidate letter. Anything else is a
# parse failure, not a new answer class.
NON_LETTER = {"NONE", "INVENTED", "PERSONAL"}

# The prompt offers exactly these three. Sonnet emitted `medium-high` and
# `low-medium` on 8 of 50 rows in the 2026-09-10 review, so off-menu values are
# recorded verbatim and counted rather than coerced into a neighbouring band.
CONFIDENCES = {"high", "medium", "low"}

_ROW = re.compile(r"^\s*\|")


def _headers():
    if not ANTHROPIC_API_KEY:
        sys.exit("ANTHROPIC_API_KEY is unset. It belongs in .env, never in a command.")
    return {"x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": API_VERSION,
            "content-type": "application/json"}


def _session():
    from streetymology.config import session
    return session()


def _post_session():
    """A session that never repeats a POST.

    `config.session` retries POST on 502/503, which is right for Overpass and
    wrong here: a batch can be created and its response lost, and the retry then
    creates a second batch and bills it. An ambiguous submit must fail and be
    reconciled by hand, not resolved by guessing.
    """
    from streetymology.config import session
    s = session(retries=0)
    return s


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _records():
    for f in sorted(RUNS_DIR.glob("*.json")):
        if f.name in {"latest.json", "pending.json"}:
            continue
        try:
            yield json.loads(f.read_text())
        except (ValueError, OSError):
            continue


def _list_batches(s, limit=100):
    """Every batch the account knows about, newest first."""
    r = s.get(API, headers=_headers(), params={"limit": limit},
              timeout=s.request_timeout)
    if r.status_code >= 400:
        sys.exit(f"list failed [{r.status_code}]: {r.text[:500]}")
    return r.json().get("data", [])


def _record(batch_id=None):
    """The run record for `batch_id`, or the most recently submitted one."""
    path = RUNS_DIR / f"{batch_id}.json" if batch_id else LATEST
    if not path.exists():
        sys.exit(f"no run record at {path}. Submit first, or pass --id.")
    return json.loads(path.read_text())


def _write_record(rec):
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / f"{rec['batch_id']}.json").write_text(json.dumps(rec, indent=2))
    LATEST.write_text(json.dumps(rec, indent=2))


def submit(path, yes=False, max_requests=MAX_REQUESTS, again=False):
    """POST the request file. Prices it and stops unless `yes`.

    Three things stand between a mistake and a second charge: an unconfirmed
    previous submit blocks this one, a file already sent is refused by content
    hash, and a file larger than expected is refused. All three run before any
    network call, so tripping one costs nothing.

    A fourth compared the account's batch list before and after the POST. It was
    written against POST retries, which `_post_session` now makes impossible, so
    it could no longer fire for its own reason; it cost two API calls per send
    and would false-positive on any concurrent account activity. `reconcile`
    makes the same comparison on demand, outside the spend path.
    """
    reqs = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not reqs:
        sys.exit(f"{path} holds no requests.")

    model = reqs[0]["params"]["model"]
    index = path.with_suffix(".index.csv")
    n_items = sum(1 for _ in csv.DictReader(index.open())) if index.exists() else 0
    cost = estimate(reqs, n_items or len(reqs), model)
    digest = _digest(path)

    print(f"file      : {path}")
    print(f"sha256    : {digest}")
    print(f"HTTP POSTs: 1")
    print(f"requests  : {len(reqs)}  <- billed model calls")
    print(f"items     : {n_items or 'unknown, no index beside the file'}")
    print(f"model     : {model}")
    print(f"estimated : ${cost['usd']} at batch pricing "
          f"({cost['input_tokens']:,} in, {cost['output_tokens']:,} out)")
    if not cost.get("priced"):
        print(f"            *** no price on file for {model}. The figure above "
              f"is not an estimate, it is a zero. ***")

    if PENDING.exists():
        sys.exit(f"\nREFUSING TO SEND. {PENDING} says an earlier submit never "
                 f"confirmed:\n  {PENDING.read_text()}\n"
                 "A batch may exist on the server. Run `reconcile` first.")

    prior = next((r for r in _records() if r.get("digest") == digest), None)
    if prior and not again:
        sys.exit(f"\nREFUSING TO SEND. This exact file was already submitted as "
                 f"{prior['batch_id']} at {prior['submitted']}.\n"
                 "Its results are already paid for; fetch them instead. "
                 "--again overrides.")

    if len(reqs) > max_requests:
        sys.exit(f"\nREFUSING TO SEND. {len(reqs)} requests is over the "
                 f"{max_requests} ceiling. Raise --max-requests if deliberate.")

    if not yes:
        print("\nNOTHING WAS SENT. Re-run with --yes to spend the estimate above.")
        return None

    s = _post_session()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    PENDING.write_text(json.dumps(
        {"digest": digest, "request_file": str(path), "requests": len(reqs),
         "attempted": dt.datetime.now(dt.timezone.utc).isoformat()}, indent=2))

    r = s.post(API, headers=_headers(), json={"requests": reqs},
               timeout=s.request_timeout)
    if r.status_code >= 400:
        PENDING.unlink(missing_ok=True)
        sys.exit(f"submit failed [{r.status_code}]: {r.text[:500]}")
    batch = r.json()

    rec = {"batch_id": batch["id"], "digest": digest, "model": model,
           "requests": len(reqs), "items": n_items, "estimate_usd": cost["usd"],
           "request_file": str(path), "index_file": str(index),
           "submitted": dt.datetime.now(dt.timezone.utc).isoformat()}
    _write_record(rec)
    PENDING.unlink(missing_ok=True)

    print(f"\nSENT. batch id {batch['id']}")
    print(f"run record {RUNS_DIR / (batch['id'] + '.json')}")

    counts = batch.get("request_counts", {})
    total = sum(v for v in counts.values() if isinstance(v, int))
    if total and total != len(reqs):
        print(f"WARNING: server counted {total} requests, file held {len(reqs)}.")

    return rec


def verify(model=MODEL_DEFAULT):
    """Prove the key and the model id work, without spending anything.

    Both endpoints return no tokens, so neither bills. This is the only free
    exercise of `_headers` and of the batch-list call the duplicate guard in
    `submit` relies on; without it, both are first tried during a paid send.

    The key is never printed, and a failure is diagnosed from the status code
    and the response body, which do not contain it.
    """
    s = _session()
    ok = True

    r = s.get(MODELS_API, headers=_headers(), params={"limit": 100},
              timeout=s.request_timeout)
    if r.status_code == 401:
        sys.exit("key REJECTED (401). The key the program loaded from .env is not "
                 "valid. I have not read .env and cannot tell you what is in it.")
    if r.status_code == 403:
        sys.exit("key FORBIDDEN (403). It authenticated but lacks permission, or "
                 "the workspace has no billing enabled.")
    if r.status_code >= 400:
        sys.exit(f"models call failed [{r.status_code}]: {r.text[:300]}")

    ids = [m["id"] for m in r.json().get("data", [])]
    print(f"key            : accepted ({len(ids)} models visible)")
    if model in ids:
        print(f"model {model} : present")
    else:
        ok = False
        near = [i for i in ids if i.split("-")[1:2] == model.split("-")[1:2]]
        print(f"model {model} : *** NOT IN THE LIST ***")
        print(f"  closest ids : {near or ids[:5]}")
        print("  A wrong id fails every request in the batch. Fix MODEL_DEFAULT "
              "in build_batch before sending.")

    r = s.get(API, headers=_headers(), params={"limit": 1},
              timeout=s.request_timeout)
    if r.status_code >= 400:
        ok = False
        print(f"batch list     : FAILED [{r.status_code}] {r.text[:200]}")
        print("  submit's duplicate check needs this call. Do not send until it works.")
    else:
        n = len(r.json().get("data", []))
        print(f"batch list     : works ({n} existing batch{'es' if n != 1 else ''})")

    print("\nNothing was billed: neither endpoint returns tokens.")
    if not ok:
        sys.exit("verification did not fully pass. Do not send.")
    return ok


def cancel(batch_id):
    """Cancel a batch. Requests that already finished are still billed."""
    s = _post_session()
    r = s.post(f"{API}/{batch_id}/cancel", headers=_headers(),
               timeout=s.request_timeout)
    if r.status_code >= 400:
        sys.exit(f"cancel failed [{r.status_code}]: {r.text[:500]}")
    b = r.json()
    print(f"{batch_id} -> {b.get('processing_status')}")
    print("Requests already completed are billed. Cancelling is not a refund.")
    return b


def reconcile():
    """Compare batches on the account with run records here.

    The case this exists for: submit died between sending and writing the id,
    so money is being spent by a batch nothing local refers to.
    """
    s = _session()
    server = _list_batches(s)
    known = {r["batch_id"]: r for r in _records()}

    print(f"batches on account : {len(server)}")
    print(f"run records here   : {len(known)}")
    if PENDING.exists():
        print(f"\nUNCONFIRMED SUBMIT: {PENDING.read_text()}")

    orphans = [b for b in server if b["id"] not in known]
    for b in server:
        mark = " " if b["id"] in known else "?"
        counts = b.get("request_counts", {})
        print(f"  {mark} {b['id']}  {b.get('processing_status'):<12} "
              f"{b.get('created_at', '')}  {counts}")
    if orphans:
        print("\n'?' means no run record here. If one is an accidental duplicate, "
              "cancel it:")
        for b in orphans:
            print(f"      python -m streetymology.run_batch cancel --id {b['id']}")
    else:
        print("\nno orphans: every batch on the account has a record here.")
        if PENDING.exists():
            print(f"Safe to delete {PENDING} once you agree.")
    return orphans


def status(batch_id=None, watch=False, every=60):
    rec = _record(batch_id)
    s = _session()
    while True:
        r = s.get(f"{API}/{rec['batch_id']}", headers=_headers(),
                  timeout=s.request_timeout)
        if r.status_code >= 400:
            sys.exit(f"status failed [{r.status_code}]: {r.text[:500]}")
        b = r.json()
        counts = b.get("request_counts", {})
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S")
        print(f"[{stamp}] {b.get('processing_status')} " +
              " ".join(f"{k}={v}" for k, v in counts.items()), flush=True)
        if b.get("processing_status") == "ended" or not watch:
            return b
        time.sleep(every)


def fetch(batch_id=None, force=False):
    """Download the raw result lines. Never re-downloads over an existing file."""
    rec = _record(batch_id)
    out = ARTIFACTS_DIR / f"{rec['batch_id']}.results.jsonl"
    if out.exists() and not force:
        print(f"already have {out} ({out.stat().st_size:,} bytes). --force to replace.")
        return out

    b = status(rec["batch_id"])
    if b.get("processing_status") != "ended":
        sys.exit(f"batch is {b.get('processing_status')}, not ended. Nothing to fetch.")

    s = _session()
    url = b.get("results_url") or f"{API}/{rec['batch_id']}/results"
    r = s.get(url, headers=_headers(), timeout=s.request_timeout, stream=True)
    if r.status_code >= 400:
        sys.exit(f"fetch failed [{r.status_code}]: {r.text[:500]}")
    with out.open("wb") as fh:
        for block in r.iter_content(chunk_size=1 << 16):
            fh.write(block)
    out.chmod(0o664)
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")
    return out


def parse_table(text):
    """Rows of the answer table, by item number. Tolerates prose around it.

    Off-menu values are kept as the model wrote them; `parse` counts them.
    """
    out = {}
    for line in text.splitlines():
        if not _ROW.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not cells[0].isdigit():
            continue
        choice = cells[2].strip("`* ")
        upper = choice.upper()
        if upper not in NON_LETTER and not (len(choice) == 1 and upper in LETTERS):
            continue
        out[int(cells[0])] = {
            "street": cells[1],
            "choice": upper,
            "confidence": cells[3].lower() if len(cells) > 3 else "",
            "theme": cells[4] if len(cells) > 4 else "",
            "reasoning": cells[5] if len(cells) > 5 else "",
        }
    return out


def _text(result):
    """The assistant text of one result line, or None if it did not succeed.

    Thinking blocks are dropped: only the table is wanted, and the reasoning is
    billed whether or not anything reads it.
    """
    if result.get("type") != "succeeded":
        return None
    blocks = result.get("message", {}).get("content", [])
    return "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text")


def _letter_qids():
    """core -> {letter: (qid, label)}, rebuilt the way `build_batch` lettered it.

    Letters mean nothing on their own, so an answer is only as good as this
    mapping. `candidate_lines` letters `candidates.json` in file order and
    nothing shuffles it, so re-reading the same file reproduces the rendering.
    Regenerating candidates between build and parse would silently move them.
    """
    cands = json.loads(data_path("candidates.json").read_text())
    return {core: {LETTERS[i]: (c.get("qid"), c.get("label"))
                   for i, c in enumerate(cs[:len(LETTERS)])}
            for core, cs in cands.items()}


def parse(batch_id=None, results=None, index=None, out=None):
    rec = _record(batch_id) if not (results and index) else {}
    results = pathlib.Path(results or ARTIFACTS_DIR / f"{rec['batch_id']}.results.jsonl")
    index = pathlib.Path(index or rec["index_file"])
    if not results.exists():
        sys.exit(f"no results at {results}. Fetch first.")

    want = collections.defaultdict(list)     # custom_id -> rows of the index
    for row in csv.DictReader(index.open()):
        want[row["custom_id"]].append(row)

    letters = _letter_qids()
    answers, missing, errored = [], [], []
    truncated, usage = [], collections.Counter()

    for line in results.read_text().splitlines():
        if not line.strip():
            continue
        rl = json.loads(line)
        cid, result = rl.get("custom_id"), rl.get("result", {})
        text = _text(result)
        if text is None:
            errored.append((cid, result.get("type"),
                            str(result.get("error"))[:200]))
            continue
        msg = result.get("message", {})
        u = msg.get("usage", {})
        usage["input"] += u.get("input_tokens", 0)
        usage["output"] += u.get("output_tokens", 0)
        usage["thinking"] += u.get("output_tokens_details", {}).get("thinking_tokens", 0)
        # A request that hit max_tokens is a success by the API's reckoning: the
        # limit was ours, so honouring it is correct behaviour. Only the caller
        # knows a truncated table is worthless, so say so here.
        if msg.get("stop_reason") == "max_tokens":
            truncated.append((cid, u.get("output_tokens", 0),
                              u.get("output_tokens_details", {}).get("thinking_tokens", 0)))

        table = parse_table(text)
        for row in want.get(cid, []):
            n = int(row["n"])
            got = table.get(n)
            if got is None:
                missing.append((cid, n, row["street"]))
                continue
            core = row["place"].split("#")[0]
            qid = label = ""
            if got["choice"] not in NON_LETTER:
                qid, label = letters.get(core, {}).get(got["choice"], ("", ""))
                if not qid:
                    missing.append((cid, n, f"{row['street']} letter "
                                            f"{got['choice']} has no candidate"))
                    continue
            answers.append({"place": row["place"], "street": row["street"],
                            "n": n, "custom_id": cid, "choice": got["choice"],
                            "qid": qid, "label": label,
                            "confidence": got["confidence"], "theme": got["theme"],
                            "reasoning": got["reasoning"]})

    out = pathlib.Path(out or ARTIFACTS_DIR /
                       f"{results.stem.replace('.results', '')}.answers.csv")
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["place", "street", "n", "custom_id",
                                           "choice", "qid", "label",
                                           "confidence", "theme", "reasoning"])
        w.writeheader()
        for a in sorted(answers, key=lambda a: a["n"]):
            w.writerow(a)
    out.chmod(0o664)

    asked = sum(len(v) for v in want.values())
    mix = collections.Counter(a["choice"] if a["choice"] in NON_LETTER
                              else "letter" for a in answers)
    conf = collections.Counter(a["confidence"] for a in answers)
    off = {k: v for k, v in conf.items() if k not in CONFIDENCES}

    print(f"asked        : {asked}")
    print(f"answered     : {len(answers)}")
    print(f"missing      : {len(missing)}")
    print(f"failed reqs  : {len(errored)}")
    print(f"answer mix   : {mix.most_common()}")
    print(f"confidence   : {conf.most_common()}")
    if off:
        print(f"OFF-MENU confidence, kept verbatim: {off}")
    if usage:
        print(f"actual tokens: {usage['input']:,} in, {usage['output']:,} out "
              f"({usage['thinking']:,} of it thinking)")
    if truncated:
        print(f"\n*** {len(truncated)} REQUEST(S) HIT max_tokens AND WERE CUT OFF ***")
        print("    Billed in full, and everything after the cut is lost.")
        for cid, out_t, think_t in truncated[:5]:
            print(f"      {cid}: {out_t:,} output tokens, {think_t:,} thinking")
        print("    Raise --max-tokens above the thinking budget, or lower --thinking.")
    if errored:
        print("\nFAILED REQUESTS -- these items were paid for and produced nothing:")
        for cid, kind, err in errored[:5]:
            print(f"  {cid} {kind} {err}")
    if missing:
        print("\nMISSING ITEMS -- in the request, absent from the answer table:")
        for cid, n, street in missing[:5]:
            print(f"  {cid} n={n} {street}")
        print("  Re-ask these with build_batch --only rather than re-running the county.")
    print(f"\nwrote {out}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("submit", help="price a request file, and send it with --yes")
    p.add_argument("file", type=pathlib.Path)
    p.add_argument("--yes", action="store_true", help="actually spend money")
    p.add_argument("--max-requests", type=int, default=MAX_REQUESTS)
    p.add_argument("--again", action="store_true",
                   help="send a file that was already sent. Pays for it twice.")

    p = sub.add_parser("status", help="processing status and per-request counts")
    p.add_argument("--id")
    p.add_argument("--watch", action="store_true")
    p.add_argument("--every", type=int, default=60)

    p = sub.add_parser("fetch", help="download raw result lines")
    p.add_argument("--id")
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("parse", help="answer tables to one row per place")
    p.add_argument("--id")
    p.add_argument("--results")
    p.add_argument("--index")
    p.add_argument("--out")

    p = sub.add_parser("verify", help="check the key and model id; bills nothing")
    p.add_argument("--model", default=MODEL_DEFAULT)

    p = sub.add_parser("reconcile", help="batches on the account vs run records here")

    p = sub.add_parser("cancel", help="cancel a batch; finished requests still bill")
    p.add_argument("--id", required=True)

    a = ap.parse_args()
    if a.cmd == "submit":
        submit(a.file, a.yes, a.max_requests, a.again)
    elif a.cmd == "verify":
        verify(a.model)
    elif a.cmd == "reconcile":
        reconcile()
    elif a.cmd == "cancel":
        cancel(a.id)
    elif a.cmd == "status":
        status(a.id, a.watch, a.every)
    elif a.cmd == "fetch":
        fetch(a.id, a.force)
    elif a.cmd == "parse":
        parse(a.id, a.results, a.index, a.out)


if __name__ == "__main__":
    main()
