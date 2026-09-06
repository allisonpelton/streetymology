# Packaging: why `pip install -e .` replaced 29 copies of a path hack

Written 2026-09-05, when the change was made.

## What was there before

Every script and every test began with a line like this:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from streetymology.config import DATA_DIR

That line existed 29 times: 23 scripts and 6 tests.

## Why the line was needed

When Python runs `import streetymology`, it searches a list of directories held
in `sys.path`. That list contains the directory of the script being run, then
the standard library, then the site-packages directory of the active virtual
environment. It does **not** contain `src/`.

So `from streetymology.config import DATA_DIR` fails from a file in `scripts/`,
because nothing in the search path contains a `streetymology` package. The hack
computes the path to `src/` at runtime and pushes it onto the front of the
search list, so the next import succeeds.

It works. The costs are that it repeats in every entry point, it must run
*before* the first project import (so import order becomes load-bearing, which
linters and formatters will fight you about), and it only helps files that
remember to include it. A notebook, a REPL, or a new script written in a hurry
gets an ImportError that has nothing to do with the bug being chased.

## What replaced it

A `pyproject.toml` at the repo root declaring the project and where its code
lives:

    [build-system]
    requires = ["setuptools>=68"]
    build-backend = "setuptools.build_meta"

    [project]
    name = "streetymology"
    version = "0.1.0"
    requires-python = ">=3.11"
    dependencies = ["requests>=2.32", "pandas>=2.2", ...]

    [tool.setuptools.packages.find]
    where = ["src"]

Then, once:

    pip install -e .

The `-e` is "editable". A normal `pip install` copies your code into
site-packages, so later edits do nothing until you reinstall. An editable
install instead drops a small file into site-packages pointing back at
`src/streetymology`. The import system follows the pointer, so the code that
runs is always the code in your working tree. Edit a file, rerun, see the
change — but now `import streetymology` works from anywhere in the environment:
scripts, tests, a REPL, a notebook.

`src/streetymology/__init__.py` was also added. Its presence is what marks the
directory as a package rather than a loose folder of modules.

## The "src layout" and why it is the recommended one

Code could have lived at `streetymology/` in the repo root instead of
`src/streetymology/`. Putting it under `src/` means the package is **not**
importable just because your shell happens to be in the repo root. That sounds
like a drawback and is actually the point: it forces the tests to import the
*installed* package, the same way a user would. If packaging is misconfigured —
a module that never gets included, say — the tests fail, instead of silently
passing because Python found the files by accident.

## What this does not do

It does not pin versions; that is `requirements.lock` and
`scripts/pin_requirements.py`. It does not publish anything to PyPI. The
`version = "0.1.0"` field is required metadata, not a release.

## If a fresh clone fails to import

Run `pip install -e .` in the virtualenv. That step is now part of setup, where
before it was implicit in every file.

## Learn more

- Python Packaging User Guide, "Packaging Python Projects" —
  https://packaging.python.org/en/latest/tutorials/packaging-projects/
- `pyproject.toml` specification (what each table means) —
  https://packaging.python.org/en/latest/guides/writing-pyproject-toml/
- setuptools on src-layout vs flat-layout —
  https://setuptools.pypa.io/en/latest/userguide/package_discovery.html#src-layout
- Python docs, "The import system" — the authoritative account of `sys.path` —
  https://docs.python.org/3/reference/import.html
- Brett Cannon, "Why you should use `python -m pip`" — useful background on
  environments and why the invocation matters —
  https://snarky.ca/why-you-should-use-python-m-pip/
