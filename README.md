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
| the Proofload adapter, scripted path | **built** -- runs end to end against Proofload with no model, on an installed Proofload checkout |
| the `verifiers` taskset export | **built** -- the task data, the task with its reward, the tool server, and a finite taskset over a declared list of seeds |
| the model path, standalone | **built** -- the taskset id `poisson-tasks` resolves, and `eval` runs the measured harness against an OpenAI-compatible endpoint with no flag |
| difficulty calibration | **built** -- pass@k per level with task-clustered intervals, paired level-to-level comparisons, cost, and the refusals that keep a card honest; **run for one model**, `gpt-5-nano` |
| a second model's card | **prepared, not run** -- a Colab notebook that serves `Qwen3-8B` with vLLM on an L4 and runs the same card |

"Built" means covered by the test suite: **1390 tests**, and `python -m pytest -q` is the check.

---

## What Is Not Built, and What Is Not Claimed

1. **One model has been calibrated, not two.** `gpt-5-nano`'s card is in and is summarised
   [below](#what-each-difficulty-level-is-worth). The second, `Qwen3-8B`, is prepared and not
   yet run. Until it is, nothing here says whether a level's difficulty holds across model
   families.
2. **The pilot's pinned serving path is not built.** There is no serving proxy, no forced
   output and no store mirror, so none of the pilot's controls exist yet. The model B
   notebook serves one model with vLLM for calibration only.
3. **No pilot has been run**, so there are no pilot results to report and none are claimed.

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
.venv/bin/python -m pytest -q
```

Run it as `python -m pytest`, from the repository root: one test imports `tests.conftest`,
which needs the root on the import path, and a bare `pytest` does not put it there.

**1390 tests, 1008 passed and 382 skipped.** The skipped ones need Proofload -- the
adapter's tests and the bridge between the two scorers -- and they say so.

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

### 4. Export Tasks in the verifiers Format

`poisson_tasks.export` packages generated tasks as a
[verifiers](https://github.com/willccbb/verifiers) v1 taskset: one task per declared seed,
scored by the generator's own verifier, with the task's tools served over MCP.

```python
import dataclasses
from poisson_tasks.knobs import ArmSpec
from poisson_tasks.export import ExportTaskset, ExportTasksetConfig

arm = ArmSpec(knob="depth", level=3, control=None, strictness="strict",
              split="eval", generator_version="0")
taskset = ExportTaskset(ExportTasksetConfig(arm=dataclasses.asdict(arm), seeds=[404, 55, 2121]))
for task in taskset.load():
    print(task.key, len(task.data.tools))
```

The reward is `strict`, 1.0 exactly when the verifier gives strict `passed`; `leaky_pass`,
`mutation_count`, `sampled_calls` and `turns` are metrics beside it. The package itself is
the taskset id `poisson-tasks`. [`docs/verifiers-export.md`](docs/verifiers-export.md) has the
ten public names, the signals and the tool server.

### 5. Run Them Against a Real Model

One command, against any OpenAI-compatible endpoint serving a model that calls tools. Set
`MODEL`, `MODEL_BASE_URL` and `MODEL_API_KEY`, then:

```bash
uv run eval poisson-tasks --model "$MODEL" --client.base-url "$MODEL_BASE_URL" --client.api-key-var MODEL_API_KEY --env.taskset.arm '{"knob": "depth", "level": 3, "control": null, "strictness": "strict", "split": "eval", "generator_version": "0"}' --env.taskset.seeds 404 55 2121 --no-push
```

It runs three `depth:d3` tasks through the `null` harness -- the model sees the task's
prompt and tool block and nothing else -- in a local subprocess. An episode ends after 32
model calls: a model that never stops is scored `turn_limit` instead of calling tools until
its context runs out, and `--env.agent.max-turns N` changes the cap. `--no-push` keeps the run
local; without it, verifiers pushes the finished run to its hub. Run against OpenAI with
`MODEL=gpt-5-nano`, it served 3 of 3 episodes for about half a cent;
[`docs/verifiers-export.md`](docs/verifiers-export.md) has the output and what to do if a
run goes quiet.

### 6. The Proofload Route, Optional

Proofload is one of the two routes a generated task can be run down. It is an **optional
route, not a dependency**, and **Proofload is not publicly available yet**, so
there is no extra for it and no index to install it from: it comes from a checkout
installed into the same environment. With one at `../proofload`:

```bash
.venv/bin/pip install -e ../proofload
.venv/bin/pip install -e ".[dev]"
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

With Proofload installed, `python -m pytest -q` is **1390 passed, 0 skipped**.

Without it, `import poisson_tasks` and every module under it work as they do with it.
Only `poisson_tasks.adapter` needs Proofload, and importing it without Proofload raises
a `ModuleNotFoundError` saying where it comes from.

### 7. Types and Lint

```bash
.venv/bin/mypy               # strict, over src/
.venv/bin/ruff check .
```

---

## What Each Difficulty Level Is Worth

A level is a candidate until a model has been run against it. A **calibration card** says
what each level of `depth` and `distractor` is worth to one named model: 60 generated tasks
per level from the eval split, 5 independent attempts at each, run through the one-line
`eval` path above with the `null` harness.
[`docs/calibration-guide.md`](docs/calibration-guide.md) explains every column; in brief:

- **strict pass@1** is the headline: the attempt reached the goal state exactly and ended
  with a reply. **leaky pass@1**, beside it, also accepts going past the goal (overshoot) or
  touching another record. Each rate carries a 95% interval that resamples tasks, and
  pass@2 and pass@5 sit beside pass@1.
- **no tool call** is the share of scored attempts that never called a tool, and **stopped
  short** the share that called some tools but fewer than the task's minimum. **A level
  where more than 10% of attempts made no tool call is not published, and neither is its
  card**: it would measure whether the model starts, not how hard the level is. Stopping
  short is a difficulty result and is printed, not gated.
- Two neighbouring levels are **distinguishable** only when their paired interval excludes
  zero *and* they differ by at least 0.15; otherwise the card says the difference is too
  small for this design to call. A level at or below 0.05, or at or above 0.95, is
  **saturated** and left out of every comparison.
- Attempts that failed for a reason that is not the model's (an API error, a timeout) are
  counted apart and leave the denominator. A card is pinned to the generator's hash and says
  so when it is stale.

### Model A: `gpt-5-nano-2025-08-07`

4,200 episodes on 2026-09-25, all scored, no instrument failure, about $2.52. Strict pass@1
per level, with its 95% interval [*source:*
[`calibration/gpt-5-nano-2025-08-07/artifact.json`](calibration/gpt-5-nano-2025-08-07/artifact.json);
`python examples/calibration_card.py` recomputes it from the 4,200 records and prints the
whole card]:

- `depth:d1`: gpt-5-nano-2025-08-07 strict pass@1 0.547 [0.473, 0.617] over 60 tasks at 5 attempts each
- `depth:d2`: gpt-5-nano-2025-08-07 strict pass@1 0.397 [0.307, 0.483] over 60 tasks at 5 attempts each
- `depth:d3`: gpt-5-nano-2025-08-07 strict pass@1 0.237 [0.167, 0.307] over 60 tasks at 5 attempts each
- `depth:d5`: gpt-5-nano-2025-08-07 strict pass@1 0.177 [0.110, 0.247] over 60 tasks at 5 attempts each
- `depth:d8`: gpt-5-nano-2025-08-07 strict pass@1 0.870 [0.823, 0.913] over 60 tasks at 5 attempts each
- `distractor:r0@k16`: gpt-5-nano-2025-08-07 strict pass@1 0.917 [0.883, 0.950] over 60 tasks at 5 attempts each
- `distractor:r2@k16`: gpt-5-nano-2025-08-07 strict pass@1 0.903 [0.863, 0.940] over 60 tasks at 5 attempts each
- `distractor:r4@k16`: gpt-5-nano-2025-08-07 strict pass@1 0.910 [0.863, 0.950] over 60 tasks at 5 attempts each
- `distractor:r8@k16`: gpt-5-nano-2025-08-07 strict pass@1 0.910 [0.870, 0.947] over 60 tasks at 5 attempts each
- `distractor:r14@k16`: gpt-5-nano-2025-08-07 strict pass@1 0.960 [0.937, 0.980] over 60 tasks at 5 attempts each

What it shows:

- **Depth works from d1 to d5.** Strict pass@1 falls at every step, 0.547 to 0.177. The
  steps d1 to d2 and d2 to d3 are distinguishable; d3 to d5 is too small to call.
- **d8 cannot overshoot.** Every depth level offers the whole eight-stage ladder, so below
  d8 an attempt can carry the record past the goal and strict fails it; at d8 nothing lies
  above the goal, and strict equals leaky at 0.870. The jump is that missing failure mode,
  not d8 being easy.
- **The distractor dial does not bite for `gpt-5-nano`.** Strict pass@1 stays between 0.90
  and 0.92 from r0 to r8 and reaches 0.960, saturated, at r14. No adjacent pair is
  distinguishable.

### Model B: `Qwen3-8B`

> **Not run yet. Placeholder: no results.** Model B is `Qwen/Qwen3-8B` at a pinned revision,
> thinking off, served with vLLM on a Colab L4 by
> [`notebooks/calibration_model_b.ipynb`](notebooks/calibration_model_b.ipynb), with the
> same seeds, attempts and decoding as model A. Its card goes here when the run is in.

<!-- MODEL-B: replace the block above with model B's lines and reading, from its committed artifact. -->

---

## Repository Index & Artifacts

- **The instrument:** [`docs/the-task.md`](docs/the-task.md) -- the domain, what a bundle
  carries, and the outcome vocabulary; [`docs/knobs-and-arms.md`](docs/knobs-and-arms.md)
  -- the two knobs, their control arms, the turn budget and the pin ledger.
- **Running it:** [`docs/verifiers-export.md`](docs/verifiers-export.md) -- the verifiers
  taskset, its signals, and the one-line run against a model.
- **Calibration:** [`docs/calibration-guide.md`](docs/calibration-guide.md) -- how to read a
  card, and what model A's shows; [`calibration/`](calibration/) -- each model's per-episode
  records and machine-readable card; [`notebooks/calibration_model_b.ipynb`](notebooks/calibration_model_b.ipynb)
  -- model B's run on a Colab GPU.
- **Examples:** [`examples/`](examples/) -- four, smallest first, with
  [`examples/README.md`](examples/README.md) describing each.
- **Changes:** [`CHANGELOG.md`](CHANGELOG.md).
- **Known gaps:** [`gap-log.md`](gap-log.md) -- what is missing or unresolved, and what
  would close each one.
- **Standard & hygiene:** [`docs/repo-hygiene.md`](docs/repo-hygiene.md).
- **Third-party material:** [`NOTICE`](NOTICE) -- every piece, its licence, and where that
  was read from, including one file that is deliberately not redistributed here;
  [`LICENSE`](LICENSE).

The test files under [`tests/`](tests/) are frozen: each module was built against tests
written before it, and the suite is not edited to suit a build. Comments and docstrings
in them may be corrected; assertions may not. [`tests/conftest.py`](tests/conftest.py) is
outside that freeze and holds the skip for the 382 tests that need Proofload.

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
