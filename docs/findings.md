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

## Domain precision is not estimable

High/low precision was assigned by intuition twice and was wrong both times, in
both directions. Measure it.
