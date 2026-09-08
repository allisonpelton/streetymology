"""Compare naming-plat choices across CLEAN_SHARE thresholds.

`build_place_context.py` picks the plat that named a street: the oldest plat
holding a whole segment cleanly inside it. CLEAN_SHARE decides what "cleanly"
means. This runs the builder at two thresholds into scratch files and reports
where they disagree, so the threshold is chosen from evidence.

Results as of 2026-09-08 are in `docs/naming_plat_threshold.md`. Scratch output
goes to /tmp: it is neither a deliverable nor an artifact worth keeping.
"""
import argparse, json, statistics, subprocess, sys, tempfile
from pathlib import Path

BUILD = Path(__file__).with_name("build_place_context.py")


def build(threshold, tmpdir):
    """Run the context builder at `threshold`, returning the parsed output."""
    name = f"place_context_cmp_{str(threshold).replace('.', '')}.json"
    out = Path(tmpdir) / name
    subprocess.run([sys.executable, str(BUILD), "--clean-share", str(threshold),
                    "--out", str(out)], check=True,
                   stdout=subprocess.DEVNULL)
    return json.loads(out.read_text())


def year(rec):
    return int(rec[:4]) if rec else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--low", type=float, default=0.4)
    ap.add_argument("--high", type=float, default=0.9)
    ap.add_argument("--examples", type=int, default=14)
    a = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        print(f"building at {a.high} and {a.low} ...", flush=True)
        hi, lo = build(a.high, tmp), build(a.low, tmp)

    keys = [k for k, v in hi.items() if v["analysed"]]
    diff = [k for k in keys if hi[k]["naming_plat"] != lo[k]["naming_plat"]]
    print(f"\nanalysed places: {len(keys)}")
    for label, d in ((a.high, hi), (a.low, lo)):
        n = sum(1 for k in keys if d[k]["naming_clean"])
        print(f"  threshold {label}: naming plat from a clean segment "
              f"{n}/{len(keys)} = {n/len(keys):.1%}")
    print(f"  disagreements: {len(diff)} ({len(diff)/len(keys):.1%})")

    older = [k for k in diff
             if (lo[k]["naming_recorded"] or "") < (hi[k]["naming_recorded"] or "")]
    print(f"  the lower threshold picks an OLDER plat in {len(older)}/{len(diff)}")
    if older:
        gaps = [year(hi[k]["naming_recorded"]) - year(lo[k]["naming_recorded"])
                for k in older]
        print(f"  years older: median {statistics.median(gaps):.0f}, max {max(gaps)}")
        pre = sum(1 for k in older if year(lo[k]["naming_recorded"]) < 1950)
        print(f"  moved onto a pre-1950 plat: {pre} ({pre/len(diff):.0%} of changes)")

    print(f"\nwhere the lower threshold hands the name to an old plat holding"
          f" little of the street")
    for k in sorted(older, key=lambda k: lo[k]["naming_share"])[:a.examples]:
        print(f"  {hi[k]['name'][:30]:30s} "
              f"{a.high}-> {hi[k]['naming_plat'][:22]:22s} "
              f"{hi[k]['naming_recorded'][:4]} {hi[k]['naming_share']:.2f}   "
              f"{a.low}-> {lo[k]['naming_plat'][:22]:22s} "
              f"{lo[k]['naming_recorded'][:4]} {lo[k]['naming_share']:.2f}")

    # The higher threshold has its own failure: a plat can hold one segment
    # cleanly and almost none of the rest of the street.
    thin = [k for k in keys if hi[k]["naming_clean"]
            and (hi[k]["naming_share"] or 0) < 0.1]
    print(f"\nat {a.high}, naming plat holds under 10% of the whole street: "
          f"{len(thin)} ({len(thin)/len(keys):.1%})")
    for k in sorted(thin, key=lambda k: hi[k]["naming_share"])[:a.examples]:
        v = hi[k]
        big = max(v["plats"], key=lambda p: p["share"])
        print(f"  {v['name'][:30]:30s} named-> {v['naming_plat'][:22]:22s} "
              f"{v['naming_recorded'][:4]} {v['naming_share']:.2f}   "
              f"largest {big['name'][:22]:22s} {big['recorded'][:4]} {big['share']:.2f}")


if __name__ == "__main__":
    main()
