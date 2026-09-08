"""Paths for one equal-ground round.

Each round owns a folder under `deliverables/equal_ground/` and
`artifacts/equal_ground/`, so a script that defaults to the wrong round cannot
overwrite a finished round's hand-made answers. Before this existed, the
adjudication builder defaulted to round 1's paths while the scorer defaulted to
round 2's.

Filenames keep the historical suffix — round 1 has none, later rounds are
`_N` — so nothing already written to disk had to be renamed.
"""
from streetymology.config import ARTIFACTS_DIR, DELIVERABLES_DIR


def suffix(n):
    """Round 1 files are unsuffixed; every later round carries `_N`."""
    return "" if int(n) == 1 else f"_{int(n)}"


class Round:
    """Every path belonging to round `n`. Creates its folders on construction."""

    def __init__(self, n):
        self.n = int(n)
        self.sfx = suffix(n)
        self.deliverables = DELIVERABLES_DIR / "equal_ground" / f"round{self.n}"
        self.artifacts = ARTIFACTS_DIR / "equal_ground" / f"round{self.n}"
        for d in (self.deliverables, self.artifacts):
            d.mkdir(parents=True, exist_ok=True)

    def _d(self, tail):
        return self.deliverables / f"equal_ground{self.sfx}{tail}"

    @property
    def items(self):
        """The labelling brief handed to human and model alike."""
        return self._d(".md")

    @property
    def labels(self):
        """The author's hand-made answers. Unregenerable. Never written to."""
        return self._d("_labels.csv")

    @property
    def results(self):
        """The model's answers."""
        return self._d("_results.md")

    @property
    def adjudication_csv(self):
        return self._d("_adjudication.csv")

    @property
    def adjudication_md(self):
        return self._d("_adjudication.md")

    @property
    def about(self):
        return self._d(".about.md")

    @property
    def key(self):
        """QID key, in artifacts: machine output, not written for a reader."""
        return self.artifacts / f"equal_ground{self.sfx}_KEY.csv"


def all_label_sheets():
    """Every round's label sheet, so a new round cannot reissue an old street.

    Recursive on purpose: the sheets sit one level down, in per-round folders.
    """
    root = DELIVERABLES_DIR / "equal_ground"
    return sorted(root.rglob("equal_ground*_labels.csv"))


def add_argument(ap, default=2):
    """Standard `--round` flag, so every script names a round the same way."""
    ap.add_argument("--round", type=int, default=default,
                    help="equal-ground round number (default %(default)s)")
