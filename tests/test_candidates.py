from streetymology.candidates import publishable, filter_candidates


def test_rejects_bare_personal_names():
    # The exact strings that reached equal-ground round 2 item 47.
    assert not publishable("family name")
    assert not publishable("family")
    assert not publishable("Greiner (surname)")
    assert not publishable("male given name")


def test_rejects_wikimedia_plumbing():
    assert not publishable("Wikimedia disambiguation page")
    assert not publishable("Wikimedia category")


def test_keeps_items_with_no_description():
    """Regression: rejecting these emptied 5 round-2 items and dropped 3 of
    AP's correct answers. Species items are often described only by aliases."""
    assert publishable("")
    assert publishable(None)
    assert publishable("   ")


def test_keeps_real_etymologies():
    assert publishable("suburb of Sydney, New South Wales, Australia")
    assert publishable("species of fish")
    assert publishable("mountain in Idaho, United States of America")
    # "family" as a substring of a real description must survive.
    assert publishable("noble family of Tuscany")
    assert publishable("family of flowering plants")


def test_filter_preserves_order():
    cands = [{"description": "family name"},
             {"description": "mountain in Idaho"},
             {"description": "species of fish"}]
    out = filter_candidates(cands)
    assert [c["description"] for c in out] == ["mountain in Idaho", "species of fish"]
