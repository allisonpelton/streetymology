"""Second $0 experiment: SELECTING among several search-derived candidates.

The first feasibility test validated judging ONE gazetteer-derived candidate
(yes/no). This is a different, harder task: pick the right entity from four or
five, or say none fits. Its accuracy is unmeasured and must not be assumed from
the first result.

Controls come from AP's hand labels, so ground truth exists:
  - `y` rows whose correct QID appears among the search results -> the model
    should pick that QID.
  - `n` rows -> the model should answer NONE. Caveat: search may surface a
    genuinely correct entity AP never saw, so disagreements here need
    adjudication rather than automatic scoring as errors.
"""
import csv, json, random
from streetymology.config import LABELS_DIR, data_path, ARTIFACTS_DIR, DELIVERABLES_DIR
from streetymology import themes, gazetteer as g, match
from streetymology.normalize import key

SEED = 20260905
# Candidate order is shuffled per item. Search relevance put the correct answer
# at position A in 9 of 12 positive controls, so an unshuffled run could be aced
# by always answering A without reading anything.
N_POS, N_NEG, N_UNKNOWN = 12, 10, 18
MAX_CAND = 5
MAX_NEIGHBOURS = 20
REJECT = ("family name", "given name", "surname", "wikimedia", "disambiguation")
LETTERS = "ABCDE"


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
    ctrl_search = json.loads((data_path("search_controls.json")).read_text())
    unm_search = json.loads((data_path("search_unmatched.json")).read_text())
    lab = [r for r in csv.DictReader((LABELS_DIR / "labels_merged.csv").open())
           if r["verdict"] in ("y", "n")]

    pos = [r for r in lab if r["verdict"] == "y"
           and any(h["qid"] == r["qid"] for h in ctrl_search.get(key(r["street"]), []))]
    neg = [r for r in lab if r["verdict"] == "n"]
    pos, neg = rng.sample(pos, min(N_POS, len(pos))), rng.sample(neg, min(N_NEG, len(neg)))
    unk_keys = rng.sample([k for k, v in unm_search.items()
                           if len([h for h in v if usable(h)]) >= 2], N_UNKNOWN)

    items = []
    for r in pos + neg:
        k = key(r["street"])
        cands = [h for h in ctrl_search.get(k, []) if usable(h)][:MAX_CAND]
        if r["verdict"] == "y" and not any(h["qid"] == r["qid"] for h in cands):
            cands = cands[:MAX_CAND - 1] + [h for h in ctrl_search[k] if h["qid"] == r["qid"]]
        rng.shuffle(cands)          # see note below on positional bias
        items.append({"street": r["street"], "key": k, "cands": cands,
                      "truth": r["qid"] if r["verdict"] == "y" else "NONE",
                      "control": True})
    for k in unk_keys:
        c = [h for h in unm_search[k] if usable(h)][:MAX_CAND]
        rng.shuffle(c)
        items.append({"street": assign.get(k, {}).get("name", k), "key": k,
                      "cands": c, "truth": "", "control": False})
    rng.shuffle(items)

    body = []
    for i, it in enumerate(items, 1):
        subs = tm.subdivisions_of(it["key"], assign)
        sub = max(subs, key=lambda s: len(tm.members.get(s, ())), default="")
        peers = sorted(tm.members.get(sub, set()) - {it["key"]}) if sub else []
        nb = sorted({strip_dir(assign[p]["name"]) for p in peers})[:MAX_NEIGHBOURS]
        lines = [f"### {i}. {it['street']}",
                 f"- **Subdivision:** {sub or '(none)'}",
                 f"- **Other streets there:** {', '.join(nb) if nb else '(none)'}",
                 "- **Candidates:**"]
        for L, h in zip(LETTERS, it["cands"]):
            lines.append(f"    - **{L}.** {h['label']} — {h.get('description','')}")
        lines.append("    - **NONE.** No candidate above is the referent.")
        body.append("\n".join(lines) + "\n")

    header = f"""# Street name etymology: pick the referent

Street names in Ada County, Idaho (Boise and surrounding towns). For each
street, candidates were retrieved from Wikidata by text search. Choose the one
the street is actually named after, or answer NONE.

## Essential background

Most American suburban street names have **no etymology at all**. A developer
filling out a plat picked a word because it sounded pleasant. Search will always
return *something* — a lunar crater, a village in Romania, an obscure album —
because the string exists somewhere in Wikidata. A candidate existing is not
evidence that the street refers to it.

**NONE is expected to be a common answer.** Choosing a plausible-looking wrong
candidate is far worse than answering NONE.

Subdivisions are usually themed: all trees, all birds, all Idaho mining towns.
The neighbouring street names are the strongest evidence available. A street
named "Griffon" surrounded by Doberman, Bluetick and Chesapeake is a dog breed,
not a mythological creature. But themes can be mixed, and many subdivisions have
no theme at all — just pleasant-sounding invented compounds.

Candidate order is **randomised**. It carries no information at all — the
correct answer is as likely to be last as first.

## Output format

Return a markdown table, one row per item, nothing else:

| n | street | choice | confidence | theme | reasoning |

- `choice`: a single letter (A-E) or `NONE`
- `confidence`: high / medium / low
- `theme`: the subdivision theme you infer, or `none`, or `unclear`
- `reasoning`: one sentence, max ~20 words

---

## Items ({len(items)})

"""
    out = DELIVERABLES_DIR / "selection_experiment.md"
    out.write_text(header + "\n".join(body))
    keyp = ARTIFACTS_DIR / "selection_experiment_KEY.csv"
    with keyp.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["n", "street", "is_control", "truth_qid", "truth_letter", "candidates"])
        for i, it in enumerate(items, 1):
            letter = ""
            if it["truth"] and it["truth"] != "NONE":
                for L, h in zip(LETTERS, it["cands"]):
                    if h["qid"] == it["truth"]:
                        letter = L
            elif it["truth"] == "NONE":
                letter = "NONE"
            w.writerow([i, it["street"], "yes" if it["control"] else "no",
                        it["truth"], letter,
                        "|".join(f"{L}={h['qid']}" for L, h in zip(LETTERS, it["cands"]))])
    print(f"{len(items)} items ({len(pos)} positive controls, {len(neg)} negative, "
          f"{len(unk_keys)} unknown)")
    print(f"experiment -> {out}\nkey        -> {keyp}")
    print(f"size: {out.stat().st_size/1000:.1f} KB")


if __name__ == "__main__":
    main()
