# Equal-ground round 1 — ground truth

Human judgement plus the model answers it was compared against. Version
controlled because **none of it can be regenerated.**

| file | rows | what it is |
|---|---|---|
| `equal_ground_labels.csv` | 40 | AP's answers. `choice` is a letter or `NONE` |
| `equal_ground_results.md` | 40 | model answers, from a fresh claude.ai chat |
| `equal_ground_adjudication.csv` | 16 | AP's rulings on the items where the two disagreed |
| `equal_ground_KEY.csv` | 40 | candidate letter → QID. Without it a `choice` of `E` means nothing |

## Why this cannot be rebuilt

`scripts/build_equal_ground.py` no longer produces this set. Candidate dedupe
now runs before truncation to five, so the same seed yields different candidate
lists. The set as labelled exists only here.

The item text AP actually read stays in `streetymology-data/deliverables/
equal_ground.md`, which is deliberately outside the repo.

## Result

Model 35/40, AP 29/40. But six of the model's eleven wins on disputed items were
surname or given-name matches AP marked *"technically right"* and would never
publish. Excluding those six rows: **29/34 each, exactly level.**

The whole measured gap was one category, and it was a difference in publishing
policy rather than in accuracy. That is why round 2 adds a `NOETYM` answer,
distinct from `NONE`, and excludes it from scoring.

## Caveat

There is no ground truth for the 24 items where AP and the model agreed. They
are scored as correct for both, which is an assumption, not a measurement.
