"""Build Wikidata gazetteers. Serial by design: WDQS allows one client only
60s of processing time per minute."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from streetymology import gazetteer as g

if __name__ == "__main__":
    only = set(sys.argv[1:])
    for d in g.ROOTS:
        if only and d not in only:
            continue
        if g.path(d).exists() and not only:
            print(f"{d:18} cached ({len(g.load(d))})", flush=True); continue
        t0 = time.time()
        try:
            n = g.build(d)
            print(f"{d:18} {n:>7}  [{g.ROOTS[d].tier}]  {time.time()-t0:.0f}s", flush=True)
        except Exception as e:
            print(f"{d:18} FAILED  {str(e)[:110]}", flush=True)
        time.sleep(2)
