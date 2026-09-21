# task-generator

A deterministic generator of tool-use tasks over one mock stateful domain. Each task is
generated together with its verifier, a reference solution, and a set of wrong answers
that are each labelled with the outcome they should earn.

It exists to make a *controlled* measurement possible. Two tasks that differ only in the
one thing you are varying, and a ledger of equalities that refuses the pair when they
differ in anything else.

Generation makes no model calls and no network calls, and is byte-identical across runs,
processes and platforms.

> `task-generator` is a working label, not a name. The repository, the distribution and
> the `task_generator` package all use it until the name is settled; the three URLs in
> `pyproject.toml` are the only other place it appears.

## What is here today

| | |
|---|---|
| the domain engine | **built** -- a pure state machine over a twelve-class ledger |
| the reference tokenizer | **built** -- o200k_base, offline |
| knobs, arms and the pin ledger | **built** -- two knobs, their control arms, thirteen rows |
| task and verifier generation | **built** -- `generate`, `verify`, the outcome vocabulary, the negative controls |
| the Proofload adapter, scripted path | **built** -- runs end to end against Proofload with no model |

## What is not

Say it plainly, because the package installs cleanly either way:

* **The model path is not built.** Nothing here runs a language model. There is no vLLM
  serving stack, no `verifiers` integration and no trace handling, and the `verifiers`
  dependency in `pyproject.toml` is not yet imported by any module. The scripted path
  exercises the instrument with the model taken out of it.
* **The `verifiers` taskset export is not built.** The tasks are not yet emitted in any
  third-party taskset format.
* **Calibration has not been run.** No difficulty level here has been measured against a
  real model, so nothing in this repository tells you what a given depth is worth. The
  levels are candidates.
* **No pilot has been run**, so there are no results to report and none are claimed.

Everything in *What is here today* is covered by the test suite, which is what "built"
means here: 548 tests, and `pytest -q` is the check.

## Install

You need Python 3.11 and a checkout of **Proofload**, which is this project's one
first-party dependency. Proofload is not public yet. Without it, `pip install -e .`
cannot resolve `proofload==0.0.1`, and the first two examples and the tests that do not
touch Proofload are as far as you can get.

From the repository root, with a Proofload checkout at `../proofload`:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e ../proofload
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m task_generator.fetch_encoding
```

The last step fetches the o200k_base encoding file, about 3.6 MB, once. It is **not**
shipped in this repository or in the distribution: its redistribution terms could not be
established, so the fetch reads the URL and the expected digest out of the installed
tiktoken and downloads through tiktoken's own reader, checking the digest before writing.
`NOTICE` sets out what was checked and what was found. Nothing else here touches the
network, and the tokenizer itself never does.

Put `.venv/bin` on `PATH` for anything that shells out to `proofload`:

```bash
export PATH="$PWD/.venv/bin:$PATH"
```

## Quickstart

Generate one task and judge every answer it ships with:

```bash
.venv/bin/python examples/one_task.py
```

It prints the task the model would see, the tool block, the correct solution with the
line the domain returns for each call, and then the verdict on that solution and on each
of the wrong answers the bundle carries:

```
--- the task ---
Advance record able-able-able-answer of the budget ledger.
Stage ladder: review then sample then measure then monitor then compare then bundle then route then label.
Raise that record through measure, and no further.
Open with entry code know; each later stage needs what the stage before returned.

--- the reference solution, and what the domain returns ---
  submit_review_budget({"record_id": "able-able-able-answer", "entry_code": "know"})
    -> '000001 ok           4746de095820d423abc70321a6dd3188'
  submit_sample_budget({"record_id": "able-able-able-answer", "chain_token": "4746de095820d423abc70321a6dd3188"})
    -> '000002 ok           1a7d6b332220792a7a901aaf9bb6823a'
  submit_measure_budget({"record_id": "able-able-able-answer", "chain_token": "1a7d6b332220792a7a901aaf9bb6823a"})
    -> '000003 ok           cdb453268efc01390589bef48f0c6bfe'

--- the verdict on each answer the bundle ships ---
  reference solution         -> passed
  one call short             -> wrong_state
  wrong_state                -> wrong_state
  turn_limit                 -> turn_limit
  collateral_mutation        -> collateral_mutation
  overshoot                  -> overshoot
  malformed_call_clause_2    -> malformed_call (clause 2)
  malformed_call_clause_3    -> malformed_call (clause 3)
  malformed_call_clause_4    -> malformed_call (clause 4)
```

In code, that is:

```python
from task_generator.knobs import ArmSpec
from task_generator.tasks import FormatSpec, Turn, generate, verify

arm = ArmSpec("depth", 3, None, "strict", "eval", "tg-m3-v1")
bundle = generate(arm, seed=7)

turns = tuple(Turn("", (call,), "tool_calls") for call in bundle.reference_calls)
turns += (Turn("Done.", (), "stop"),)

verdict = verify(bundle, turns, True, False, FormatSpec("direct", ()))
assert verdict.label == "passed"
```

Then run the whole scripted path against Proofload, three arms end to end:

```bash
.venv/bin/python examples/proofload_sweep/run.py
```

## Where to go next

* [`examples/`](examples/) -- three runnable examples, smallest first
* [`docs/the-task.md`](docs/the-task.md) -- the domain, what a bundle carries, and the
  outcome vocabulary
* [`docs/knobs-and-arms.md`](docs/knobs-and-arms.md) -- the two knobs, their control
  arms, the turn budget and the pin ledger
* [`gap-log.md`](gap-log.md) -- what is known to be missing or unresolved, and what
  would close each one
* [`NOTICE`](NOTICE) -- every piece of third-party material, what licence it is under,
  and where that was read from

## Development

```bash
.venv/bin/pytest -q          # 548 tests; the Proofload ones drive its real CLI
.venv/bin/mypy               # strict, over src/
.venv/bin/ruff check .
```

The test files are frozen: each module was built against tests written before it, and
the suite is not edited to suit a build. Comments and docstrings in them may be
corrected; assertions may not.

## Licence

MIT, see [`LICENSE`](LICENSE). Third-party material is itemised in [`NOTICE`](NOTICE),
including one file that is deliberately not redistributed here.
