"""Audit the whole hand-labelled set by re-deciding every row with an LLM.

The selection experiment found 4 of 12 sampled `y` labels were wrong, so the
176-row ground truth needs checking. Every precision and AUC figure in the
project rests on it.

Format matches the validated selection experiment (95-100% adjudicated), so the
task is one the models are known to be good at. Split into chat-sized files.

The author's verdict is NEVER shown -- otherwise the audit just confirms itself.
"""
import csv, json, random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from streetymology.config import DATA_DIR, LABELS_DIR
from streetymology import themes, gazetteer as g, match
from streetymology.normalize import key

SEED = 20260906
PER_FILE = 44
MAX_CAND = 5
MAX_NEIGHBOURS = 18
REJECT = ("family name", "given name", "surname", "wikimedia", "disambiguation")
LETTERS = "ABCDE"
HEADER = """# Street name etymology audit — batch {b} of {t}

Street names in Ada County, Idaho (Boise and surrounding towns). For each
street, candidates were retrieved from Wikidata. Choose the one the street is
actually named after, or answer NONE.

## Essential background

Most American suburban street names have **no etymology at all**. A developer
filling out a plat picked a word because it sounded pleasant. Wikidata contains
*something* for almost any string — a lunar crater, a village in Romania, an
obscure album. A candidate existing is not evidence the street refers to it.

**NONE is expected to be a common answer.** Choosing a plausible-looking wrong
candidate is far worse than answering NONE.

Subdivisions are usually themed: all trees, all birds, all Idaho mining towns.
Neighbouring street names are the strongest evidence available. But themes can
be mixed, and many subdivisions have no theme at all.

Where several candidates are the same kind of thing, prefer the **least
specific** one that fits. "Prickly Pear" means the genus *Opuntia*, not a
Galapagos endemic species. "Meadowlark" means the meadowlark, not one species
of it.

Candidate order is randomised and carries no information.

## Output format

Return a markdown table, one row per item, nothing else:

| n | street | choice | confidence | theme | reasoning |

- `choice`: a single letter (A-E) or `NONE`
- `confidence`: high / medium / low
- `theme`: subdivision theme, or `none`, or `unclear`
- `reasoning`: one sentence, max ~20 words

---

## Items ({n})

"""


def strip_dir(n):
    p = n.split(" ", 1)
    return p[1] if p[0] in ("North", "South", "East", "West") and len(p) > 1 else n


def usable(h):
    d = (h.get("description") or "").lower()
    return bool(d) and not any(r in d for r in REJECT)


def main():
    rng = random.Random(SEED)
    assign = themes.load()
    idx = match.build_indexes(g.available(), g.index)
    m = {k: {c.domain for c in match.match(v["name"], idx,
             fallback_domains=g.FALLBACK_DOMAINS)} for k, v in assign.items()}
    tm = themes.ThemeModel(assign, m)
    search = json.loads((DATA_DIR / "search_controls.json").read_text())
    meta = json.loads((DATA_DIR / "meta_candidates.json").read_text())
    rows = [r for r in csv.DictReader((LABELS_DIR / "labels_merged.csv").open())
            if r["verdict"] in ("y", "n", "w")]

    items = []
    for r in rows:
        k = key(r["street"])
        cands, seen = [], set()
        # the entity the author was shown, so her choice is always available
        cands.append({"qid": r["qid"], "label": r["wikidata_label"],
                      "description": meta.get(r["qid"], {}).get("description", "")})
        seen.add(r["qid"])
        for h in search.get(k, []):
            if h["qid"] in seen or not usable(h):
                continue
            cands.append(h); seen.add(h["qid"])
            if len(cands) >= MAX_CAND:
                break
        rng.shuffle(cands)
        items.append({"street": r["street"], "key": k, "cands": cands,
                      "author_verdict": r["verdict"], "author_qid": r["qid"],
                      "domain": r["domain"]})
    rng.shuffle(items)

    batches = [items[i:i + PER_FILE] for i in range(0, len(items), PER_FILE)]
    out_dir = DATA_DIR / "deliverables"
    keyrows = []
    n = 0
    for bi, batch in enumerate(batches, 1):
        body = []
        for it in batch:
            n += 1
            subs = tm.subdivisions_of(it["key"], assign)
            sub = max(subs, key=lambda s: len(tm.members.get(s, ())), default="")
            peers = sorted(tm.members.get(sub, set()) - {it["key"]}) if sub else []
            nb = sorted({strip_dir(assign[p]["name"]) for p in peers})[:MAX_NEIGHBOURS]
            lines = [f"### {n}. {it['street']}",
                     f"- **Subdivision:** {sub or '(none)'}",
                     f"- **Other streets there:** {', '.join(nb) if nb else '(none)'}",
                     "- **Candidates:**"]
            letter_of = {}
            for L, h in zip(LETTERS, it["cands"]):
                lines.append(f"    - **{L}.** {h['label']} — {h.get('description','') or '(no description)'}")
                letter_of[h["qid"]] = L
            lines.append("    - **NONE.** No candidate above is the referent.")
            body.append("\n".join(lines) + "\n")
            keyrows.append({"n": n, "street": it["street"], "domain": it["domain"],
                            "author_verdict": it["author_verdict"],
                            "author_qid": it["author_qid"],
                            "author_letter": letter_of.get(it["author_qid"], ""),
                            "candidates": "|".join(f"{L}={h['qid']}"
                                                   for L, h in zip(LETTERS, it["cands"]))})
        p = out_dir / f"label_audit_{bi}.md"
        p.write_text(HEADER.format(b=bi, t=len(batches), n=len(batch)) + "\n".join(body))
        print(f"  {p.name}: {len(batch)} items, {p.stat().st_size/1000:.1f} KB")
    kp = DATA_DIR / "artifacts" / "label_audit_KEY.csv"
    with kp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(keyrows[0].keys()))
        w.writeheader(); w.writerows(keyrows)
    print(f"\n{len(items)} items in {len(batches)} files -> {out_dir}")
    print(f"key -> {kp}")


if __name__ == "__main__":
    main()
