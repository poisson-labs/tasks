# What each difficulty level is worth: reading a calibration card

A knob level is a candidate until a model has been run against it. A **calibration card**
says what each level of `depth` and `distractor` is worth to one named model, measured on
generated tasks and printed with its uncertainty, its cost and every setting it depends on.
`poisson_tasks.calibration` computes it; this page explains how to read one, and what the
first one, for `gpt-5-nano`, shows.

Every number on a card is one model's. A card never pools two models or ranks them, and a
level's number for one model says nothing about what it is worth to another.

## How a card is measured

- **Tasks.** Each level (an *arm*, such as `depth:d3`) is run on **S = 60** generated tasks,
  one per seed. The sixty seeds are derived from a fixed string, come from the eval split,
  and are the same at every arm; the artifact publishes them with their hash.
- **Attempts.** Each task gets **n = 5** independent attempts, so a cell (one arm, one
  model) is 300 episodes. The decoding is declared in full and is deliberately not
  deterministic: temperature 1.0, top_p 1.0, `reasoning_effort: low`, a 2,048-token
  completion limit.
- **Harness.** Every episode runs through the verifiers taskset with the `null` harness,
  the same path as the one-line `eval` command in [the verifiers export](verifiers-export.md):
  the model sees the task's prompt and its tool block, and nothing else.
- **Scoring.** The export's own reward: `strict` is 1.0 when the generator's verifier gives
  strict `passed`, and `leaky_pass` is recorded beside it.
- **Stopping.** A run stops on whichever comes first: its token budget, its wall-clock
  limit, or the provider saying the account is out of credit. A stopped run keeps every
  episode already paid for and marks the cell incomplete; it never quietly publishes a
  smaller sample.
- **Resuming.** A run that is interrupted and resumed serves the same tasks, each with its
  full `n` attempts, none run twice and none skipped. It does not reproduce the interrupted
  attempts byte for byte, because the decoding is not deterministic.
- **Staleness.** A card is pinned to the generator hash, which is taken over the bytes of
  `src/poisson_tasks/tasks.py`. When that file changes, the tasks change and the card is
  stale. It is not regenerated automatically; a card whose generator hash differs from the
  installed package's says so.

## The columns

One table per knob, one row per level:

| column | what it means |
|---|---|
| **strict pass@1** | **The headline.** The share of attempts that reached the goal state exactly and then ended with a reply: no stage past the goal, no other record touched. It is the mean over tasks of each task's pass rate, so every task weighs the same. |
| **95% interval** | For strict pass@1, from a bootstrap that resamples *tasks* (each task's five attempts move together), 2,000 resamples at a fixed seed, so the interval recomputes exactly. |
| **leaky pass@1** | Also counts an attempt that reached the goal and then went past it (overshoot) or touched another record (collateral damage). It is a different claim from strict and is printed beside it, so a rate is never read without knowing which one it is. |
| **strict pass@2, pass@5** | The chance that at least one of *k* attempts passes, by the unbiased estimator `1 - C(n-c, k) / C(n, k)` per task. Every *k* up to *n* is in the artifact; the card shows 1, 2 and 5. |
| **min calls** | The fewest tool calls the task can be solved in, known from the task alone: *d* at depth *d*, 2 for every distractor level. |
| **no tool call** | The share of scored episodes that ended without a single tool call. |
| **stopped short** | The share that made at least one call but fewer than the minimum. Disjoint from *no tool call*. Giving up partway through a long chain is a difficulty result, so this is printed and never gated. |
| **saturated** | `yes` when strict pass@1 is at or below 0.05, or at or above 0.95. A saturated level is one this model cannot see past, and it appears in no comparison. |
| **instrument** | Episodes that failed for a reason that is not the model's: `verifier_error`, `replay_mismatch`, `api_error` or `wall_timeout`. They leave the denominator, and they are counted at the moment they happen, so a resumed run cannot hide them. A cell whose instrument rate is above 0.02 is not published. |
| **incomplete** | `yes` when the run stopped on a limit before the cell was full. |

### The no-call refusal

**A cell in which more than 10% of scored episodes made no tool call is not published at
all, and neither is the card that holds it.** Such a cell measures whether the model starts
the task, not how hard the level is. This is not hypothetical: the first card for
`gpt-5-nano` had 72.5% of its episodes end on a first reply asking for the record id and the
entry code, both of which were in the prompt. The prompt was fixed to quote both values,
the refusal was added so the same failure cannot publish again, and the card was re-run.
The tests call this invariant CAL24 (`tests/test_cal_calibration_fix.py`).

### The other tables

- **Control arms** (`depth:d1+h8`, `depth:d2+h5`, `distractor:r0+len(r8)@k16`,
  `distractor:r2+len(r14)@k16`) have their own table. They exist to separate a knob from
  what travels with it (depth from history length, distractors from prompt length); they are
  not difficulty levels and are never read as one. See [knobs and arms](knobs-and-arms.md).
- **Cost per episode** is measured from each episode's own token usage, never estimated.
  Cached and uncached input are kept apart because they are billed at different rates;
  reasoning tokens are already inside the completion tokens and are not added again. Dollars
  are tokens times the rates the run declared, with the date they were read. A model with no
  declared rate, such as one served on your own GPU, has no dollar figure.
- **Adjacent levels** compares each level with the next one up, paired over the shared seeds
  inside each bootstrap resample. A pair is **distinguishable** only when its paired 95%
  interval excludes zero **and** the difference is at least **0.15** pass-rate points, a
  resolution declared before any run. Otherwise it reads *too small for this design to
  call*, with the difference and interval still shown.
- **Ordering** asks whether strict pass@1 is non-increasing across the whole axis. For
  `depth` it also shows leaky pass@1, for the reason under *Model A* below.
- **Provenance** lists everything a number depends on: the package version, the engine,
  generator and vocabulary hashes, the seed list's hash, the harness and verifiers version,
  the model and where it was served (for a locally served model, the serving stack, its
  version and flags, the GPU and the weights' exact revision), the decoding, the budget and
  every threshold above.

## Model A: `gpt-5-nano-2025-08-07`

Run on 2026-09-25 against OpenAI's API: 14 arms × 60 tasks × 5 attempts, **4,200 episodes,
all 4,200 scored, no instrument failure**, about 20 minutes, **about $2.52** by the card's own
cost table. The records and the artifact are in
[`calibration/gpt-5-nano-2025-08-07/`](../calibration/gpt-5-nano-2025-08-07/), and
`python examples/calibration_card.py` rebuilds the artifact from the records, checks it is
byte-identical to the committed one, and prints the whole card. Every figure below is read
from that artifact.

**The no-call refusal passed.** The highest no-call share in any cell was 0.063, on the
control arm `depth:d2+h5`; on the levels themselves it was at most 0.053.

### `depth` works from d1 to d5

| level | strict pass@1 | 95% interval | leaky pass@1 | stopped short |
|---|---|---|---|---|
| `d1` | 0.547 | [0.473, 0.617] | 0.993 | 0.000 |
| `d2` | 0.397 | [0.307, 0.483] | 0.957 | 0.003 |
| `d3` | 0.237 | [0.167, 0.307] | 0.667 | 0.243 |
| `d5` | 0.177 | [0.110, 0.247] | 0.713 | 0.237 |
| `d8` | 0.870 | [0.823, 0.913] | 0.870 | 0.080 |

Strict pass@1 falls at every step from d1 to d5. The first two steps are distinguishable
(d1 to d2: 0.150, paired interval [0.037, 0.267]; d2 to d3: 0.160, [0.073, 0.247]); d3 to d5
(0.060, [-0.030, 0.147]) is too small for this design to call. About a quarter of the d3 and
d5 attempts stopped short of the minimum.

### `d8` cannot overshoot

Strict pass@1 jumps to 0.870 at d8. That is not d8 being easy; it is d8 not being able to
fail the same way. Every depth arm offers the whole eight-stage ladder, so below the top level
the model can carry the record past the goal, and strict fails that as overshoot. At d8 no
stage lies above the goal, which is why strict and leaky are the same number there. Strict at
d1 to d5 therefore includes a *stop at the goal* test that d8 cannot have. Leaky pass@1 is
comparable across the whole axis, and it is not monotone either: 0.993, 0.957, 0.667, 0.713,
0.870. Strict stays the headline.

### The distractor dial does not bite for `gpt-5-nano`

| level | strict pass@1 | 95% interval | leaky pass@1 |
|---|---|---|---|
| `r0` | 0.917 | [0.883, 0.950] | 0.917 |
| `r2` | 0.903 | [0.863, 0.940] | 0.953 |
| `r4` | 0.910 | [0.863, 0.950] | 0.957 |
| `r8` | 0.910 | [0.870, 0.947] | 0.963 |
| `r14` | 0.960 | [0.937, 0.980] | 0.977 |

Strict pass@1 stays between 0.90 and 0.92 from r0 to r8 and rises to 0.960 at r14, which is
saturated and so drops out of every comparison. Every adjacent pair that can be compared is
too small for this design to call. For this model, adding distractor tools to the block does
not make the task harder. Whether it does for a different model is what the second card is
for.

## Model B: `Qwen3-8B`

> **Not run yet. This section is a placeholder and holds no results.**
>
> Model B is an open-weights model from a different family: `Qwen/Qwen3-8B` at revision
> `b968826d9c46dd6066d109eabc6255188de91218`, thinking off, served with vLLM 0.29.0 (FP8,
> 8,192-token context, the `hermes` tool parser) on a Colab L4, through
> [`notebooks/calibration_model_b.ipynb`](../notebooks/calibration_model_b.ipynb). Same seeds,
> same attempts, same decoding as model A. Its card and its reading go here once the run is in.

<!-- MODEL-B: replace the block above with model B's reading, from its committed artifact. -->

## Running a card of your own

Per arm, `calibration.run_arm(spec, output_dir=..., model=..., client=...)` runs one cell
through the verifiers `eval` body, checking the budget before each episode and resuming
from its own output directory if interrupted; `calibration.arm_specs()` lists the fourteen
arms. `calibration.records_from_run` turns a finished run directory into per-episode
records, `calibration.build_artifact` computes every figure from them under a `Provenance`
block, and `calibration.render_document` renders the card. `build_artifact` is where the
refusals above are enforced. [`examples/calibration_card.py`](../examples/calibration_card.py)
shows the last three steps against model A's committed records.

A card costs real model calls: model A's took 4,200 episodes and about $2.52.
