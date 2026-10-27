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

At 0.2.1 the suite is 4,444 tests: 4,083 pass and 361 skip on a checkout without Prove. The skipped ones need Prove (the adapter's, and the bridge between the two scorers) and say so. They run with a checkout of Prove installed beside this one, at the commit CI pins, from before Prove's package was renamed from `proofload` to `poisson_prove`: the adapter still imports `proofload`. [docs/proofload.md](docs/proofload.md) shows how.

Type checks and lint, which CI runs too:

<!-- docs-check: skip reason="needs the dev tools of a checkout" -->
```bash
.venv/bin/mypy               # strict, over src/
.venv/bin/mypy --strict src
.venv/bin/ruff check .
```

## The test files are frozen

Each module was built against tests written before it, and the suite is not edited to suit a build. Comments and docstrings in a test file may be corrected; assertions may not. A frozen test that looks wrong is a question for the maintainers, not an edit. When the maintainers rule that a frozen test must change (a docs page added, a literal that named a version), the change is its own commit, says which test and why, and the test's docstring says it was retrofitted and for what; 0.1.0, 0.2.1 and the docs rewrite after it each carried one. [`tests/conftest.py`](tests/conftest.py) is outside that freeze and holds the skip for the tests that need Proofload.

The generator's three source files (`tasks.py`, `surface.py` and `knobs.py`) are frozen until the published cards are measured again: their bytes are in the generator hash, so an edit moves every task id and makes both published cards stale. `engine.py` and the vocabulary table do not change either. What a run records about what produced it is computed in `provenance.py`, which no module in either generator's hash imports, so recording it moves no task. A test regenerates the 840 tasks of each published card, and every knob's kept tasks, and compares them with the recorded ones; it is the first thing to run after touching anything near them.

## Build the wheel

The wheel is built with hatchling from the working tree, and a test builds it and reads its file list. It ships the `poisson-tasks` command, the package's marker for type checkers (`py.typed`), the knob probe's table (`knob_status.json`) and the two published cards (`poisson_tasks/cards/`, mapped from the repository's `calibration/` folder). It does not ship the tokenizer file, the examples or the tests.

<!-- docs-check: skip reason="builds the wheel from a checkout" -->
```bash
.venv/bin/pip wheel . --no-deps --wheel-dir dist
```

## The docs are checked

Every fenced `bash`, `console` and `python` block in the README, in `docs/` and in this file carries a marker on the line before it, and a test fails when one does not. The markers say how each block is checked. A test holds that every marker is well formed and sits on a block. A test runs each command's `--help` and compares it with the help blocks in `docs/commands.md`, and one compares the settings file `init` writes with the TOML block in `docs/config.md`. [`scripts/docs_blocks.py`](scripts/docs_blocks.py) runs every `run` block of the README and `docs/` from the wheel built from the commit, each page in a folder of its own with a HOME of its own and its blocks in file order, and compares each output block with what the block before it printed. CI runs it on every push and pull request, in the fast lane's job without Prove. A marker is a comment:

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

To run the blocks yourself, install a wheel built from your tree in a venv of its own and point the script at it. It runs on the checkout's venv, since it reads the blocks with the marker test's own parser, and puts the checkout's tokenizer file into the wheel's venv when it is not there. The export page's `uv run eval` needs `uv` on the PATH and PyPI.

<!-- docs-check: skip reason="builds and installs a wheel from a checkout, then runs the docs' own blocks" -->
```bash
.venv/bin/pip wheel . --no-deps --wheel-dir dist
python3.11 -m venv <wheel venv>
<wheel venv>/bin/pip install dist/poisson_tasks-*.whl
.venv/bin/python scripts/docs_blocks.py --venv <wheel venv>
```

It prints each block's exit and each output block's lines that differ, and exits 1 when any block did not hold.

## Words in the docs

The README, `docs/` (but the three standards, `repo-hygiene.md`, `cli-look.md` and `releasing.md`) and `CHANGELOG.md` are for users. They carry no internal identifiers, no decision ids and no names of work sessions; "knob", "arm" and "level" are each explained where they first appear, and a number is shown with its unit. The pin ledger's row ids (`N1` to `N35`) appear only beside their names. A test reads the files with the same pattern the card text is held to.

## Notes for maintainers

**The vocabulary and the tool names.** No record-id word is a substring of any tool name the generator makes. The two 256-word lists are checked against the 112 names of the mock domain's own table, and the larger blocks the newer knobs make hold the same (896 distinct names at every knob's top level over forty seeds, checked by hand on 2026-10-26), though the test covers the 112. It was not always so: an earlier vocabulary carried six words that some tool name contains, and four of them (`city`, `disc`, `grad`, `port`) made pin-ledger row N7, which compares the prompt's words with the tool names, refuse a decoy-tools contrast that held the `r14` arm, the one level whose block keeps no read tool at all. The row is measured by substring over the user instruction's tokens, the record id is in the instruction, and the id is an injective function of the task seed, so a seed whose first word was one of the four had no way out. Depth was unaffected at every level. The current vocabulary draws the lists disjoint from every tool name.

**The export's tool server.** `ExportTask.toolsets(config)` returns a fresh `DomainToolset` on every call, because tool servers are launched per rollout and two rollouts of one task must not share a record or a counter. `setup_task` builds the engine state from the task data, `seq_start` included, which is why a depth control's first live observation is not numbered 1. The advertised block is the bundle's as written; FastMCP would otherwise derive a schema of its own from the body's signature. A call that fails its own schema still reaches the engine, because the engine is total and numbers every call: a call refused before the body would leave the live counter trailing a replay of the same calls. The module runs as `__main__` (`python -m poisson_tasks.export`), which is how verifiers launches a task-scoped tool server as a child process.

## Commits and history

Commits are signed and have plain, human-written messages. Devlogs and working notes live outside the repository. [`docs/repo-hygiene.md`](docs/repo-hygiene.md) is the lab's standard for what a public repository holds and never holds, [`docs/cli-look.md`](docs/cli-look.md) is the look every command of the lab's tools keeps (until the suite keeps one copy of it, in Prove), and [`docs/releasing.md`](docs/releasing.md) is the checklist every release follows.
