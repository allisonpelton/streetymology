"""Build a self-contained experiment for a fresh (non-Code) Claude chat.

Purpose: test whether reading raw neighbouring street names resolves cases the
deterministic theme signal cannot. Runs on claude.ai under a Pro subscription,
so it costs nothing and decides whether API billing is justified.

Design notes:
- Known-label CONTROLS are mixed in, shuffled and unmarked, so the result can be
  scored rather than merely collected.
- No computed signal scores, sitelink counts or gazetteer domains for the
  NEIGHBOURS are included: those would leak our reasoning into the answer.
- The proposed candidate IS shown, because the real pipeline is
  retrieve-then-select, not generate.
"""
import csv, json, random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from streetymology.config import DATA_DIR, LABELS_DIR
from streetymology import gazetteer as g, match, themes
from streetymology.normalize import key

SEED = 20260904
N_CONTROLS = 17
MAX_NEIGHBOURS = 25
OUT = DATA_DIR / "artifacts" / "llm_experiment.md"


def strip_dir(name: str) -> str:
    parts = name.split(" ", 1)
    return parts[1] if parts[0] in ("North", "South", "East", "West") and len(parts) > 1 else name


def main():
    rng = random.Random(SEED)
    assign = themes.load()
    idx = match.build_indexes(g.available(), g.index)
    m = {k: {c.domain for c in match.match(v["name"], idx)} for k, v in assign.items()}
    tm = themes.ThemeModel(assign, m)
    meta = json.loads((DATA_DIR / "meta_candidates.json").read_text())
    locs = json.loads((DATA_DIR / "meta_location.json").read_text()) if (
        DATA_DIR / "meta_location.json").exists() else {}

    rows = list(csv.DictReader((LABELS_DIR / "labels_merged.csv").open()))
    unknown = [r for r in rows if r["verdict"] == "q"]
    decided = [r for r in rows if r["verdict"] in ("y", "n")]
    # Stratify controls: the main failure mode we are testing for is
    # over-eager agreement, which only shows up against known negatives.
    pos = [r for r in decided if r["verdict"] == "y"]
    neg = [r for r in decided if r["verdict"] == "n"]
    half = N_CONTROLS // 2
    controls = (rng.sample(pos, min(half, len(pos)))
                + rng.sample(neg, min(N_CONTROLS - half, len(neg))))
    items = unknown + controls
    rng.shuffle(items)

    lines = []
    for i, r in enumerate(items, 1):
        k = key(r["street"])
        subs = tm.subdivisions_of(k, assign)
        sub = max(subs, key=lambda s: len(tm.members.get(s, ())), default=None)
        peers = sorted(tm.members.get(sub, set()) - {k}) if sub else []
        names = sorted({strip_dir(assign[p]["name"]) for p in peers})[:MAX_NEIGHBOURS]
        md = meta.get(r["qid"], {})
        loc = locs.get(r["qid"], "")
        lines.append(
            f"### {i}. {r['street']}\n"
            f"- **Proposed:** {r['wikidata_label']} — {md.get('description','(no description)')}"
            + (f" _(located in {loc})_" if loc else "") + "\n"
            f"- **Category:** {r['domain']}\n"
            f"- **Subdivision:** {sub or '(none)'}\n"
            f"- **Other streets in that subdivision:** "
            + (", ".join(names) if names else "(none)") + "\n"
        )

    header = f"""# Street-name etymology: judgement task

You are helping evaluate street name etymologies in Ada County, Idaho (Boise and
surrounding towns). For each street below, a candidate Wikidata entity has been
proposed by an automated matcher. Your job is to judge whether it is right.

## Essential background

Most American suburban street names have **no etymology at all**. A developer
filling out a plat picked a word because it sounded pleasant. "Meadowlark Lane"
usually does not honour the bird *Sturnella neglecta* — it is decoration.
So the goal is not to find a referent for everything. It is to identify the
minority that genuinely refer to something, and to say so when nothing does.

Subdivisions are typically themed: all trees, all birds, all Idaho mining towns.
The neighbouring street names are therefore strong evidence. A street named
"Griffon" surrounded by Doberman, Bluetick and Chesapeake is a dog breed, not a
mythological creature. But themes can be **mixed** (one real subdivision here
combines dog breeds, racehorses and racetracks), and many subdivisions have no
theme at all — just pleasant-sounding invented compounds.

## Verdict codes

- `y` — correct. The street really is named after the proposed entity.
- `w` — right **category**, wrong specific item. (e.g. it is named after some
  river, but not the one proposed.)
- `n` — wrong. Not this, and not anything in this category.
- `q` — genuinely unsure.

`q` and `n` are valuable answers. A confident wrong answer is much worse than an
honest "unsure". Do not reach for a referent that is not there.

## Output format

Return a markdown table, one row per item, nothing else:

| n | street | verdict | confidence | theme | reasoning |

- `confidence`: high / medium / low
- `theme`: the theme you infer for the subdivision, or `none` if you see no
  theme, or `unclear`
- `reasoning`: one sentence, max ~20 words

---

## Items ({len(items)})

"""
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(header + "\n".join(lines))

    key_path = DATA_DIR / "artifacts" / "llm_experiment_KEY.csv"
    with key_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["n", "street", "domain", "qid", "true_verdict", "is_control"])
        for i, r in enumerate(items, 1):
            w.writerow([i, r["street"], r["domain"], r["qid"],
                        r["verdict"], "yes" if r["verdict"] != "q" else "no"])
    print(f"{len(items)} items ({len(unknown)} unknown, {len(controls)} controls)")
    print(f"experiment -> {OUT}")
    print(f"answer key -> {key_path}  (do NOT paste this into the chat)")
    print(f"size: {OUT.stat().st_size/1000:.1f} KB")


if __name__ == "__main__":
    main()
