# Ground truth labels

**These files cannot be regenerated.** Everything in `streetymology-data/`
re-downloads from Wikidata or Overpass; these are hours of human judgement by
Allison Pelton and are the basis of every precision figure in the project.
They are version-controlled for that reason.

| file | rows | what it is |
|---|---|---|
| `pass1_review.csv` | 199 | first labelling pass, stratified across all gazetteer domains |
| `pass2_relabel.csv` | 28 | focused re-label of `q` rows that became answerable |
| `labels_merged.csv` | 199 | merged view; pass 2 supersedes pass 1, including changed QIDs |

## Verdict codes

| code | meaning |
|---|---|
| `y` | correct |
| `w` | domain right, specific item wrong |
| `n` | domain wrong |
| `q` | genuinely unsure |

`q` is a real answer, not a failure. Rows the author marked `q` in pass 1 and
later decided were correct only 22% of the time, versus 69.6% for pass-1
decided rows -- human uncertainty strongly predicts incorrectness.

## Provenance

- Pass 1 signal scores were deliberately hidden from the labeller to keep the
  evaluation from being circular.
- `South Blue Hill Lane` was corrected `y` -> `n` by the author after review;
  the change is noted in that row's `notes` field.
- 3 rows in pass 2 were left blank (`North Stanley Creek Avenue`,
  `North Cherry Creek Place`, `West Summit Peak Drive`) and keep their pass-1 `q`.

Regenerate the merged file with `python scripts/merge_labels.py`.
Never hand-edit `labels_merged.csv` -- edit the pass files and re-merge.
