"""Fixed inputs must produce byte-identical output.

A change detector, not a proof of correctness: a failure means the output moved,
go look. No network -- the two fetch stages are outside the chain under test and
`derived/candidates.json` is frozen. What the fixture covers, and what it
deliberately does not, is in `fixture/README.md`.

Re-bless an intended change with:

    export STREETYMOLOGY_DATA_DIR=tests/fixture
    python -m streetymology.build_context
    python -m streetymology.build_batch --out tests/fixture/expected/batch.jsonl
    cp tests/fixture/derived/place_context.json tests/fixture/expected/

`build_batch` reads `derived/place_context.json`, so copy it afterwards, not
before. Read the diff before committing it.
"""
import collections
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
    if moved:
        # Name the fields, not just the count. A re-bless is only safe if the
        # reader can see WHAT moved: a projection change once cut near_unplatted
        # from 16 to 1 and was waved through as "24 places changed".
        fields = collections.Counter(
            f for k in moved for f in want[k] if want[k][f] != got[k].get(f))
        raise AssertionError(
            f"{len(moved)} places changed. Fields: "
            + ", ".join(f"{f} x{n}" for f, n in fields.most_common())
            + f"\nfirst: {moved[:5]}")


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
