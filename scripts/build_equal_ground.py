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
import csv, json, random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from streetymology.config import DATA_DIR, LABELS_DIR
from streetymology.wikidata import query
from streetymology import themes, gazetteer as g, match, neighbours
from streetymology.normalize import key
from streetymology.streets import osm_cores

SEED = 20260907
N = 40
MAX_CAND = 5
REJECT = ("wikimedia", "disambiguation")
LETTERS = "ABCDE"


def main():
    rng = random.Random(SEED)
    assign = themes.load()
    idx = match.build_indexes(g.available(), g.index)
    m = {k: {c.domain for c in match.match(v["name"], idx,
             fallback_domains=g.FALLBACK_DOMAINS)} for k, v in assign.items()}
    tm = themes.ThemeModel(assign, m)
    ni = neighbours.NeighbourIndex()
    search = json.loads((DATA_DIR / "search_unmatched.json").read_text())
    meta = json.loads((DATA_DIR / "meta_candidates.json").read_text())
    already = {key(r["street"]) for r in csv.DictReader((LABELS_DIR / "labels_corrected.csv").open())}
    cores = osm_cores()

    pool = []
    for k, orig in cores.items():
        if k in already:
            continue
        cands = []
        for c in match.match(orig, idx, fallback_domains=g.FALLBACK_DOMAINS):
            cands.append({"qid": c.qid, "label": c.name,
                          "description": meta.get(c.qid, {}).get("description", "")})
        for h in search.get(k, []):
            d = (h.get("description") or "").lower()
            if not d or any(r in d for r in REJECT):
                continue
            if h["qid"] not in {x["qid"] for x in cands}:
                cands.append(h)
        if 2 <= len(cands):
            pool.append((k, orig, cands[:MAX_CAND]))
    picked = rng.sample(pool, min(N, len(pool)))

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
        # Dedupe by QID. The same entity reached the pool under more than one
        # letter twice in the 40-item set, so two of the five options were not
        # a choice at all.
        seen, uniq = set(), []
        for c in cands:
            if c["qid"] not in seen:
                seen.add(c["qid"])
                uniq.append(c)
        cands = uniq
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
        lines.append("    - **NONE.** A referent may exist, but no candidate "
                     "above is it.")
        lines.append("    - **NOETYM.** The name has no etymology worth "
                     "publishing: invented, purely descriptive, or a bare "
                     "surname or given name used as filler.")
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

Most American suburban street names have **no etymology at all** — a developer
picked a word because it sounded pleasant. Wikidata contains something for almost
any string. A candidate existing is not evidence the street refers to it.
**NONE and NOETYM are expected to be common answers.**

Two different abstentions, and the difference matters:

- **NONE** — a real referent may well exist, but it is not among the candidates.
- **NOETYM** — the name has no etymology worth publishing at all. Invented,
  purely descriptive ("Westview"), or a bare surname or given name that only
  matches because Wikidata has an item for the surname. Choosing the surname
  item would be technically correct and editorially useless.

NOETYM rows are excluded from the human/model comparison, because they turn on
an editorial judgement about what belongs in OSM rather than on evidence.

Subdivisions are usually themed. Nearby streets are the strongest evidence.
Themes can be mixed, and many subdivisions have no theme at all.

Where several candidates are the same kind of thing, prefer the **least specific**
one that fits: "Prickly Pear" means the genus *Opuntia*, not a Galapagos species.

Candidate order is randomised.

## How to record answers

Fill in `equal_ground_labels.csv` — columns `choice` (A-E, NONE or NOETYM),
`confidence` (high/medium/low), and `notes`.

Afterwards, paste this same file into a fresh chat to get the model's answers for
comparison.

---

## Items ({len(picked)})

"""
    out = DATA_DIR / "deliverables" / "equal_ground.md"
    out.write_text(hdr + "\n".join(body))
    kp = DATA_DIR / "artifacts" / "equal_ground_KEY.csv"
    with kp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(keyrows[0].keys()))
        w.writeheader(); w.writerows(keyrows)
    sheet = DATA_DIR / "deliverables" / "equal_ground_labels.csv"
    with sheet.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["n", "street", "choice", "confidence", "notes"])
        for r in keyrows:
            w.writerow([r["n"], r["street"], "", "", ""])
    print(f"{len(picked)} items -> {out}  ({out.stat().st_size/1000:.1f} KB)")
    print(f"answer sheet -> {sheet}")
    print(f"candidate map -> {kp}")
    dupes = sum(1 for b in body if "share a description" in b)
    print(f"items where candidates share a description: {dupes}")


if __name__ == "__main__":
    main()
