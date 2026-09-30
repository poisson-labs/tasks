# What each difficulty level is worth: reading a calibration card

A knob level is a candidate until a model has been run against it. A **calibration card**
says what each level of `depth` and `distractor` is worth to one named model, measured on
generated tasks and printed with its uncertainty, its cost and every setting it depends on.
`poisson_tasks.calibration` computes it; this page explains how to read one, and what the
two cards so far, for `gpt-5-nano` and `Qwen3-8B`, show. Both cards in full, and where the
models agree, are on one page: [`calibration.md`](calibration.md).

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
- **Turn limit.** An episode ends after 32 model calls, the taskset's own default (see [the
  verifiers export](verifiers-export.md)). An episode that reaches it is scored `turn_limit`,
  the model's failure, and the card prints the cap in its provenance. Model A's run predates
  the default and had no limit; its longest episode was 18 calls, so its card is what it
  would be under the cap.
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
| **strict pass@1** | First in every table. The share of attempts that reached the goal state exactly and then ended with a reply: no stage past the goal, no other record touched. It is the mean over tasks of each task's pass rate, so every task weighs the same. |
| **95% interval** | For strict pass@1, from a bootstrap that resamples *tasks* (each task's five attempts move together), 2,000 resamples at a fixed seed, so the interval recomputes exactly. |
| **leaky pass@1** | Reaching the goal: also counts an attempt that reached it and then went past it (overshoot) or touched another record (collateral damage). **Depth is read on this rate** (below). |
| **leaky 95% interval** | The same task-resampling bootstrap, on the leaky rate. |
| **overshoot** | Stopping at the goal: the share of scored attempts that reached the goal and carried the record past it. Strict fails these and leaky counts them. |
| **strict pass@2, pass@5** | The chance that at least one of *k* attempts passes, by the unbiased estimator `1 - C(n-c, k) / C(n, k)` per task. Every *k* up to *n* is in the artifact; the card shows 1, 2 and 5. |
| **min calls** | The fewest tool calls the task can be solved in, known from the task alone: *d* at depth *d*, 2 for every distractor level. |
| **no tool call** | The share of scored episodes that ended without a single tool call. |
| **stopped short** | The share that made at least one call but fewer than the minimum. Disjoint from *no tool call*. Giving up partway through a long chain is a difficulty result, so this is printed and never gated. |
| **saturated** | `yes` when strict pass@1 is at or below 0.05, or at or above 0.95. A comparison on a rate leaves out a level saturated on that rate. |
| **instrument** | Episodes that failed for a reason that is not the model's: `verifier_error`, `replay_mismatch`, `api_error` or `wall_timeout`. They leave the denominator, and they are counted at the moment they happen, so a resumed run cannot hide them. A cell whose instrument rate is above 0.02 is not published. |
| **incomplete** | `yes` when the run stopped on a limit before the cell was full. |

### How depth is read

Every depth level offers the whole eight-stage ladder, so below the top level a model can
carry the record past the goal. The strict rate therefore asks two things at once: reach the
goal, and stop there. The two calibrated models do not fail these the same way, so a card
reports them apart. **Depth is read on leaky pass@1, reaching the goal**, compared level by level in
its own table; the overshoot column shows how often the model did not stop. Strict is still
computed, published and compared, and it is first in every table. At d8 no stage lies above
the goal, so nothing can overshoot there and strict equals leaky.

### The no-call refusal

**A cell in which more than 10% of scored episodes made no tool call is not published at
all, and neither is the card that holds it.** Such a cell measures whether the model starts
the task, not how hard the level is. This is not hypothetical: the first card for
`gpt-5-nano` had 72.5% of its episodes end on a first reply asking for the record id and the
entry code, both of which were in the prompt. The prompt was fixed to quote both values,
the refusal was added so the same failure cannot publish again, and the card was re-run.
The tests call this invariant CAL24 (`tests/test_cal_calibration_fix.py`).

### The distractor dial is experimental

On both calibrated models the distractor knob does not make tasks harder (below), so it is
**not a difficulty setting** for current models, and `eval --help` says so beside the arm
option. Its levels stay available and are measured on every card; a redesign that makes
choosing a tool genuinely hard is future work.

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
  call*, with the difference and interval still shown. Depth has one table on leaky
  pass@1, reaching the goal, which is how depth is read, and every knob has one on strict.
- **Ordering** asks whether pass@1 is non-increasing across the whole axis, on strict and,
  for depth, on leaky.
- **Provenance** lists everything a number depends on: the package version, the engine,
  generator and vocabulary hashes, the seed list's hash, the harness and verifiers version,
  the model and where it was served (for a locally served model, the serving stack, its
  version and flags, the GPU and the weights' exact revision), the decoding, the budget, the
  turn limit and every threshold above.

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

### `depth`: one callable step on reaching, and about half the attempts do not stop

| level | leaky pass@1 | leaky 95% interval | overshoot | strict pass@1 | stopped short |
|---|---|---|---|---|---|
| `d1` | 0.993 | [0.983, 1.000] | 0.447 | 0.547 | 0.000 |
| `d2` | 0.957 | [0.927, 0.980] | 0.560 | 0.397 | 0.003 |
| `d3` | 0.667 | [0.597, 0.730] | 0.427 | 0.237 | 0.243 |
| `d5` | 0.713 | [0.653, 0.770] | 0.537 | 0.177 | 0.237 |
| `d8` | 0.870 | [0.823, 0.913] | 0.000 | 0.870 | 0.080 |

On reaching the goal, reaching falls from 0.957 at d2 to 0.667 at d3, but d2 is at or above
the 0.95 saturation bound, so the design leaves that step out, as it does d1 to d2. d3 to d5
is too small for this design to call (a difference of -0.047, paired interval -0.130 to
0.037), and d5 to d8 is distinguishable in the other direction: d8 reaches the goal more
often (-0.157, -0.220 to -0.090). So the one step of depth this card can call on reaching the
goal runs the wrong way. What stays high is overshoot:
between 0.43 and 0.56 of its attempts at d1 to d5 reach the goal and carry the record past
it. On strict, which asks for both, pass@1 falls from 0.547 at d1 to 0.177 at d5, and d1 to
d2 (0.150) and d2 to d3 (0.160) are distinguishable. About a quarter of the d3 and d5
attempts stopped short of the minimum.

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
too small for this design to call.

## Model B: `Qwen3-8B`

An open-weights model from a different family: `Qwen/Qwen3-8B` at revision
`b968826d9c46dd6066d109eabc6255188de91218`, thinking off, served with vLLM 0.29.0 on a Colab
L4 through [`notebooks/calibration_model_b.ipynb`](../notebooks/calibration_model_b.ipynb):
FP8 weights, a 16,384-token context, the `hermes` tool parser and vLLM's own sampler. Same
tasks, seeds, attempts and decoding as model A, each episode capped at 32 model calls. Run on
2026-09-30: **4,200 episodes, all scored, no instrument failure**; phase 3 took 1.6 hours on
the L4. There is no dollar figure: the run cost Colab compute units, not API spend. The records
and the artifact are in
[`calibration/qwen3-8b-b968826d/`](../calibration/qwen3-8b-b968826d/), and
`python examples/calibration_card.py calibration/qwen3-8b-b968826d` rebuilds the artifact,
checks it byte for byte and prints the card.

**No cell came near the no-call refusal:** every attempt made at least one tool call.

### `depth`: reaching is saturated, and stopping improves with depth

| level | leaky pass@1 | leaky 95% interval | overshoot | strict pass@1 | median model calls |
|---|---|---|---|---|---|
| `d1` | 1.000 | [1.000, 1.000] | 1.000 | 0.000 | 9 |
| `d2` | 1.000 | [1.000, 1.000] | 0.600 | 0.397 | 9 |
| `d3` | 0.993 | [0.983, 1.000] | 0.170 | 0.823 | 4 |
| `d5` | 0.973 | [0.930, 1.000] | 0.113 | 0.860 | 6 |
| `d8` | 0.997 | [0.990, 1.000] | 0.000 | 0.997 | 9 |

Qwen reaches the goal at every depth, so every level is saturated on reaching and depth does
not order difficulty there at all. What varies is stopping. At d1 all 300 attempts carried
the record past the goal, typically all the way up the eight stages (a median of nine model
calls on a task that needs one); the higher the goal, the less ladder is left to overshoot,
and overshoot falls to 0.113 at d5. So Qwen's strict rate rises with depth: d3 scores 0.427
above d2 (paired interval 0.323 to 0.527), which is distinguishable, the opposite direction
to model A's; d3 to d5 (0.037) is too small to call.

### The distractor dial does not bite for Qwen either

Strict pass@1 is between 0.980 and 1.000 at every level from r0 to r14, and every level is
saturated, so no difference can be called.

### What the control arms add

The history controls are where Qwen fails to reach the goal at all. Leaky pass@1 is 0.773
for `depth:d1+h8` and 0.733 for `depth:d2+h5`, against 1.000 for plain `d1` and `d2`. These
two arms account for 46 of the 49 attempts, out of 4,200, scored `turn_limit` at the 32-call
cap. The two distractor controls are saturated at 1.000.

## The two cards together

Both cards were measured on one generator (`3a379aa5…`), one seed list and one decoding, so
they compare level for level. [`calibration.md`](calibration.md) lays each pair of adjacent
levels side by side, reading agreement from each card's own verdicts: the models agree on a
pair only when both call it distinguishable in the same direction.

- **Across the 12 pairs** (depth on reaching the goal, depth on strict, and the distractor
  dial), they agree on none and disagree on one: depth 2 against 3 on strict, where
  `gpt-5-nano` falls and Qwen rises. Every other pair is one that at least one card cannot
  call.
- **On reaching the goal, depth does not order difficulty for either model:** saturated
  everywhere for Qwen, and for `gpt-5-nano` only the d5 to d8 step is distinguishable, the
  other way round (its fall from d2 to d3 starts at a saturated level, so it is not called).
  What depth changes for both is stopping at the goal.
- **The distractor dial does not make tasks harder for either model**, and is experimental.

So a level's worth is one model's, as every card says. Before choosing a level for a model,
calibrate that model.

## Running a card of your own

Per arm, `calibration.run_arm(spec, output_dir=..., model=..., client=...)` runs one cell
through the verifiers `eval` body, checking the budget before each episode and resuming
from its own output directory if interrupted; `calibration.arm_specs()` lists the fourteen
arms. `calibration.records_from_run` turns a finished run directory into per-episode
records, `calibration.build_artifact` computes every figure from them under a `Provenance`
block, and `calibration.render_document` renders the card. `build_artifact` is where the
refusals above are enforced. `calibration.render_combined_document` renders one page for
several cards measured the same way, and refuses cards that were not.
[`examples/calibration_card.py`](../examples/calibration_card.py) rebuilds any committed card
from its records under the provenance its run recorded, and `--page` prints the combined page
that [`calibration.md`](calibration.md) is.

A card costs real model calls: model A's took 4,200 episodes and about $2.52.
