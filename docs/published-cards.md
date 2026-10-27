# The published cards

Two calibration cards ship inside the package, for `gpt-5-nano` and `Qwen3-8B`. Each says what every level of depth and of the decoy-tools dial was worth to that model, measured on the same 60 tasks per level with 5 attempts at each. This page says what they show and where the two models agree; [calibration.md](calibration.md) holds both cards in full, every table as the code renders it.

**Neither card is current in this release.** Both were measured on an earlier build of the generator. The generator's source changed after they were measured, to add the knobs the knob probe covers, so the tasks they hold regenerate today with the same text and with other ids (a check in the repository regenerates all 840 tasks of each card and compares them). A card is pinned to the build it was measured on, and says so: `poisson-tasks card --published` rebuilds both from their records, checks each against its stored files byte for byte, and reads each *not current for this install*. For the same reason a card from your own run is not set beside them: `poisson-tasks card --compare published` says so in one line (`the generators differ`). A later release measures them again on the current generator.

The records and the machine-readable cards are in the repository's [`calibration`](https://github.com/poisson-labs/tasks/tree/main/calibration) folder. [reading-a-card.md](reading-a-card.md) says how a card is measured and how to read every column.

## How they were measured

Both cards measured the same 14 arms: depth at 1, 2, 3, 5 and 8, the decoy-tools dial at 0, 2, 4, 8 and 14 decoys in a sixteen-tool block, and the four control arms (`depth:d1+h8`, `depth:d2+h5`, `distractor:r0+len(r8)@k16`, `distractor:r2+len(r14)@k16`). Each arm ran on the same 60 tasks from the eval split, with 5 attempts at each, so a card is 14 × 60 × 5 = 4,200 episodes. The decoding was the same for both (temperature 1.0, top_p 1.0, `reasoning_effort: low`, a 2,048-token completion limit), and every episode ran through verifiers with the `null` harness, which gives the model the task's prompt and its tool block and nothing else.

## `gpt-5-nano-2025-08-07`

Run on 2026-09-25 against OpenAI's API: **4,200 episodes, all 4,200 scored, no instrument failure**, about 20 minutes, **about $2.52** by the card's own cost table. The run had no turn limit; its longest episode was 18 model calls, so the card is what it would be under today's 32-call cap. **The no-call refusal passed:** the highest share of episodes that made no tool call, in any cell, was 0.063, on the control arm `depth:d2+h5`; on the levels themselves it was at most 0.053.

Every level, as the card renders it:

- `depth:d1`: gpt-5-nano-2025-08-07 strict pass@1 0.547 [0.473, 0.617], leaky pass@1 0.993, overshoot 0.447, over 60 tasks at 5 attempts each
- `depth:d2`: gpt-5-nano-2025-08-07 strict pass@1 0.397 [0.307, 0.483], leaky pass@1 0.957, overshoot 0.560, over 60 tasks at 5 attempts each
- `depth:d3`: gpt-5-nano-2025-08-07 strict pass@1 0.237 [0.167, 0.307], leaky pass@1 0.667, overshoot 0.427, over 60 tasks at 5 attempts each
- `depth:d5`: gpt-5-nano-2025-08-07 strict pass@1 0.177 [0.110, 0.247], leaky pass@1 0.713, overshoot 0.537, over 60 tasks at 5 attempts each
- `depth:d8`: gpt-5-nano-2025-08-07 strict pass@1 0.870 [0.823, 0.913], leaky pass@1 0.870, overshoot 0.000, over 60 tasks at 5 attempts each
- `distractor:r0@k16`: gpt-5-nano-2025-08-07 strict pass@1 0.917 [0.883, 0.950], leaky pass@1 0.917, overshoot 0.000, over 60 tasks at 5 attempts each
- `distractor:r2@k16`: gpt-5-nano-2025-08-07 strict pass@1 0.903 [0.863, 0.940], leaky pass@1 0.953, overshoot 0.000, over 60 tasks at 5 attempts each
- `distractor:r4@k16`: gpt-5-nano-2025-08-07 strict pass@1 0.910 [0.863, 0.950], leaky pass@1 0.957, overshoot 0.000, over 60 tasks at 5 attempts each
- `distractor:r8@k16`: gpt-5-nano-2025-08-07 strict pass@1 0.910 [0.870, 0.947], leaky pass@1 0.963, overshoot 0.000, over 60 tasks at 5 attempts each
- `distractor:r14@k16`: gpt-5-nano-2025-08-07 strict pass@1 0.960 [0.937, 0.980], leaky pass@1 0.977, overshoot 0.000, over 60 tasks at 5 attempts each

### `depth`: one callable step on reaching, and about half the attempts do not stop

| level | leaky pass@1 | leaky 95% interval | overshoot | strict pass@1 | stopped short |
|---|---|---|---|---|---|
| `d1` | 0.993 | [0.983, 1.000] | 0.447 | 0.547 | 0.000 |
| `d2` | 0.957 | [0.927, 0.980] | 0.560 | 0.397 | 0.003 |
| `d3` | 0.667 | [0.597, 0.730] | 0.427 | 0.237 | 0.243 |
| `d5` | 0.713 | [0.653, 0.770] | 0.537 | 0.177 | 0.237 |
| `d8` | 0.870 | [0.823, 0.913] | 0.000 | 0.870 | 0.080 |

On reaching the goal, reaching falls from 0.957 at d2 to 0.667 at d3, but d2 is at or above the 0.95 saturation bound, so the card leaves that step out, as it does d1 to d2. d3 to d5 is too small for this design to call (a difference of -0.047, paired interval -0.130 to 0.037), and d5 to d8 is distinguishable in the other direction: d8 reaches the goal more often (-0.157, -0.220 to -0.090). So the one step of depth this card can call on reaching the goal runs the wrong way. What stays high is overshoot: between 0.43 and 0.56 of its attempts at d1 to d5 reach the goal and carry the record past it. On strict, which asks for both, pass@1 falls from 0.547 at d1 to 0.177 at d5, and d1 to d2 (0.150) and d2 to d3 (0.160) are distinguishable. About a quarter of the d3 and d5 attempts stopped short of the minimum.

### The decoy-tools dial does not bite for `gpt-5-nano`

Strict pass@1 stays between 0.90 and 0.92 from r0 to r8 and rises to 0.960 at r14, which is saturated and so drops out of every comparison. Every adjacent pair that can be compared is too small for this design to call.

## `Qwen3-8B`

An open-weights model from a different family: `Qwen/Qwen3-8B` at revision `b968826d9c46dd6066d109eabc6255188de91218`, thinking off, served with vLLM 0.29.0 on a Colab L4 through a notebook in the repository ([`notebooks/calibration_model_b.ipynb`](https://github.com/poisson-labs/tasks/blob/main/notebooks/calibration_model_b.ipynb)): FP8 weights, a 16,384-token context, the `hermes` tool parser and vLLM's own sampler. Each episode was capped at 32 model calls. Run on 2026-09-30: **4,200 episodes, all scored, no instrument failure**; the main run took 1.6 hours on the L4. There is no dollar figure: the run cost Colab compute units, not API spend. **No cell came near the no-call refusal:** every attempt made at least one tool call.

Every level, as the card renders it:

- `depth:d1`: Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 strict pass@1 0.000 [0.000, 0.000], leaky pass@1 1.000, overshoot 1.000, over 60 tasks at 5 attempts each
- `depth:d2`: Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 strict pass@1 0.397 [0.300, 0.500], leaky pass@1 1.000, overshoot 0.600, over 60 tasks at 5 attempts each
- `depth:d3`: Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 strict pass@1 0.823 [0.753, 0.890], leaky pass@1 0.993, overshoot 0.170, over 60 tasks at 5 attempts each
- `depth:d5`: Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 strict pass@1 0.860 [0.787, 0.923], leaky pass@1 0.973, overshoot 0.113, over 60 tasks at 5 attempts each
- `depth:d8`: Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 strict pass@1 0.997 [0.990, 1.000], leaky pass@1 0.997, overshoot 0.000, over 60 tasks at 5 attempts each
- `distractor:r0@k16`: Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 strict pass@1 1.000 [1.000, 1.000], leaky pass@1 1.000, overshoot 0.000, over 60 tasks at 5 attempts each
- `distractor:r2@k16`: Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 strict pass@1 0.990 [0.980, 1.000], leaky pass@1 0.997, overshoot 0.000, over 60 tasks at 5 attempts each
- `distractor:r4@k16`: Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 strict pass@1 0.993 [0.983, 1.000], leaky pass@1 1.000, overshoot 0.000, over 60 tasks at 5 attempts each
- `distractor:r8@k16`: Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 strict pass@1 0.980 [0.957, 0.997], leaky pass@1 1.000, overshoot 0.000, over 60 tasks at 5 attempts each
- `distractor:r14@k16`: Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 strict pass@1 0.997 [0.990, 1.000], leaky pass@1 1.000, overshoot 0.000, over 60 tasks at 5 attempts each

### `depth`: reaching is saturated, and stopping improves with depth

| level | leaky pass@1 | leaky 95% interval | overshoot | strict pass@1 | median model calls |
|---|---|---|---|---|---|
| `d1` | 1.000 | [1.000, 1.000] | 1.000 | 0.000 | 9 |
| `d2` | 1.000 | [1.000, 1.000] | 0.600 | 0.397 | 9 |
| `d3` | 0.993 | [0.983, 1.000] | 0.170 | 0.823 | 4 |
| `d5` | 0.973 | [0.930, 1.000] | 0.113 | 0.860 | 6 |
| `d8` | 0.997 | [0.990, 1.000] | 0.000 | 0.997 | 9 |

Qwen reaches the goal at every depth, so every level is saturated on reaching and depth does not order difficulty there at all. What varies is stopping. At d1 all 300 attempts carried the record past the goal, typically all the way up the eight stages (a median of nine model calls on a task that needs one); the higher the goal, the less ladder is left to overshoot, and overshoot falls to 0.113 at d5. So Qwen's strict rate rises with depth: d3 scores 0.427 above d2 (paired interval 0.323 to 0.527), which is distinguishable, the opposite direction to `gpt-5-nano`'s; d3 to d5 (0.037) is too small to call.

### The decoy-tools dial does not bite for Qwen either

Strict pass@1 is between 0.980 and 1.000 at every level from r0 to r14, and every level is saturated, so no difference can be called.

### What the control arms add

The history controls are where Qwen fails to reach the goal at all. Leaky pass@1 is 0.773 for `depth:d1+h8` and 0.733 for `depth:d2+h5`, against 1.000 for plain `d1` and `d2`. These two arms account for 46 of the 49 attempts, out of 4,200, scored `turn_limit` at the 32-call cap. The two decoy-tools controls are saturated at 1.000.

## The two cards together

Both cards were measured on one generator, one seed list and one decoding, so they compare level for level. [calibration.md](calibration.md) lays each pair of adjacent levels side by side, reading agreement from each card's own verdicts: the models agree on a pair only when both call it distinguishable in the same direction.

- **Across the 12 pairs** (depth on reaching the goal, depth on strict, and the decoy-tools dial), they agree on none and disagree on one: depth 2 against 3 on strict, where `gpt-5-nano` falls and Qwen rises. Every other pair is one that at least one card cannot call.
- **On reaching the goal, depth does not order difficulty for either model:** saturated everywhere for Qwen, and for `gpt-5-nano` only the d5 to d8 step is distinguishable, the other way round (its fall from d2 to d3 starts at a saturated level, so it is not called). What depth changes for both is stopping at the goal.
- **The decoy-tools dial does not make tasks harder for either model**, and is experimental.

So a level's worth is one model's, as every card says. Before choosing a level for a model, measure that model.
