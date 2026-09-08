"""Would the deterministic matcher have beaten the LLM on any round-2 item?

The gazetteer stage publishes its best-confidence match. This replays that
decision over an adjudicated round and scores it against the same truth the
human and the model were scored against, so all three are answering one
question on one set.

Truth is the author's label, overridden by her adjudication verdict. Rows she
left unruled are dropped. A letter answer is converted to a QID through the
round key; NONE and NOETYM both mean "publish nothing".
"""
import argparse, csv, json

from streetymology import gazetteer as g, match, rounds
from streetymology.candidates import publishable
from streetymology.config import data_path

NONE, NOETYM = "NONE", "NOETYM"


def main():
    ap = argparse.ArgumentParser()
    rounds.add_argument(ap)
    ap.add_argument("--filtered", action="store_true",
                    help="apply the candidate filter before picking, as the pipeline now does")
    a = ap.parse_args()
    R = rounds.Round(a.round)

    meta = json.loads(data_path("meta_candidates.json").read_text())
    with R.key.open(newline="") as fh:
        key_qids = {int(r["n"]): dict(p.split("=") for p in r["candidates"].split("|"))
                    for r in csv.DictReader(fh)}
    with R.labels.open(newline="") as fh:
        H = {int(r["n"]): r for r in csv.DictReader(fh) if r.get("choice", "").strip()}
    V, unruled = {}, set()
    with R.adjudication_csv.open(newline="") as fh:
        for r in csv.DictReader(fh):
            n = int(r["n"])
            if r.get("verdict", "").strip():
                V[n] = r["verdict"].strip().upper()
            else:
                unruled.add(n)

    model = {}
    for line in R.results.read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0].isdigit():
            model[int(cells[0])] = cells[2].strip().upper()

    idx = match.build_indexes(g.available(), g.index)

    rows = []
    for n, r in H.items():
        if n in unruled:
            continue
        final = V.get(n, r["choice"].strip().upper())
        truth_qid = key_qids.get(n, {}).get(final) if final not in (NONE, NOETYM) else None

        cands = match.match(r["street"], idx, fallback_domains=g.FALLBACK_DOMAINS)
        if a.filtered:
            cands = [c for c in cands
                     if publishable(meta.get(c.qid, {}).get("description", ""))]
        pick = cands[0].qid if cands else None

        # The heuristic has no abstention: if it matched, it publishes.
        heur_right = (pick == truth_qid) if truth_qid else (pick is None)
        m = model.get(n, "")
        model_qid = key_qids.get(n, {}).get(m) if m not in (NONE, NOETYM, "") else None
        model_right = (model_qid == truth_qid) if truth_qid else (m in (NONE, NOETYM))

        rows.append({"n": n, "street": r["street"], "final": final,
                     "pick": pick, "heur": heur_right, "model": model_right,
                     "matched": bool(cands)})

    tot = len(rows)
    def pct(k): return f"{k}/{tot} = {k/tot:.0%}"
    print(f"round {R.n}: {tot} adjudicated items"
          f"{' (candidate filter applied)' if a.filtered else ''}\n")
    print(f"gazetteer produced a match for {pct(sum(r['matched'] for r in rows))}")
    print(f"heuristic correct   {pct(sum(r['heur'] for r in rows))}")
    print(f"model correct       {pct(sum(r['model'] for r in rows))}")

    both = sum(r["heur"] and r["model"] for r in rows)
    hnot = [r for r in rows if r["heur"] and not r["model"]]
    mnot = sum(r["model"] and not r["heur"] for r in rows)
    print(f"\nboth right {both} | heuristic only {len(hnot)} | model only {mnot}"
          f" | neither {tot - both - len(hnot) - mnot}")

    # The question that decides whether the gazetteer stage still earns its place.
    print(f"\nitems the heuristic got right and the model did not: {len(hnot)}")
    for r in hnot:
        print(f"  {r['n']:4d}  {r['street']:<34} truth {r['final']:<7} "
              f"{'matched ' + r['pick'] if r['pick'] else 'no match'}")

    publishable_rows = [r for r in rows if r["final"] not in (NONE, NOETYM)]
    if publishable_rows:
        hp = sum(r["heur"] for r in publishable_rows)
        mp = sum(r["model"] for r in publishable_rows)
        print(f"\non the {len(publishable_rows)} items with a real referent:")
        print(f"  heuristic {hp}/{len(publishable_rows)} = {hp/len(publishable_rows):.0%}")
        print(f"  model     {mp}/{len(publishable_rows)} = {mp/len(publishable_rows):.0%}")


if __name__ == "__main__":
    main()
