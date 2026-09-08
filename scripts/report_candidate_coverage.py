"""How many streets can reach the LLM stage, by candidate source?

The gazetteers were the original route to candidates. `search_unmatched.json`
holds Wikidata search hits for street names the gazetteers missed. If search
alone covers most streets, the gazetteer stage is a stepping stone rather than
the pipeline.
"""
import json

from streetymology import gazetteer as g, match
from streetymology.candidates import publishable
from streetymology.config import data_path
from streetymology.streets import osm_cores


def main():
    cores = osm_cores()
    idx = match.build_indexes(g.available(), g.index)
    search = json.loads(data_path("search_unmatched.json").read_text())
    meta = json.loads(data_path("meta_candidates.json").read_text())

    gaz = set()
    for k, orig in cores.items():
        cs = [c for c in match.match(orig, idx, fallback_domains=g.FALLBACK_DOMAINS)
              if publishable(meta.get(c.qid, {}).get("description", ""))]
        if cs:
            gaz.add(k)

    srch = {k for k, hits in search.items()
            if k in cores and any(publishable(h.get("description")) for h in hits)}

    n = len(cores)
    def line(label, s):
        print(f"  {label:<28} {len(s):5d}  {len(s)/n:5.1%}")

    print(f"{n} unique OSM street cores in Ada County\n")
    line("gazetteer candidates", gaz)
    line("search candidates", srch)
    line("either", gaz | srch)
    line("both", gaz & srch)
    line("search only", srch - gaz)
    line("gazetteer only", gaz - srch)
    line("no candidates at all", set(cores) - gaz - srch)


if __name__ == "__main__":
    main()
