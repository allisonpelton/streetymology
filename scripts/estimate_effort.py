"""Estimate reviewer effort with and without the pipeline.

Rates are measured from AP's actual labelling sessions, not assumed:
  pass 1: 199 rows, ~2h            -> ~36 s/row  (candidates supplied)
  pass 2:  28 rows, ~20 min        -> ~43 s/row  (candidates supplied)
Manual-from-scratch has no measurement, so it is bracketed rather than guessed.
"""
import json
from streetymology.config import data_path
from streetymology import gazetteer as g, match
from streetymology.streets import osm_cores

REVIEW_S = 40          # measured, reviewing a supplied candidate
SCRATCH_LO, SCRATCH_HI = 120, 300     # researching one street unaided
MODEL_ACCEPT = 0.33    # share of candidate-bearing streets the model proposes an entity for
SPOT_CHECK = 0.20      # share of model NONEs still worth a glance

if __name__ == "__main__":
    idx = match.build_indexes(g.available(), g.index)
    cores = osm_cores()
    gaz = sum(1 for k, v in cores.items() if match.match(v, idx, fallback_domains=g.FALLBACK_DOMAINS))
    search = json.loads((data_path("search_unmatched.json")).read_text())
    from streetymology.candidates import publishable
    MEDIA = ("film", "album", "song", "band", "novel", "video game", "tv series")
    srch = sum(1 for k, v in search.items()
               if any(publishable(h.get("description"))
                      and not any(r in (h.get("description") or "").lower() for r in MEDIA)
                      for h in v))
    total = len(cores)
    withc = gaz + srch
    print(f"streets                        {total:>7,}")
    print(f"  with a candidate to judge    {withc:>7,}")
    print(f"  with none at all             {total-withc:>7,}\n")
    lo = total * SCRATCH_LO / 3600
    hi = total * SCRATCH_HI / 3600
    print(f"UNAIDED: research every street")
    print(f"  {SCRATCH_LO//60}-{SCRATCH_HI//60} min each -> {lo:,.0f}-{hi:,.0f} hours "
          f"({lo/6:,.0f}-{hi/6:,.0f} days at 6h/day)\n")
    proposed = withc * MODEL_ACCEPT
    glance = withc * (1 - MODEL_ACCEPT) * SPOT_CHECK
    hours = (proposed * REVIEW_S + glance * 10) / 3600
    print(f"WITH PIPELINE: model proposes, human reviews")
    print(f"  model proposes an entity     {proposed:>7,.0f}  @ {REVIEW_S}s = {proposed*REVIEW_S/3600:,.0f} h")
    print(f"  spot-check {int(SPOT_CHECK*100)}% of NONEs      {glance:>7,.0f}  @ 10s = {glance*10/3600:,.0f} h")
    print(f"  TOTAL                        {hours:>7,.0f} hours ({hours/6:.0f} days at 6h/day)\n")
    print(f"saving: {lo-hours:,.0f}-{hi-hours:,.0f} hours, a factor of {lo/hours:.0f}-{hi/hours:.0f}x")
    print(f"\nmoney: LLM stage costs about $4 on Sonnet, $1.30 on Haiku.")
    print(f"At even $15/h of AP's time, the pipeline pays for itself after "
          f"{4/15*60:.0f} minutes saved.")
