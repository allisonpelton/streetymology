"""Build Wikidata gazetteers.

Serial by design: WDQS allows one client only 60s of processing time per minute.
Rebuilds any domain whose root query has changed since it was last built.
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from streetymology import gazetteer as g

if __name__ == "__main__":
    only = set(a for a in sys.argv[1:] if not a.startswith("-"))
    force = "--force" in sys.argv
    failures = []
    for d in g.ROOTS:
        if only and d not in only:
            continue
        if not force and not g.is_stale(d):
            print(f"{d:18} up to date ({len(g.load(d))})", flush=True); continue
        t0 = time.time()
        try:
            n = g.build(d)
            print(f"{d:18} {n:>7}  [{g.ROOTS[d].tier}/{g.ROOTS[d].precision}]  {time.time()-t0:.0f}s", flush=True)
        except g.GazetteerTooSmall as e:
            failures.append(d); print(f"{d:18} TOO SMALL  {e}", flush=True)
        except Exception as e:
            failures.append(d); print(f"{d:18} FAILED  {str(e)[:110]}", flush=True)
        time.sleep(2)
    if failures:
        print(f"\n{len(failures)} domain(s) need attention: {', '.join(failures)}")
        sys.exit(1)
