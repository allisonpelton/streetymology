"""Batch results to one row per place.

The model answers in a markdown table, one row per item, keyed by the item
number the prompt gave it. This reads those tables back, joins them to the
index `build_batch` wrote, and produces the answers CSV everything downstream
reads.

It makes no network calls and knows nothing about batches. `run_batch` fetches
the result lines; this turns them into answers.
"""
import collections
import csv
import json
import pathlib
import re

from streetymology.config import ARTIFACTS_DIR, atomic_write, data_path
from streetymology.prompt import LETTERS

# Answers the prompt offers besides a candidate letter. Anything else is a
# parse failure, not a new answer class.
NON_LETTER = {"NONE", "INVENTED", "PERSONAL"}

# The prompt offers exactly these three. Off-menu values are recorded verbatim
# and counted rather than coerced into a neighbouring band.
CONFIDENCES = {"high", "medium", "low"}

_ROW = re.compile(r"^\s*\|")


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


def parse(rec=None, results=None, index=None, out=None):
    """Answer tables to one row per place. `rec` is a run record, or None.

    The caller supplies the record rather than this module looking one up,
    because a results file and an index are enough on their own. That is how a
    file recovered by hand gets parsed without inventing a record for it.
    """
    rec = rec or {}
    results = pathlib.Path(results or ARTIFACTS_DIR / f"{rec['batch_id']}.results.jsonl")
    index = pathlib.Path(index or rec["index_file"])
    if not results.exists():
        raise ValueError(f"no results at {results}. Fetch first.")

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
    with atomic_write(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["place", "street", "n", "custom_id",
                                           "choice", "qid", "label",
                                           "confidence", "theme", "reasoning"])
        w.writeheader()
        for a in sorted(answers, key=lambda a: a["n"]):
            w.writerow(a)

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
        print("\nFAILED REQUESTS. These items were paid for and produced nothing:")
        for cid, kind, err in errored[:5]:
            print(f"  {cid} {kind} {err}")
    if missing:
        print("\nMISSING ITEMS. In the request, absent from the answer table:")
        for cid, n, street in missing[:5]:
            print(f"  {cid} n={n} {street}")
        print("  Re-ask these with build_batch --only rather than re-running the county.")
    print(f"\nwrote {out}")
    return out
