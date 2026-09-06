"""Fetch skos:altLabel for every gazetteer entity, keyed by QID.

Done as a separate pass because folding an altLabel UNION into the P171*
taxon traversal made every query exceed the WDQS 60s deadline. Batching by QID
is cheap and reliable. Resumable.
"""
import json, time
from streetymology.config import data_path
from streetymology.wikidata import query
from streetymology import gazetteer as g

CHUNK = 250
OUT = data_path(g).ALIAS_FILE

if __name__ == "__main__":
    qids = sorted({r["qid"] for d in g.available() for r in g.load(d)})
    cache = json.loads(OUT.read_text()) if OUT.exists() else {}
    todo = [q for q in qids if q not in cache]
    print(f"{len(qids)} entities, {len(todo)} still to fetch")
    for i in range(0, len(todo), CHUNK):
        batch = todo[i:i + CHUNK]
        sparql = ("SELECT ?s ?a WHERE { VALUES ?s {%s} ?s skos:altLabel ?a "
                  'FILTER(lang(?a)="en") }' % " ".join("wd:" + x for x in batch))
        try:
            for r in query(sparql, timeout=70):
                cache.setdefault(r["s"].rsplit("/", 1)[-1], []).append(r["a"])
        except Exception as e:
            print(f"  chunk {i//CHUNK}: FAILED {str(e)[:60]}"); continue
        for x in batch:
            cache.setdefault(x, [])
        OUT.write_text(json.dumps(cache))
        if (i // CHUNK) % 20 == 0:
            got = sum(1 for v in cache.values() if v)
            print(f"  {i+len(batch)}/{len(todo)}  entities with aliases: {got}", flush=True)
        time.sleep(1)
    print(f"done. {sum(1 for v in cache.values() if v)} of {len(cache)} have aliases -> {OUT}")
