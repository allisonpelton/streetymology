"""Emit an adjudication pack for equal-ground items where human and model
disagreed.

Two files, matching the pattern that worked for the labelling set itself:
a readable markdown brief, and a narrow CSV to type answers into. Candidate
text is never packed into a spreadsheet cell.

No blinding. The author remembers her own answers, so randomising which side
appears first bought nothing and only made the sheet harder to read. Both
answers are shown, attributed.
"""
import argparse, csv, os, re

from streetymology import rounds, taxonomy

DATA = os.environ.get("STREETYMOLOGY_DATA_DIR", "/workspace/streetymology-data")


def parse_items(path):
    items, cur = {}, None
    for line in open(path, encoding="utf-8"):
        if m := re.match(r"^### (\d+)\.\s+(.*)", line):
            cur = {"n": int(m.group(1)), "street": m.group(2).strip(),
                   "subdivision": "", "nearby": "", "cands": []}
            items[cur["n"]] = cur
        elif cur is None:
            continue
        elif m := re.match(r"^- \*\*Subdivision:\*\*\s*(.*)", line):
            cur["subdivision"] = m.group(1).strip()
        elif m := re.match(r"^- \*\*Nearby streets:\*\*\s*(.*)", line):
            cur["nearby"] = m.group(1).strip()
        elif m := re.match(r"^\s+- \*\*([A-E])\.\*\*\s*(.*)", line):
            cur["cands"].append((m.group(1), m.group(2).strip()))
    return items


def read_human(p):
    return {int(r["n"]): r for r in csv.DictReader(open(p, newline="", encoding="utf-8"))}


def read_model(p):
    rows = {}
    for line in open(p, encoding="utf-8"):
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) >= 6 and re.fullmatch(r"\d+", c[0]):
            rows[int(c[0])] = {"choice": c[2], "confidence": c[3], "reasoning": c[5]}
    return rows


def dedupe(cands, key):
    """Drop candidates whose QID already appeared, keeping the first letter."""
    seen, out = set(), []
    for letter, text in cands:
        q = key.get(letter)
        if q and q in seen:
            continue
        seen.add(q)
        out.append((letter, text))
    return out


def main():
    ap = argparse.ArgumentParser()
    rounds.add_argument(ap)
    ap.add_argument("--items")
    ap.add_argument("--human")
    ap.add_argument("--model")
    ap.add_argument("--key")
    ap.add_argument("--out-md")
    ap.add_argument("--out-csv")
    ap.add_argument("--only", default="",
                    help="restrict to these item numbers, e.g. a re-ruling pass")
    ap.add_argument("--unruled", action="store_true",
                    help="restrict to disagreements left without a verdict")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an answer sheet that already has verdicts")
    a = ap.parse_args()
    R = rounds.Round(a.round)
    a.items = a.items or R.items
    a.human = a.human or R.labels
    a.model = a.model or R.results
    a.key = a.key or R.key
    a.out_md = a.out_md or R.adjudication_md
    a.out_csv = a.out_csv or R.adjudication_csv
    print(f"round {R.n}: {R.deliverables}")

    # Refuse to clobber completed hand adjudication. It cannot be regenerated.
    if os.path.exists(a.out_csv) and not a.force:
        with open(a.out_csv, newline="", encoding="utf-8") as fh:
            filled = [r for r in csv.DictReader(fh) if r.get("verdict", "").strip()]
        if filled:
            raise SystemExit(
                f"{a.out_csv} already holds {len(filled)} verdicts. "
                "Move it aside or pass --force.")

    items, H, M = parse_items(a.items), read_human(a.human), read_model(a.model)
    keys = {}
    for r in csv.DictReader(open(a.key, newline="", encoding="utf-8")):
        keys[int(r["n"])] = dict(p.split("=") for p in r["candidates"].split("|"))

    disputed = [n for n in sorted(set(H) & set(M)) if H[n]["choice"] != M[n]["choice"]]
    if a.unruled:
        # Rows that went out for adjudication and came back without a verdict.
        with open(R.adjudication_csv, newline="", encoding="utf-8") as fh:
            blank = {int(r["n"]) for r in csv.DictReader(fh)
                     if not r.get("verdict", "").strip()}
        disputed = [n for n in disputed if n in blank]
    if a.only:
        want = {int(x) for x in a.only.replace(",", " ").split()}
        disputed = [n for n in disputed if n in want]

    body = [f"""# Equal-ground adjudication, round {R.n}

Items where the two answers differed. Rule on the evidence: pick the letter you
believe is the referent, or one of the abstentions.

{taxonomy.guide()}

You may pick an option neither side chose. Record answers in
`{os.path.basename(a.out_csv)}`.
"""]

    for n in disputed:
        it = items[n]
        cands = dedupe(it["cands"], keys.get(n, {}))
        dropped = len(it["cands"]) - len(cands)
        body.append(f"## {n}. {it['street']}\n")
        body.append(f"- **Subdivision:** {it['subdivision'] or '(none)'}")
        body.append(f"- **Nearby streets:** {it['nearby'] or '(none)'}")
        body.append("- **Candidates:**")
        for letter, text in cands:
            body.append(f"    - **{letter}.** {text}")
        body.extend(taxonomy.options_block())
        if dropped:
            body.append(f"\n  _({dropped} duplicate candidate(s) removed — same "
                        f"Wikidata item under another letter.)_")
        body.append(f"\n- Answers given: **{H[n]['choice']}** and **{M[n]['choice']}**\n")

    with open(a.out_md, "w", encoding="utf-8") as fh:
        fh.write("\n".join(body))

    with open(a.out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["n", "street", "verdict", "notes"])
        w.writeheader()
        for n in disputed:
            w.writerow({"n": n, "street": items[n]["street"], "verdict": "", "notes": ""})

    for p in (a.out_md, a.out_csv):
        os.chmod(p, 0o664)
    print(f"{len(disputed)} disputed items -> {a.out_md} + {a.out_csv}")


if __name__ == "__main__":
    main()
