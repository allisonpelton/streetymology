"""One chat-ready prompt over every street AP has labelled, with plat context.

240 items: round 1's 40 and round 2's 200, renumbered into a single sequence so
they fit one paste. Candidates, their letters and their order are copied verbatim
from the round files, because AP's answers are recorded against those letters and
regenerating candidates would void them.

Two things are rewritten per item:

  the context   one flat "Nearby streets" line becomes three tiers -- named by
                this subdivision, in it but named by another, nearby and outside
                it -- plus how confident we are the subdivision laid the street
                out and that its name follows a theme.
  the answers   NONE/NOETYM becomes NONE/INVENTED/PERSONAL, the taxonomy from
                deliverables/equal_ground/all_labels_recode.csv, which is the
                ground truth this run is scored against.

Plat phases are merged per data/plat_judgement/phase_merges.json. That file is
hand judgement, not a rule: see scripts/plat_phase_report.py for the evidence.

Usage:
  python scripts/build_context_prompt.py
"""
import argparse
import csv
import json
import pathlib
import re

from streetymology.config import data_path, DELIVERABLES_DIR, ROOT
from streetymology.normalize import key

MERGES = ROOT / "data" / "plat_judgement" / "phase_merges.json"
R1 = DELIVERABLES_DIR / "equal_ground" / "round1" / "equal_ground.md"
R2 = DELIVERABLES_DIR / "equal_ground" / "round2" / "equal_ground_2.md"
OUT_DIR = DELIVERABLES_DIR / "context_prompt"
VOID = {(2, 152)}          # OSM renamed the street; recorded in CLAUDE.md

HEADER = """# Street etymology — 240 items

For each street, choose the Wikidata item it is named after, or say that none
applies. Candidate order is randomised and carries no meaning.

## Essential background

Most American suburban street names have **no etymology at all** — a developer
picked a word because it sounded pleasant. Wikidata contains something for almost
any string. A candidate existing is not evidence the street refers to it.
**The three non-candidate answers are expected to be common.**

Subdivisions are usually themed, so the names of streets *named by the same
subdivision* are the strongest evidence available. Themes can be mixed, and many
subdivisions have no theme at all.

Where several candidates are the same kind of thing, prefer the **least specific**
one that fits: "Prickly Pear" means the genus *Opuntia*, not a Galapagos species.

## How to read the context

Each item names the subdivision that platted the street, then three tiers of
neighbouring street names, strongest evidence first:

- **Named by that subdivision** — platted by the same act. One theme, if there
  is one, lives here.
- **In that subdivision, named by a different one** — the plats overlap, but a
  different developer chose the name. Related, weaker.
- **Nearby, outside it** — adjacent or unplatted ground. Weakest; proximity
  alone is not evidence of a shared theme. Rarely, one of these streets could 
  be the etymology.

Two numbers are given, both 0 to 1:

- **Confidence this subdivision laid the street out.** Below about 0.9, treat the subdivision and its street names as uncertain.
- **Confidence its name follows that subdivision's theme.** This is the
  confidence above, reduced by the plat's age. Older subdivisions seldom have themes beyond trees
  and presidents. This number doesn't imply the subdivision has a theme or 
  that every listed street is part of the theme. If this value is low, themes
  are likely coincidental.

## Answers

- A single **candidate letter**.
- **NONE** — a real etymology probably exists, but no candidate above is it.
- **INVENTED** — no referent exists. A developer coined the name.
- **PERSONAL** — named for a person or a family. A real referent exists, but
  Wikidata does not carry it.

## Output format
Return a markdown table, one row per item, nothing else:
| n | street | choice | confidence | theme | reasoning |
- choice: a candidate letter, NONE, INVENTED, or PERSONAL
- confidence: high / medium / low
- theme: the subdivision theme you infer, or none, or unclear
- reasoning: one sentence, max ~20 words

---

## Items (240)
"""

OPTIONS = [
    "    - **NONE.** A real etymology probably exists, but no candidate above is it.",
    "    - **INVENTED.** No referent exists. A developer coined the name.",
    "    - **PERSONAL.** Named for a person or a family. A real referent exists,"
    " but Wikidata does not carry it.",
]


def load_merges():
    """base name -> the set of base names it is one naming act with."""
    doc = json.loads(MERGES.read_text())
    fam = {}
    for entry in doc["merge"]:
        members = set(entry["family"])
        for m in members:
            fam[m] = members
    return fam


def context_index(merges):
    """place id -> record, plus a map from a place to its merged peer group."""
    ctx = json.loads(data_path("place_context.json").read_text())
    by_core = {}
    for pid, rec in ctx.items():
        by_core.setdefault(pid.split("#")[0], []).append((pid, rec))
    return ctx, by_core


def pick(street, by_core):
    places = by_core.get(key(street))
    if not places:
        return None
    if len(places) == 1:
        return places[0][1]
    exact = [r for _, r in places if r.get("name") == street]
    pool = exact or [r for _, r in places]
    return max(pool, key=lambda r: len(r.get("peers", ())))


def upper_base(name):
    return (name or "").upper().strip()


def tiers(rec, ctx, by_core, merges):
    """The three tiers, deduped so a street appears once at its strongest."""
    def nm(pid):
        r = ctx.get(pid)
        return r["display"] if r else None

    peers = [nm(p) for p in rec.get("peers", ()) if nm(p)]

    # Phase merge: pull in places whose naming plat is in the same judged family.
    plat = upper_base(rec.get("naming_plat"))
    family = merges.get(plat)
    if family:
        for pid, other in ctx.items():
            if upper_base(other.get("naming_plat")) in family and nm(pid):
                peers.append(nm(pid))

    same = [nm(p) for p in rec.get("same_plat", ()) if nm(p)]
    near = sorted({nm(p) for b in ("attached", "near_unplatted")
                   for p in rec.get(b, ()) if nm(p)})

    mine = rec.get("display")
    seen = {mine}
    def dedupe(seq):
        out = []
        for x in seq:
            if x and x not in seen:
                seen.add(x)
                out.append(x)
        return out

    return dedupe(sorted(set(peers))), dedupe(same), dedupe(near), bool(family)


def render(n, street, cand_lines, rec, ctx, by_core, merges):
    L = [f"### {n}. {street}"]
    if rec is None:
        L.append("- **Subdivision:** unknown — this street is not in the plat data")
        L += ["- **Candidates:**"] + cand_lines + OPTIONS
        return "\n".join(L), False
    plat = rec.get("naming_plat")
    if plat:
        yr = (rec.get("naming_recorded") or "")[:4]
        L.append(f"- **Subdivision:** {plat}" + (f", platted {yr}" if yr else ""))
        L.append("- **Confidence this subdivision laid the street out:** "
                 f"{rec['confidence']:.2f}")
        L.append("- **Confidence its name follows that subdivision's theme:** "
                 f"{rec['theme_confidence']:.2f}")
    else:
        L.append("- **Subdivision:** none — no subdivision appears to have named "
                 "this street")
        L.append("- **Confidence its name follows a subdivision theme:** low")
    a, b, c, merged = tiers(rec, ctx, by_core, merges)
    L.append("- **Named by that subdivision:** " + (", ".join(a) or "(none)"))
    L.append("- **In that subdivision, named by a different one:** "
             + (", ".join(b) or "(none)"))
    L.append("- **Nearby, outside it:** " + (", ".join(c) or "(none)"))
    L += ["- **Candidates:**"] + cand_lines + OPTIONS
    return "\n".join(L), merged


def items_from(path, round_n):
    text = pathlib.Path(path).read_text()
    for block in re.split(r"^### ", text, flags=re.M)[1:]:
        head, rest = block.split("\n", 1)
        num, street = head.split(". ", 1)
        cands = [l for l in rest.splitlines()
                 if l.startswith("    - **")
                 and not re.match(r"\s+- \*\*(NONE|NOETYM)\.", l)]
        yield round_n, int(num), street.strip(), cands


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(OUT_DIR / "context_prompt.md"))
    ap.add_argument("--index", default=str(OUT_DIR / "context_prompt_index.csv"))
    a = ap.parse_args()

    merges = load_merges()
    ctx, by_core = context_index(merges)

    rows, blocks, n = [], [], 0
    merged_items = 0
    for src, rnd in ((R1, 1), (R2, 2)):
        for _, old_n, street, cands in items_from(src, rnd):
            n += 1
            rec = pick(street, by_core)
            block, merged = render(n, street, cands, rec, ctx, by_core, merges)
            merged_items += bool(merged)
            blocks.append(block)
            rows.append({"n": n, "round": rnd, "round_n": old_n, "street": street,
                         "score": "no" if (rnd, old_n) in VOID else "yes",
                         "phase_merged": "yes" if merged else "no"})

    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(HEADER + "\n" + "\n\n".join(blocks) + "\n")

    idx = pathlib.Path(a.index)
    with idx.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    chars = len(out.read_text())
    print(f"items: {n}  (round 1: 40, round 2: 200)")
    print(f"items whose peers changed from a phase merge: {merged_items}")
    print(f"items not to score: {sum(1 for r in rows if r['score'] == 'no')}")
    print(f"prompt: {chars:,} chars, roughly {chars // 4:,} tokens")
    print(f"wrote {out}")
    print(f"wrote {idx}")


if __name__ == "__main__":
    main()
