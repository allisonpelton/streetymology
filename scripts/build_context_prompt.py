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

from streetymology.config import DELIVERABLES_DIR
from streetymology.prompt import (HEADER, keep_candidates, load_context,
                                  load_merges, pick, render)
from streetymology.normalize import key

R1 = DELIVERABLES_DIR / "equal_ground" / "round1" / "equal_ground.md"
R2 = DELIVERABLES_DIR / "equal_ground" / "round2" / "equal_ground_2.md"
OUT_DIR = DELIVERABLES_DIR / "context_prompt"
VOID = {(2, 152)}          # OSM renamed the street; recorded in CLAUDE.md


def items_from(path, round_n):
    text = pathlib.Path(path).read_text()
    for block in re.split(r"^### ", text, flags=re.M)[1:]:
        head, rest = block.split("\n", 1)
        num, street = head.split(". ", 1)
        raw = [l for l in rest.splitlines()
               if l.startswith("    - **")
               and not re.match(r"\s+- \*\*(NONE|NOETYM)\.", l)]
        cands, dropped = keep_candidates(raw)
        yield round_n, int(num), street.strip(), cands, dropped


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(OUT_DIR / "context_prompt.md"))
    ap.add_argument("--index", default=str(OUT_DIR / "context_prompt_index.csv"))
    a = ap.parse_args()

    merges = load_merges()
    ctx, by_core = load_context()

    rows, blocks, n = [], [], 0
    merged_items = n_dropped = no_cands = 0
    for src, rnd in ((R1, 1), (R2, 2)):
        for _, old_n, street, cands, dropped in items_from(src, rnd):
            n += 1
            rec = pick(street, by_core)
            block, merged = render(n, street, cands, rec, ctx, by_core, merges)
            merged_items += bool(merged)
            n_dropped += dropped
            no_cands += not cands
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
    print(f"bare personal-name candidates dropped: {n_dropped}")
    print(f"items left with no candidate at all: {no_cands}")
    print(f"items not to score: {sum(1 for r in rows if r['score'] == 'no')}")
    print(f"prompt: {chars:,} chars, roughly {chars // 4:,} tokens")
    print(f"wrote {out}")
    print(f"wrote {idx}")


if __name__ == "__main__":
    main()
