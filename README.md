# Poisson Tasks (`poisson-tasks`)

[![Code License: MIT](https://img.shields.io/badge/Code%20License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](pyproject.toml)

A deterministic generator of tool-use tasks over one mock stateful domain. Each task is
generated together with its verifier, a reference solution, and a set of wrong answers
that are each labelled with the outcome they should earn.

Generation makes no model calls and no network calls, and is byte-identical across runs,
processes and platforms.

> The tool is **Poisson Tasks**. The distribution and the importable package are
> `poisson-tasks` and `poisson_tasks`; the repository is `poisson-labs/tasks`, which the
> three URLs in `pyproject.toml` carry.

---

## What It Generates

A task is a request to move one record of a mock ledger up a fixed ladder of stages,
using the tools it is given and nothing else.

- **The domain.** Twelve ledger classes over a shared eight-stage ladder (`review`,
  `sample`, `measure`, `monitor`, `compare`, `bundle`, `route`, `label`), and a block of
  sixteen tools. One call moves one record one stage: the first carries the record's
  `entry_code`, every later one the `chain_token` the previous call returned, so a
  depth-*d* task takes at least *d* calls whatever the model already knows. Every call
  returns one fixed-width line of 52 bytes, and a call that is wrong changes nothing
  [*source:* [`docs/the-task.md`](docs/the-task.md)].
- **The bundle.** `generate(arm, seed)` returns the task and arm ids, the prompts, the
  tool schemas in the order the model sees them, the goal as `(class, record_id, stage)`,
  a reference solution with the domain's reply to every call, negative controls keyed by
  the outcome each should earn, the pin-ledger measurements, and the engine and generator
  hashes.
- **The verdict.** `verify(bundle, turns, ended_with_reply, turn_limit_hit, fmt)` is a
  pure function of those five arguments. The outcome vocabulary is closed and ordered at
  ten labels, first match wins: `verifier_error`, `replay_mismatch`, `api_error`,
  `wall_timeout`, `malformed_call`, `turn_limit`, `overshoot`, `wrong_state`,
  `collateral_mutation`, `passed`. Every episode is judged strict and leaky at once, as
  `strict_label` and `leaky_pass`.
- **The knobs.** `depth` at levels `1, 2, 3, 5, 8` and `distractor` at `0, 2, 4, 8, 14`,
  each with a control arm that answers the obvious objection to it: `depth:d1+h8` is as
  long as `d8` and as deep as `d1`, and `distractor:r0+len(r8)@k16` holds the block's
  token count where `r8` puts it while keeping `r0`'s tools [*source:*
  [`docs/knobs-and-arms.md`](docs/knobs-and-arms.md)].
- **The pin ledger.** Thirteen rows, each an equality across the arms of one contrast,
  measured on the generated bundles. A violated row refuses the contrast before any model
  runs -- except N5, the block's token count, which reports.

---

## What Is Built

| | |
|---|---|
| the domain engine | **built** -- a pure state machine over a twelve-class ledger |
| the reference tokenizer | **built** -- o200k_base, offline |
| knobs, arms and the pin ledger | **built** -- two knobs, their control arms, thirteen rows |
| task and verifier generation | **built** -- `generate`, `verify`, the outcome vocabulary, the negative controls |
| the Proofload adapter, scripted path | **built** -- runs end to end against Proofload with no model, on the optional `proofload` extra |
| the `verifiers` taskset export | **built** -- the task data, the task with its reward, the tool server, and a finite taskset over a declared list of seeds |
| the model path, standalone | **built** -- the taskset id `poisson-tasks` resolves, and `eval` runs the measured harness against an OpenAI-compatible endpoint with no flag |

"Built" means covered by the test suite: **1086 tests**, and `pytest -q` is the check.

---

## What Is Not Built, and What Is Not Claimed

1. **No language model has been run against this repository.** The standalone model path
   is built and tested -- the taskset loads by its id, and `eval` resolves to the measured
   harness in a local subprocess -- but every test drives it against a stub or the `null`
   harness. No number here was produced by a real model.
2. **The pinned serving path is not built.** There is no vLLM serving stack, no serving
   proxy, no forced output and no store mirror, so none of the pilot's controls exist yet.
3. **Calibration has not been run.** No difficulty level here has been measured against a
   real model, so nothing in this repository tells you what a given depth is worth. The
   levels are candidates.
4. **No pilot has been run**, so there are no results to report and none are claimed.

---

## How to Run It

### 1. Environment Setup

Python 3.11, and nothing else is required:

```bash
git clone https://github.com/poisson-labs/tasks.git
cd tasks

python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m poisson_tasks.fetch_encoding
```

The last step fetches the o200k_base encoding file, about 3.6 MB, once. It is not shipped
in this repository or in the distribution; [`NOTICE`](NOTICE) records why and what was
checked. Nothing else here touches the network, and the tokenizer itself never does.

Sanity check:

```bash
.venv/bin/pytest -q
```

**1086 tests, 706 passed and 380 skipped.** The skipped ones are the Proofload adapter's,
and they say so.

### 2. Generate One Task, and Judge Every Answer It Ships With

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
from poisson_tasks.knobs import ArmSpec
from poisson_tasks.tasks import FormatSpec, Turn, generate, verify

arm = ArmSpec("depth", 3, None, "strict", "eval", "tg-m3-v1")
bundle = generate(arm, seed=7)

turns = tuple(Turn("", (call,), "tool_calls") for call in bundle.reference_calls)
turns += (Turn("Done.", (), "stop"),)

verdict = verify(bundle, turns, True, False, FormatSpec("direct", ()))
assert verdict.label == "passed"
```

### 3. Run a Contrast Through the Pin Ledger

```bash
.venv/bin/python examples/a_contrast.py
```

Builds four arms of `depth` and all five of `distractor` at one seed, runs the thirteen
rows over each contrast, and prints which were measured off the bundles, which two could
not be and why, and the one row that reports rather than refuses. Then it builds a
deliberately broken contrast -- two arms generated from different seeds -- and prints the
three rows that catch it.

### 4. The Proofload Route, Optional

Proofload is one of the two routes a generated task can be run down. It is an **optional
extra, not a dependency**, and **Proofload is not publicly available yet**, so the extra
does not resolve from an index: it resolves against a checkout already installed in the
same environment. With one at `../proofload`:

```bash
.venv/bin/pip install -e ../proofload
.venv/bin/pip install -e ".[dev,proofload]"
export PATH="$PWD/.venv/bin:$PATH"
```

The `PATH` line is required: the adapter and its tests shell out to `proofload`. Then:

```bash
.venv/bin/python examples/proofload_sweep/run.py
```

Writes a pre-registration, builds a registry module from it under its own hash, writes a
Proofload sweep spec, and runs three real `proofload sweep` processes -- one per arm --
driven by the reference policy. It then reads the stored episodes back and prints their
outcomes, and runs a `proofload diff` of the two depth arms. Every episode comes back
`passed`, and the depth arms differ in `t`: 2 turns at `d1`, 4 at `d3`. It takes a few
seconds and writes about 80 KB under `examples/proofload_sweep/example-store`, which is
git-ignored.

With the extra installed, `pytest -q` is **1086 passed, 0 skipped**.

Without it, `import poisson_tasks` and every module under it work as they do with it.
Only `poisson_tasks.adapter` needs Proofload, and importing it without the extra raises
a `ModuleNotFoundError` naming the extra.

### 5. Types and Lint

```bash
.venv/bin/mypy               # strict, over src/
.venv/bin/ruff check .
```

---

## Repository Index & Artifacts

- **The instrument:** [`docs/the-task.md`](docs/the-task.md) -- the domain, what a bundle
  carries, and the outcome vocabulary; [`docs/knobs-and-arms.md`](docs/knobs-and-arms.md)
  -- the two knobs, their control arms, the turn budget and the pin ledger.
- **Examples:** [`examples/`](examples/) -- three, smallest first, with
  [`examples/README.md`](examples/README.md) describing each.
- **Known gaps:** [`gap-log.md`](gap-log.md) -- what is missing or unresolved, and what
  would close each one.
- **Standard & hygiene:** [`docs/repo-hygiene.md`](docs/repo-hygiene.md).
- **Third-party material:** [`NOTICE`](NOTICE) -- every piece, its licence, and where that
  was read from, including one file that is deliberately not redistributed here;
  [`LICENSE`](LICENSE).

The test files under [`tests/`](tests/) are frozen: each module was built against tests
written before it, and the suite is not edited to suit a build. Comments and docstrings
in them may be corrected; assertions may not. [`tests/conftest.py`](tests/conftest.py) is
outside that freeze and holds the skip for the Proofload adapter's 313 tests.

---

## Citation

```bibtex
@misc{kolasinski2026poissontasks,
  author = {Kolasinski, Taylor},
  title  = {poisson-tasks: deterministic tool-use tasks, each generated with its verifier},
  year   = {2026},
  howpublished = {\url{https://github.com/poisson-labs/tasks}},
  note   = {Poisson Labs}
}
```

## Licence

MIT. See [`LICENSE`](LICENSE). Third-party material is itemised in [`NOTICE`](NOTICE).
