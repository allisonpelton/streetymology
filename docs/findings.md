# Findings — empirical, do not re-derive

Moved out of CLAUDE.md on 2026-09-05 so it is not loaded into context every
session. Each entry cost real labelling effort. Nothing here should be
re-measured without a reason; nothing here should be re-proposed as a new idea.

Provenance: drafted by Claude from measurements in `deliverables/`, reviewed by
the author.

## The main open finding

**The dominant failure mode is "invented", not "wrong item".** 17 author notes
use the word; 15 are `n`, 0 are `y`. Concentrated in `us_river` (7),
`us_mountain` (6), `ski_resort` (2), `us_lake` (2).

These streets have NO referent. "Lake Creek", "Trail Creek" and "Long Lake" are
descriptive names a developer invented, which coincidentally exist as real
features elsewhere in the country. **Better candidate ranking cannot help
them** — the correct answer is not a different item, it is no item. They need an
`invented` output class.

`NOETYM` is the first implementation of that class (2026-09-04). As a labelling
answer it is distinct from `NONE`:

- `NONE` — a referent may exist, but is not among the candidates shown.
- `NOETYM` — the name has no etymology worth publishing at all.

Author's mechanism, verbatim: *"invented confidence goes up for multiple
invented streets"* — **inventedness is a property of a cluster, not of a name.**
A single plausible-looking name cannot be judged alone; its neighbours decide it.

Equal-ground round 2 is the first set to collect `NOETYM`.

## Dead — do not rebuild

- **`specificity` signal** — AUC 0.498, exactly a coin flip.
- **`proximity` as a standalone signal** — AUC 0.414 overall; 0.582 within GNIS
  domains. Decisive test: `North Long Lake Way` was re-shown with the best case
  proximity can offer (Long Lake, Owyhee County, Idaho, 136 km) and the author
  still rejected it — *"too generic of a name, must be invented"*. Proximity
  survives ONLY inside `max(proximity, notability)` (0.794 vs 0.782).
- **surname / given_name gazetteers** — an item that refers to a *name* is not a
  valid etymology; it must refer to a particular individual or family. Nameness
  has also not proven a reliable indicator of validity (AUC 0.568) and may be
  removed entirely. Caveat: 0.568 measured it against "is this candidate the
  right entity", which is not the question it answers. It is a
  no-publishable-etymology detector and should be re-measured against `NOETYM`.

Fuller numbers: `deliverables/signal_evaluation.md`.

## Equal-ground round 1, settled 2026-09-04

40 streets never labelled before, shown to the author and to a model with
**identical information**: neighbour context, full Wikidata descriptions,
aliases.

- Raw: **model 35/40, author 29/40.** The author adjudicated all 16
  disagreements.
- Six of the model's eleven dispute wins were surname or given-name matches the
  author marked *"technically right"* and would never publish. Excluding those:
  **29/34 each — exactly level.**
- **The entire measured gap was one category**, and it was a difference in
  publishing policy, not accuracy. The single `NONE` option was carrying two
  incompatible meanings. This is what produced `NOETYM`.
- Caveat: the 24 items where both agreed have no ground truth and are scored
  correct for both. That is an assumption, not a measurement.

Ground truth is version-controlled at `data/labels/equal_ground/`. It cannot be
rebuilt: the builder's dedupe now runs before truncation, so the same seed no
longer reproduces the set.

## Equal-ground round 2, settled 2026-09-07

200 streets, none previously labelled, drawn from the unmatched pool. AP labelled
all 200; 72 disagreements went to adjudication and she ruled on 52. Regenerate
any figure with `scripts/score_equal_ground.py --round 2`.

Agreement: 128/200 exact, 163/200 publish-or-withhold. Model NOETYM precision
83%, recall 66% against AP's labels.

**Accuracy, on the 52 disagreements she ruled on: model 37/52 (71%), AP 12/52
(23%).** Aggregate accuracy figures (model 92%, human 78%) credit both sides for
all 128 undisputed rows and should not be quoted without that caveat.

**What this means and does not mean.** AP adjudicated disputes in which she was
one of the two parties, with her own answer displayed, so this is accuracy
against her considered second judgement, not against truth. Her notes run
against herself — "human missed the theme" appears repeatedly. Taking it at face
value, the model is not at parity with the author on this task; it is better than
her, mostly at noticing subdivision themes she skimmed past.

20 disagreements were left unruled, all of them NONE vs NOETYM. That boundary is
underspecified in the labelling guide and neither party applies it consistently.

## `nameness` works; it had never been given its own input

Superseded the round-1 verdict. Measured against "is this candidate the right
entity" it scored AUC 0.568 and was on notice for removal. That was the wrong
question: surname matching is a *no-publishable-etymology* detector, not an
entity picker.

The deeper fault was the data. `fetch_metadata.py` feeds `fetch_nameness` the
labels of gazetteer *candidates*, so `meta_nameness.json` only ever covered the
1,395 gazetteer-matched streets. The equal-ground sets are drawn from the
unmatched pool by design, so **3 of 200 round-2 streets had any nameness data at
all**. The signal had never been evaluated on the population it exists to filter.

`scripts/fetch_core_nameness.py` asks the question of the street's own core name.
With that input, on round 2 (`scripts/evaluate_noetym_signals.py --round 2`):

    AUC 0.671 as a NOETYM detector

    nameness  n    NOETYM rate   meaning
       0.0    33      73%        core is both a surname and a given name
       0.2    49      61%        core is one of the two
       1.0    98      34%        core is not a known personal name

Monotonic, against a 48% base rate. As a hard rule, "core is a known personal
name -> NOETYM" gives precision 66%, recall 62%.

Not good enough to publish on alone. Good enough to *withhold* on, and good
enough to drop bare-name candidates from the list shown to the LLM.

## Domain precision is not estimable

High/low precision was assigned by intuition twice and was wrong both times, in
both directions. Measure it.
