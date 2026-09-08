# Equal ground: the author against a model, same information

Provenance: drafted by Claude from the scorers' output and AP's adjudication
notes. Every figure regenerates from a script named beside it. Not reviewed
prose — rewrite before publishing any of it.

## The method

A street, its subdivision, its neighbouring streets, and a lettered candidate
list with full Wikidata descriptions and aliases. The author and the model get
that same document and answer independently. Neither sees the other's answer
until scoring.

Answers are a letter, `NONE`, or `NOETYM`. Since 2026-09-07 these are decided in
a fixed order, which is what stopped the two abstentions competing:

1. Is there any etymology worth publishing? If not, `NOETYM`, before looking at
   the candidates at all.
2. Only if there is: is the referent among them? A letter, else `NONE`.

`NONE` therefore counts pipeline misses — an answer exists and was not
surfaced. `NOETYM` is a judgement about the street and is independent of what
was offered. Definitions live in `src/streetymology/taxonomy.py`.

**The standing caveat on every accuracy figure below.** There is no ground-truth
key. Disagreements are settled by AP, who is one of the two parties and sees her
own original answer while ruling. These are accuracies *against her considered
second judgement*, not against truth. Her adjudication notes run heavily against
herself — "human missed the theme", "human hallucination!" — so the bias is not
obviously self-serving, but it is not absent either.

## Round 1 — 40 streets, settled 2026-09-04

Raw: **model 35/40, author 29/40.** AP adjudicated all 16 disagreements.

Six of the model's eleven dispute wins were surname or given-name matches she
marked "technically right" and would never publish. Excluding those: **29/34
each — exactly level.**

The entire measured gap was one category, and it was a difference in publishing
policy rather than accuracy. `NONE` was carrying two incompatible meanings. That
is what produced `NOETYM`.

Caveat: the 24 items where both agreed have no ground truth and are scored
correct for both. That is an assumption, not a measurement.

Labels are version-controlled at `data/labels/equal_ground/`. The set cannot be
rebuilt — the builder's dedupe now runs before truncation, so the same seed no
longer reproduces it.

## Round 2 — 200 streets, settled 2026-09-07

None previously labelled. AP labelled all 200; 72 disagreements went to
adjudication and she ruled on 52. Regenerate with
`scripts/score_equal_ground.py --round 2`.

    agreement          128/200 exact, 163/200 publish-or-withhold
    model NOETYM       precision 83%, recall 66% against AP's labels

**On the 52 disagreements she ruled on: model 37/52 (71%), AP 12/52 (23%).**

Aggregate figures — model 92%, human 78% — credit both sides for all 128
undisputed rows and share a floor of 128 correct. They compress the gap and
should not be quoted without that caveat.

Taken at face value, the model is not at parity with the author on this task. It
is better, mostly at noticing subdivision themes she skimmed past. Round 1 said
"level"; round 2, ten times the size and with the abstention defect fixed, does
not.

20 disagreements were left unruled, every one of them `NONE` against `NOETYM`.
That is what forced the ordered rule above; they are being re-ruled under it.

## What the model gets wrong, from AP's notes

Its errors are directional, which is what makes them worth guarding against.

- **It prefers a candidate to abstaining.** On item 166, West Pyramid Peak
  Street, it recognised a Sierra Nevada theme and then took a generic stateless
  mountain as "best available". The correct entity, Q7263270, was not offered;
  the correct answer was to say so.
- **It builds themes from streets in adjacent subdivisions.** Item 68, East
  Chester Lane, drew a British theme from Londoner Way, Parliament Court and
  Dundee Street, none of which share its subdivision.
- **It over-applies specificity to generic words**, demanding a particular
  referent for Humanity and Warbler where the generic term is the answer.

The first of these is the expensive one: it is the failure that publishes a
wrong tag rather than withholding a right one. Twelve of AP's `NOETYM` rows drew
a letter from the model.

## The deterministic arm, on the same truth

Scored against the same adjudicated answers: the gazetteer matcher produced a
match for 11 of 180 items and got **2 of 66 real referents right, against the
model's 63**. Its five apparent wins over the model were silence — no entry, on
items where the answer happened to be `NOETYM`. Retired 2026-09-07; see
`streetymology-data/retired/gazetteer_arm/README.md`.
