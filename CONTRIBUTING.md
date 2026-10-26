# Contributing to Poisson Tasks

This page is for working on the package itself: cloning it, running its tests, and the few rules the repository keeps. If you only want to use it, [the README](README.md) is the page for that.

## How to help

Anyone can open an [issue](https://github.com/poisson-labs/tasks/issues): a bug, a question or an idea. Pull requests come from invited collaborators. To help, open an issue first.

## Set up a checkout

Python 3.11 to 3.13 on macOS or Linux. From a clone:

<!-- docs-check: skip reason="clones the repository and installs the checkout; the job installs the wheel built from the commit" -->
```bash
git clone https://github.com/poisson-labs/tasks.git
cd tasks

python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m poisson_tasks.fetch_encoding
```

The last step fetches the o200k_base encoding file, about 3.6 MB, once. It is not shipped in this repository or in the distribution; [`NOTICE`](NOTICE) records why and what was checked. Generating tasks touches nothing else on the network, and the tokenizer never does.

## Run the tests

<!-- docs-check: skip reason="runs the whole test suite, which needs the checkout and PyPI" -->
```bash
.venv/bin/python -m pytest -q
```

Run it from the repository root. A bare `pytest` collects the same tests: `pyproject.toml` puts the root on the import path, which the tests that import one another need.

The suite needs the network: every test that runs an episode through the `null` harness needs PyPI and astral.sh, because the `verifiers` wheel installs `uv` and the harness's dependencies before each episode ([`tests/conftest.py`](tests/conftest.py) says how). Those tests skip when `uv` is missing, and the CI jobs install it. A run that starts from a background job should leave `SIGINT` at its default.

The tests that need Proofload (the adapter's, and the bridge between the two scorers) are skipped without it, and say so. With a Proofload checkout installed beside this one they run; [docs/proofload.md](docs/proofload.md) shows how.

Type checks and lint, which CI runs too:

<!-- docs-check: skip reason="needs the dev tools of a checkout" -->
```bash
.venv/bin/mypy               # strict, over src/
.venv/bin/mypy --strict src
.venv/bin/ruff check .
```

## The test files are frozen

Each module was built against tests written before it, and the suite is not edited to suit a build. Comments and docstrings in a test file may be corrected; assertions may not. A frozen test that looks wrong is a question for the maintainers, not an edit. [`tests/conftest.py`](tests/conftest.py) is outside that freeze and holds the skip for the tests that need Proofload.

The generator's three source files (`tasks.py`, `surface.py` and `knobs.py`) are frozen until the published cards are measured again: their bytes are in the generator hash, so an edit moves every task id and makes both published cards stale. `engine.py` and the vocabulary table do not change either. What a run records about what produced it is computed in `provenance.py`, which no module in either generator's hash imports, so recording it moves no task. A test regenerates the 840 tasks of each published card, and every knob's kept tasks, and compares them with the recorded ones; it is the first thing to run after touching anything near them.

## Build the wheel

The wheel is built with hatchling from the working tree, and a test builds it and reads its file list. It ships the `poisson-tasks` command, the package's marker for type checkers (`py.typed`), the knob probe's table (`knob_status.json`) and the two published cards (`poisson_tasks/cards/`, mapped from the repository's `calibration/` folder). It does not ship the tokenizer file, the examples or the tests.

<!-- docs-check: skip reason="builds the wheel from a checkout" -->
```bash
.venv/bin/pip wheel . --no-deps --wheel-dir dist
```

## The docs are checked

Every fenced `bash`, `console` and `python` block in the README, in `docs/` and in this file carries a marker on the line before it, and a test fails when one does not. The clean-install job runs the marked blocks from a wheel built from the commit, in file order, in a folder of its own, and compares each block's output with the output block after it. A marker is a comment:

```text
<!-- docs-check: run -->                           run it; it must exit 0
<!-- docs-check: run exit=N -->                    run it; it must exit N (a documented refusal)
<!-- docs-check: run tty answers="1,,,y" -->       run it on a pseudo-terminal, typing the answers
<!-- docs-check: run fixture -->                   a block that would cost money: run it against the
                                                   fixture model, with a made-up key
<!-- docs-check: run fixture env="MODEL,MODEL_BASE_URL,MODEL_API_KEY" -->
                                                   the same, for a block that reads its own variables
<!-- docs-check: output -->                        the block after a run block is its expected output;
                                                   "…" in a line matches any run of characters
<!-- docs-check: skip reason="..." -->             a block that cannot run in CI, with the reason
```

Write a value that varies (a path, a duration, a date) as `…` in the output block, so the page says honestly what varies.

## Words in the docs

The README, `docs/` (but the three standards, `repo-hygiene.md`, `cli-look.md` and `releasing.md`) and `CHANGELOG.md` are for users. They carry no internal identifiers, no decision ids and no names of work sessions; "knob", "arm" and "level" are each explained where they first appear, and a number is shown with its unit. The pin ledger's row ids (`N1` to `N35`) appear only beside their names. A test reads the files with the same pattern the card text is held to.

## Commits and history

Commits are signed and have plain, human-written messages. Devlogs and working notes live outside the repository. [`docs/repo-hygiene.md`](docs/repo-hygiene.md) is the lab's standard for what a public repository holds and never holds, [`docs/cli-look.md`](docs/cli-look.md) is the look every command of the lab's tools keeps, and [`docs/releasing.md`](docs/releasing.md) is the checklist every release follows.
