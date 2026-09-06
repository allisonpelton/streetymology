"""Keep STREETYMOLOGY_DATA_DIR tidy: every file in a subfolder, nothing loose.

The data directory is working material outside the repo. It accumulates loose
files fast, because most scripts write into it. This sorts them by filename
prefix using the same rules the code reads them back with
(`streetymology.config.data_path`), so organising can never move a file
somewhere the loaders will not look.

    python scripts/organize_data.py           # report only
    python scripts/organize_data.py --apply   # actually move

Files it cannot classify are reported, never guessed at.
"""
import argparse, shutil
from streetymology.config import (
    DATA_DIR, RAW_DIR, GAZ_DIR, DERIVED_DIR, ARTIFACTS_DIR,
    DELIVERABLES_DIR, BUNDLES_DIR, UNUSED_DIR, data_path,
)

KEEP_AT_ROOT = {".keep", "README.md"}
SUBFOLDERS = [RAW_DIR, GAZ_DIR, DERIVED_DIR, ARTIFACTS_DIR,
              DELIVERABLES_DIR, BUNDLES_DIR, UNUSED_DIR]


def classify(path):
    """Where should this file live? None means 'cannot tell'."""
    if path.suffix == ".bundle":
        return BUNDLES_DIR
    dest = data_path(path.name)
    return dest.parent if dest.parent != DATA_DIR else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="move files; default is a dry run")
    a = ap.parse_args()

    loose = [p for p in sorted(DATA_DIR.iterdir())
             if p.is_file() and p.name not in KEEP_AT_ROOT]

    moves, unknown = [], []
    for p in loose:
        home = classify(p)
        (moves if home else unknown).append((p, home))

    for p, home in moves:
        print(f"  {p.name}  ->  {home.name}/")
        if a.apply:
            home.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(home / p.name))

    for p, _ in unknown:
        print(f"  ? {p.name}  -- unclassified, left in place")

    if a.apply:
        print(f"\nmoved {len(moves)} file(s)")
    elif moves:
        print(f"\n{len(moves)} file(s) would move; re-run with --apply")
    else:
        print("\nno loose files")

    if unknown:
        print(f"{len(unknown)} file(s) need a rule in config._HOMES or a manual home")

    print("\ncontents")
    for d in SUBFOLDERS:
        if d.exists():
            n = sum(1 for _ in d.iterdir())
            note = "  <- author can delete these" if d == UNUSED_DIR and n else ""
            print(f"  {d.name + '/':16s} {n:4d} file(s){note}")

    empty = [d for d in SUBFOLDERS if d.exists() and not any(d.iterdir())
             and d not in (UNUSED_DIR, BUNDLES_DIR)]
    for d in empty:
        print(f"  note: {d.name}/ is empty")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
