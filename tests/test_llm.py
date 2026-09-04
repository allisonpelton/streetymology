import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from streetymology.llm import Item, build_prompt, build_requests, parse_table, estimate_cost

ITEM = Item(1, "West Indus Street", "constellation", "Q10406", "Indus",
            "constellation", "", "Fallbrook", ["Pavo Street", "Cold Creek Avenue"])


def test_prompt_states_that_most_names_have_no_etymology():
    """The validated prompt's core instruction; removing it would change results."""
    p = build_prompt([ITEM])
    assert "no etymology at all" in p
    assert "`q` and `n` are valuable answers" in p


def test_prompt_includes_neighbours():
    assert "Pavo Street" in build_prompt([ITEM])


def test_requests_chunk_at_forty():
    reqs = build_requests([ITEM] * 95, chunk=40)
    assert len(reqs) == 3
    assert [len(r["_items"]) for r in reqs] == [40, 40, 15]


def test_bookkeeping_key_is_stripped_from_params():
    r = build_requests([ITEM])[0]
    assert "_items" in r and "_items" not in r["params"]


def test_parse_accepts_prose_around_the_table():
    text = ("Here is my analysis.\n\n"
            "| n | street | verdict | confidence | theme | reasoning |\n"
            "|---|---|---|---|---|---|\n"
            "| 1 | West Indus Street | y | high | constellations | Pavo adjacent |\n"
            "\nHope that helps.")
    out = parse_table(text)
    assert out[1]["verdict"] == "y" and out[1]["confidence"] == "high"


def test_parse_rejects_invalid_verdicts():
    assert parse_table("| 1 | X | maybe | high | t | r |") == {}


def test_cost_estimate_scales_with_items():
    a = estimate_cost(build_requests([ITEM] * 40))
    b = estimate_cost(build_requests([ITEM] * 400))
    assert b["usd_estimate"] > a["usd_estimate"]
