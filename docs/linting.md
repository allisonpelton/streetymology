# Linting and formatting with ruff — proposal

Written 2026-09-05. **Not yet implemented.** This describes what would be done
and why, so the decision can be made before the diff exists.

## What a linter is

A linter reads source code without running it and reports things that are
probably wrong or probably unwise. It is a static check, like a compiler's
warnings, for a language that does not have a compiler to give them.

Two separate jobs are usually bundled together, and it is worth keeping them
distinct in your head:

- **Linting** — finding likely bugs and dead weight. An unused import. A
  variable assigned and never read. A comparison that is always true. A bare
  `except:` that will swallow a keyboard interrupt.
- **Formatting** — rewriting whitespace, line breaks and quote style to one
  consistent shape. Purely cosmetic, and precisely because it is cosmetic, it
  should be automatic and never argued about.

`ruff` does both. It is a drop-in replacement for the older stack — flake8,
isort, pyupgrade, and largely `black` — and is fast enough (written in Rust)
that running it on this repo is effectively instant.

## Why it matters here, concretely

You said you want it to show code quality. That is a real reason, and there is a
sharper one this week.

Removing the `sys.path` hack left 29 files carrying imports that nothing used
any more — `sys`, `pathlib`, `Path`, and in two files `re` and `collections`. I
found them by hand-rolling a regex pass and then manually verifying nothing
broke. `ruff check --select F401 --fix` does exactly that job, correctly, in
about a second, and would have removed the need to trust my regex.

That is the honest argument for a linter. Not that it makes code beautiful, but
that it mechanises the checks you would otherwise do by eye and get wrong
occasionally.

For a portfolio repo, a reviewer also reads the *presence* of a lint config as a
signal before reading any of your code: it says the author knows the tool exists
and cared enough to configure it.

## What would be added

To `pyproject.toml`:

    [tool.ruff]
    line-length = 88
    target-version = "py311"

    [tool.ruff.lint]
    select = ["E", "F", "I", "UP", "B"]
    ignore = ["E501"]

Those rule families, in plain terms:

| code | family | what it catches |
|------|--------|-----------------|
| `F`  | pyflakes | real errors: unused imports, undefined names, unused variables |
| `E`  | pycodestyle | PEP 8 layout complaints |
| `I`  | isort | import ordering and grouping |
| `UP` | pyupgrade | old idioms that have a cleaner modern form |
| `B`  | bugbear | likely-wrong patterns, e.g. a mutable default argument |

`E501` (line too long) is in `ignore` because the formatter already handles line
length, and leaving both on produces noisy duplicate complaints.

## How it would be introduced

Adopting a linter on an existing codebase has one failure mode: you turn it on,
get four hundred warnings, and learn to ignore all of them. So, in order:

1. `pip install ruff`, added to the `dev` extra in `pyproject.toml`.
2. `ruff check .` — read the report, change nothing yet. This is the honest
   measurement of where the code stands.
3. `ruff check --fix .` — apply only the automatic, safe fixes. Run `pytest`.
   Commit that alone, so the mechanical diff is separable from any judgement
   call.
4. Read whatever is left by hand. Some will be real bugs. Some will be rules
   that do not suit this project, and those get added to `ignore` **with a
   comment saying why** — an unexplained ignore is worse than no linter.
5. `ruff format .` last, as its own commit. It touches nearly every line, so
   mixing it with anything else makes both undiffable.

One notable caveat for this repo: `src/streetymology/llm.py` holds the validated
prompt text, and CLAUDE.md says the measured accept-precision belongs to that
exact string. The formatter must not be allowed to reflow it. Add it to
`[tool.ruff.format] exclude` before step 5.

## What it will not do

It will not tell you whether the code is *correct*, whether the method is sound,
or whether a number is right. It checks form, not truth. A fully lint-clean
repository can still be wrong about everything that matters.

## Learn more

- ruff documentation — https://docs.astral.sh/ruff/
- The full rule list, searchable by code — https://docs.astral.sh/ruff/rules/
- PEP 8, the style guide the `E` rules encode —
  https://peps.python.org/pep-0008/
- "Black code style" — the reasoning behind automatic, non-negotiable
  formatting; ruff's formatter follows it —
  https://black.readthedocs.io/en/stable/the_black_code_style/current_style.html
- pre-commit, if you later want these to run automatically before each commit —
  https://pre-commit.com/
