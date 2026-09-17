# Golden-test fixture

One geographic slice of Ada County: the bounding box of the `LUGARNO TERRA` and
`LUGARNO TERRA NORTH` plats, padded by 0.004 degrees, with every OSM way and
every recorded plat that intersects it. 49 ways, 17 plats, 34 core names.

That area was chosen because it exercises the normal path in one readable piece:
a clean single-plat street, a contested one, a street no plat named, the Lugarno
Terra phase merge, and tiers long enough to truncate.

The phase merge is a rule rather than a listed case. `platnames.base_name`
strips the phase marker and `plats.PlatIndex` re-splits a base name by
distance.

`LUGARNO TERRA NORTH` merges into `LUGARNO TERRA` through the directional rule
in `plats._apply_merges`, not through anything in `judgement`. Removing that
rule fails this test for a reason unrelated to the fixture.

`derived/candidates.json` is a **frozen snapshot** of what Wikidata search
returned, after `filter_candidates` ran over it. Neither stage is in the tested
chain, so live Wikidata edits cannot break the test. They also cannot be noticed
by it; that is a data question, not a code question.

`expected/` holds the output the pipeline must reproduce byte for byte. See
`tests/test_pipeline_output.py` for how to re-bless it.
