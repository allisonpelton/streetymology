"""End-to-end tripwire: fixed inputs must produce the byte-identical prompt.

This is the only test worth having here. The project is a sequence of
single-purpose stages whose correctness was established by hand -- fifty places
audited for the naming-plat rule, twenty-one phase merges judged one at a time.
A unit test asserting what those already-checked stages currently do would
restate the code, not verify it.

What actually goes wrong is silent drift: a refactor that changes the output
without anyone noticing. Merging three scripts into build_context altered 397
plat names, and the only reason that was caught was a manual byte-diff. This
automates that diff.

Read it as a change detector, not a proof of correctness. A failure means "the
output moved, go look", not "the code is wrong".

No network. `fetch_candidates` is the only stage that talks to Wikidata and it is
deliberately outside the chain under test; `derived/search_unmatched.json` is a
frozen snapshot of what it returned. So live Wikidata edits cannot break this
test, and equally this test can never notice them. Wikidata drift is a data
question, answered by re-fetching and auditing, not by a test.

SCOPE. The fixture is one coherent geographic slice: the Lugarno Terra plats and
everything around them, 49 ways and 17 plats. It covers what a normal run does --
a clean single-plat street, a contested one, a street no plat named, a phase
merge, tiers long enough to truncate, and 17 bare personal-name candidates that
candidates.publishable removes -- so the expected prompt proves the filter works
by not containing them. It deliberately does NOT reach for rare branches. Widening it to hit every code path tripled its size and made the diff
too large to read, which destroys the only thing keeping this test honest.

The fetch stages are not covered at all: mocking their HTTP would test the mock.
The two rules in geo.pretty that the slice happens to miss are asserted directly
at the bottom of this file, because both have already shipped broken once.

RE-BLESSING. When a change to the output is intended:

    export STREETYMOLOGY_DATA_DIR=tests/fixture
    python -m streetymology.build_context
    python -m streetymology.build_batch --out tests/fixture/expected/batch.jsonl
    cp tests/fixture/derived/place_context.json tests/fixture/expected/
    rm tests/fixture/derived/place_context.json tests/fixture/expected/batch.index.csv

Order matters: build_batch reads derived/place_context.json, so copy it to
expected/ afterwards, not before. Read the diff before committing it. Re-blessing
without reading defeats the only safety net in the repo.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixture"
EXPECTED = FIXTURE / "expected"


def run_pipeline(tmp_path):
    """Copy the frozen inputs somewhere writable and run the real stages."""
    for sub in ("raw", "derived"):
        shutil.copytree(FIXTURE / sub, tmp_path / sub)
    env = {**os.environ, "STREETYMOLOGY_DATA_DIR": str(tmp_path)}
    for stage, extra in (("build_context", []),
                         ("build_batch", ["--out", str(tmp_path / "batch.jsonl")])):
        r = subprocess.run([sys.executable, "-m", f"streetymology.{stage}", *extra],
                           env=env, capture_output=True, text=True)
        assert r.returncode == 0, f"{stage} failed:\n{r.stderr}"
    return tmp_path


def test_place_context_is_unchanged(tmp_path):
    out = run_pipeline(tmp_path) / "derived" / "place_context.json"
    got = json.loads(out.read_text())
    want = json.loads((EXPECTED / "place_context.json").read_text())
    assert set(got) == set(want), "the set of places changed"
    moved = sorted(k for k in want if got[k] != want[k])
    assert not moved, f"{len(moved)} places changed, first: {moved[:5]}"


def test_prompt_is_unchanged(tmp_path):
    out = run_pipeline(tmp_path) / "batch.jsonl"
    got = [json.loads(l) for l in out.read_text().splitlines()]
    want = [json.loads(l) for l in (EXPECTED / "batch.jsonl").read_text().splitlines()]
    assert len(got) == len(want), "number of requests changed"
    for g, w in zip(got, want):
        gp = g["params"]["messages"][0]["content"]
        wp = w["params"]["messages"][0]["content"]
        if gp != wp:
            gl, wl = gp.splitlines(), wp.splitlines()
            first = next((i for i, (a, b) in enumerate(zip(gl, wl)) if a != b), 0)
            raise AssertionError(
                f"prompt {g['custom_id']} changed at line {first}:\n"
                f"  expected: {wl[first] if first < len(wl) else '<end>'}\n"
                f"  got:      {gl[first] if first < len(gl) else '<end>'}")


# ---------------------------------------------------------------------------
# Two literal assertions, not snapshots. The fixture slice contains no plat that
# exercises either rule, and both have already reached the prompt broken: plats
# read "Highlands the Unit" and "Elmer Davis 02Nd" for weeks. The names go into
# every prompt and onto the map, and nothing else would catch a change.
# ---------------------------------------------------------------------------

def test_pretty_unpads_and_lowercases_ordinals():
    from streetymology.geo import pretty
    assert pretty("ELMER DAVIS 02ND SUB") == "Elmer Davis 2nd"
    assert pretty("HIDDEN SPRINGS SUB 03RD ADD") == "Hidden Springs 3rd"
    # Kept numeric: this one is a street name, and "Fifty-Second" would be wrong.
    assert pretty("52ND STREET CONDO") == "52nd Street Condo"


def test_pretty_moves_a_stranded_the_to_the_front():
    from streetymology.geo import pretty
    assert pretty("HIGHLANDS THE UNIT NO 01") == "The Highlands"
    assert pretty("EASTMAN THE TRACT") == "The Eastman"
    # THE means what it says here; leave these alone.
    assert pretty("LUCY IN THE SKY") == "Lucy in the Sky"
    assert pretty("LEXINGTON ON THE RIM") == "Lexington on the Rim"
