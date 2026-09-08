"""A labelling set where the human gets exactly what the model gets.

AP's original labels were ~70% accurate against the audit, but she was working
from a spreadsheet with a bare label and a one-line description, no neighbour
context, and no way to tell Wikidata near-duplicates apart. This set gives her:

  - neighbour context from subdivision membership UNION streets within 200m
  - full Wikidata descriptions
  - aliases, which were the deciding evidence on White Pine ("Idaho white pine")
  - an explicit note when candidates share a description

The same file goes to a model afterwards, so the comparison is like-for-like.
Streets are drawn from those never previously labelled.
"""
import argparse, csv, json, random, time
from streetymology.config import LABELS_DIR, data_path
from streetymology import rounds
from streetymology.wikidata import query
from streetymology import themes, gazetteer as g, match, neighbours
from streetymology.candidates import publishable
from streetymology import taxonomy
from streetymology.normalize import key
from streetymology.streets import osm_cores

SEED = 20260907
N = 40
MAX_CAND = 5
LETTERS = "ABCDE"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=N, help="number of streets")
    ap.add_argument("--seed", type=int, default=SEED)
    rounds.add_argument(ap, default=None)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    if args.round is None:
        raise SystemExit("--round is required: name the round you are building.")
    R = rounds.Round(args.round)
    sheet = R.labels
    # Completed label sheets are hand-made and unregenerable.
    if sheet.exists():
        with sheet.open(newline="") as fh:
            filled = [r for r in csv.DictReader(fh) if r.get("choice", "").strip()]
        if filled:
            raise SystemExit(f"{sheet} already holds {len(filled)} answers. "
                             f"Pass a new --round to write another round.")

    assign = themes.load()
    idx = match.build_indexes(g.available(), g.index)
    m = {k: {c.domain for c in match.match(v["name"], idx,
             fallback_domains=g.FALLBACK_DOMAINS)} for k, v in assign.items()}
    tm = themes.ThemeModel(assign, m)
    ni = neighbours.NeighbourIndex()
    search = json.loads((data_path("search_unmatched.json")).read_text())
    meta = json.loads((data_path("meta_candidates.json")).read_text())
    already = {key(r["street"]) for r in csv.DictReader((LABELS_DIR / "labels_corrected.csv").open())}
    # Every previously issued labelling set, or the same streets come back.
    for prev in rounds.all_label_sheets():
        with prev.open(newline="") as fh:
            already |= {key(r["street"]) for r in csv.DictReader(fh) if r.get("street")}
    cores = osm_cores()

    pool = []
    for k, orig in cores.items():
        if k in already:
            continue
        cands = []
        for c in match.match(orig, idx, fallback_domains=g.FALLBACK_DOMAINS):
            d = meta.get(c.qid, {}).get("description", "")
            # Gazetteer matches used to bypass this filter entirely.
            if not publishable(d):
                continue
            cands.append({"qid": c.qid, "label": c.name, "description": d})
        for h in search.get(k, []):
            if not publishable(h.get("description")):
                continue
            if h["qid"] not in {x["qid"] for x in cands}:
                cands.append(h)
        seen, uniq = set(), []
        for c in cands:
            if c["qid"] not in seen:
                seen.add(c["qid"])
                uniq.append(c)
        if 2 <= len(uniq):
            pool.append((k, orig, uniq[:MAX_CAND]))
    picked = rng.sample(pool, min(args.n, len(pool)))
    print(f"pool {len(pool)} unlabelled streets with >=2 candidates; picked {len(picked)}")

    qids = sorted({c["qid"] for _, _, cs in picked for c in cs})
    alias = {}
    for i in range(0, len(qids), 200):
        b = qids[i:i + 200]
        q = ('SELECT ?s ?a WHERE { VALUES ?s {%s} ?s skos:altLabel ?a '
             'FILTER(lang(?a)="en") }' % " ".join("wd:" + x for x in b))
        try:
            for r in query(q, timeout=70):
                alias.setdefault(r["s"].rsplit("/", 1)[-1], []).append(r["a"])
        except Exception as e:
            print("alias fetch failed:", str(e)[:60])
        time.sleep(2)

    body, keyrows = [], []
    for n, (k, orig, cands) in enumerate(picked, 1):
        rng.shuffle(cands)
        sub, nb = neighbours.context(k, assign, tm, ni, limit=22)
        descs = [c.get("description", "") for c in cands]
        dupe = any(descs.count(d) > 1 for d in descs if d)
        lines = [f"### {n}. {orig}",
                 f"- **Subdivision:** {sub or '(none)'}",
                 f"- **Nearby streets:** {', '.join(nb) if nb else '(none)'}",
                 "- **Candidates:**"]
        for L, c in zip(LETTERS, cands):
            al = alias.get(c["qid"], [])
            al = f"  _also known as: {', '.join(sorted(set(al))[:4])}_" if al else ""
            lines.append(f"    - **{L}.** {c['label']} — "
                         f"{c.get('description') or '(no description)'}{al}")
        lines.extend(taxonomy.options_block())
        if dupe:
            lines.append("    _(note: two candidates share a description; the "
                         "aliases are the only way to tell them apart)_")
        body.append("\n".join(lines) + "\n")
        keyrows.append({"n": n, "street": orig, "key": k,
                        "candidates": "|".join(f"{L}={c['qid']}" for L, c in zip(LETTERS, cands))})

    hdr = f"""# Equal-ground labelling set — {len(picked)} streets

Same information a model would get: neighbour context, full Wikidata
descriptions, and aliases. Streets never labelled before.

## Background

{taxonomy.guide()}

Subdivisions are usually themed. Nearby streets are the strongest evidence.
Themes can be mixed, and many subdivisions have no theme at all.

Where several candidates are the same kind of thing, prefer the **least specific**
one that fits: "Prickly Pear" means the genus *Opuntia*, not a Galapagos species.

Candidate order is randomised.

## How to record answers

Fill in the companion `_labels.csv` — columns `choice` (A-E, NONE or NOETYM),
`confidence` (high/medium/low), and `notes`.

Afterwards, paste this same file into a fresh chat to get the model's answers for
comparison.

---

## Items ({len(picked)})

"""
    out = R.items
    out.write_text(hdr + "\n".join(body))
    kp = R.key
    with kp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(keyrows[0].keys()))
        w.writeheader(); w.writerows(keyrows)
    with sheet.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["n", "street", "choice", "confidence", "notes"])
        for r in keyrows:
            w.writerow([r["n"], r["street"], "", "", ""])
    for f in (out, sheet):
        f.chmod(0o664)
    print(f"{len(picked)} items -> {out}  ({out.stat().st_size/1000:.1f} KB)")
    print(f"answer sheet -> {sheet}")
    print(f"candidate map -> {kp}")
    dupes = sum(1 for b in body if "share a description" in b)
    print(f"items where candidates share a description: {dupes}")


if __name__ == "__main__":
    main()
