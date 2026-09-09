"""Rebuild the feasibility prompt with plat-based neighbours instead of landuse ones.

The point is an A/B a person can read. `deliverables/llm_experiment.md` is the
prompt that was pasted into a Sonnet chat, and
`artifacts/llm_experiment_RESULT_sonnet.md` is what came back, with true verdicts
in `artifacts/llm_experiment_KEY.csv`. This script copies that prompt verbatim
and rewrites exactly two lines per item -- the subdivision and the neighbour
list -- from `derived/place_context.json`.

Everything else is held fixed on purpose: same instructions, same items, same
proposed candidate, same wording, same order. So a difference in the answers is
attributable to the neighbours and not to a reworded prompt.

Neighbours are emitted in the trust order build_place_context.py defines --
peers (same naming plat), then attached (a real intersection), then same_plat,
then near unplatted -- rather than alphabetically, so truncation drops the
weakest evidence instead of the end of the alphabet.

same_plat is included on evidence. Dropping it cost West Indus both Pavo and
Lacerta, the two constellations that made the item answerable at all: they sit
in a plat that overlaps Indus's without having named it.

Usage:
  python scripts/build_chat_prompt.py            # writes the prompt, prints a diff summary
  python scripts/build_chat_prompt.py --max-neighbours 25
"""
import argparse
import json
import re

from streetymology.config import data_path, DELIVERABLES_DIR
from streetymology.normalize import key

DIRECTIONALS = ("North", "South", "East", "West")
SRC = DELIVERABLES_DIR / "llm_experiment.md"
OUT_DIR = DELIVERABLES_DIR / "plat_neighbour_test"

ITEM_RE = re.compile(r"^### (\d+)\. (.+)$")


def strip_dir(name):
    """Drop a leading directional. Matches how the original prompt printed names."""
    p = name.split(" ", 1)
    return p[1] if p[0] in DIRECTIONALS and len(p) > 1 else name


def load_context():
    ctx = json.loads(data_path("place_context.json").read_text())
    by_core = {}
    for pid, rec in ctx.items():
        by_core.setdefault(pid.split("#")[0], []).append((pid, rec))
    return ctx, by_core


def pick_place(street, by_core):
    """The place for a full street name. Cores can split across locations."""
    places = by_core.get(key(street))
    if not places:
        return None
    if len(places) == 1:
        return places[0][1]
    exact = [r for _, r in places if r.get("name") == street]
    if len(exact) == 1:
        return exact[0]
    pool = exact or [r for _, r in places]
    return max(pool, key=lambda r: len(r.get("peers", ())))


def neighbours(rec, ctx, cap):
    """Neighbour names in trust order, deduped, capped. Returns (names, truncated)."""
    seen, out = set(), []
    for bucket in ("peers", "attached", "same_plat", "near_unplatted"):
        for pid in rec.get(bucket, ()):
            other = ctx.get(pid)
            if other is None:
                continue
            nm = strip_dir(other.get("name") or other.get("display", ""))
            if nm and nm not in seen:
                seen.add(nm)
                out.append(nm)
    return out[:cap], len(out) > cap


def rewrite(text, ctx, by_core, cap):
    """Replace the subdivision and neighbour lines of every item. Other lines pass through."""
    lines = text.splitlines()
    out, stats = [], []
    street = None
    for line in lines:
        m = ITEM_RE.match(line)
        if m:
            street = m.group(2).strip()
            out.append(line)
            continue
        if street and line.startswith("- **Subdivision:**"):
            rec = pick_place(street, by_core)
            plat = (rec or {}).get("naming_plat") or ""
            out.append(f"- **Subdivision:** {plat or '(none identified)'}")
            continue
        if street and line.startswith("- **Other streets in that subdivision:**"):
            rec = pick_place(street, by_core)
            old = [s.strip() for s in
                   line.split(":**", 1)[1].split(",") if s.strip()]
            if rec is None:
                names, trunc = [], False
            else:
                names, trunc = neighbours(rec, ctx, cap)
            body = ", ".join(names) if names else "(none)"
            if trunc:
                body += " — list truncated"
            out.append(f"- **Nearby street names:** {body}")
            stats.append((street, len(old), len(names),
                          len(set(old) & set(names))))
            street = None
            continue
        out.append(line)
    return "\n".join(out) + "\n", stats


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-neighbours", type=int, default=25,
                    help="cap per item; the original prompt used 25")
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--out", default=str(OUT_DIR / "llm_experiment_plat_neighbours.md"))
    a = ap.parse_args()

    ctx, by_core = load_context()
    text = open(a.src).read()
    new, stats = rewrite(text, ctx, by_core, a.max_neighbours)

    out = __import__("pathlib").Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(new)

    changed = [s for s in stats if s[3] != s[1] or s[1] != s[2]]
    print(f"items rewritten: {len(stats)}")
    print(f"items whose neighbour list changed at all: {len(changed)}")
    if stats:
        kept = sum(s[3] for s in stats)
        oldn = sum(s[1] for s in stats)
        newn = sum(s[2] for s in stats)
        print(f"neighbour names: {oldn} before, {newn} after, {kept} in common")
        empty = [s[0] for s in stats if s[2] == 0]
        if empty:
            print(f"items with no neighbours under the new rule ({len(empty)}): "
                  + ", ".join(empty))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
