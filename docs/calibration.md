# What each difficulty level is worth

Calibration cards for 2 models, measured the same way: generator `3a379aa5bc4e2bc9e1d2c97357b2dfbcd4bc42e12d64e158fc2af1416c326fd4`, the same 60 tasks from the eval split (seed list `2061672b2321df0981ca56b1d0a2446fe17c59865bd3e47702b214741daca725`), 5 attempts per task, the same decoding, and a difference called only when its paired 95% interval excludes zero and it is at least 0.15. Each model's own card follows in full.

Every number is one model's. This page does not rank models or pool their numbers: it says where their difficulty orderings agree.

Time is each card's own. Seconds depend on the serving and on the run's concurrency as much as on the task, so this page does not compare one card's time with another's.

## Where the models agree

For each pair of adjacent levels, each model's own comparison. The models *agree* when every card calls the pair distinguishable in the same direction, and *disagree* when every card calls it distinguishable but not in one direction. Otherwise at least one card cannot call it (*cannot tell*): a level is saturated for that model, or the difference is too small for this design. A difference is level a minus level b. Depth is read on reaching the goal; the strict comparison also asks the model to stop at the goal.

### depth, on reaching the goal (leaky pass@1)

depth, on reaching the goal (leaky pass@1): the models agree on 0, disagree on 0, and cannot tell on 4, of 4 adjacent pairs.

| levels | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 delta | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 verdict | gpt-5-nano-2025-08-07 delta | gpt-5-nano-2025-08-07 verdict | agreement |
|---|---|---|---|---|---|
| 1 vs 2 | n/a | excluded | n/a | excluded | cannot tell |
| 2 vs 3 | n/a | excluded | n/a | excluded | cannot tell |
| 3 vs 5 | n/a | excluded | -0.047 | too small for this design to call | cannot tell |
| 5 vs 8 | n/a | excluded | -0.157 | distinguishable | cannot tell |

### depth, strict pass@1

depth, strict pass@1: the models agree on 0, disagree on 1, and cannot tell on 3, of 4 adjacent pairs.

| levels | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 delta | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 verdict | gpt-5-nano-2025-08-07 delta | gpt-5-nano-2025-08-07 verdict | agreement |
|---|---|---|---|---|---|
| 1 vs 2 | n/a | excluded | 0.150 | distinguishable | cannot tell |
| 2 vs 3 | -0.427 | distinguishable | 0.160 | distinguishable | disagree |
| 3 vs 5 | -0.037 | too small for this design to call | 0.060 | too small for this design to call | cannot tell |
| 5 vs 8 | n/a | excluded | -0.693 | distinguishable | cannot tell |

### distractor, strict pass@1

distractor, strict pass@1: the models agree on 0, disagree on 0, and cannot tell on 4, of 4 adjacent pairs.

| levels | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 delta | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 verdict | gpt-5-nano-2025-08-07 delta | gpt-5-nano-2025-08-07 verdict | agreement |
|---|---|---|---|---|---|
| 0 vs 2 | n/a | excluded | 0.013 | too small for this design to call | cannot tell |
| 2 vs 4 | n/a | excluded | -0.007 | too small for this design to call | cannot tell |
| 4 vs 8 | n/a | excluded | 0.000 | too small for this design to call | cannot tell |
| 8 vs 14 | n/a | excluded | n/a | excluded | cannot tell |

## Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218

### What each difficulty level is worth

Rendered from the calibration artifact for poisson-tasks 0.0.1 (domain `03ade70a2fb8c7dbd9369fef45f1e3dac9b409b8965cdf79ad372a80a5ab640c`, generator `3a379aa5bc4e2bc9e1d2c97357b2dfbcd4bc42e12d64e158fc2af1416c326fd4`, vocabulary `9f3a8c4f4711574e947ec8b3396ff552c9b7aa730fbb5d565db4f10776653037`), run through the `null` harness at verifiers 0.3.1 over S = 60 seeds from the eval split (seed list `2061672b2321df0981ca56b1d0a2446fe17c59865bd3e47702b214741daca725`) at n = 5 independent attempts per task.

**This card is pinned to the generator hash above and is stale the moment `tasks.py` changes.** It is not regenerated automatically; a card whose generator hash differs from the package's is stale and says so here.

**A resumed run is the same run in this sense and no other.** A run that was interrupted and resumed serves the same tasks, each with its full number of attempts, none run twice and none skipped. It does not reproduce the interrupted attempts byte for byte: the decoding is deliberately not deterministic, so a resumed attempt is a fresh attempt and not an identical copy of the one it replaces.

Every number is one model's. No figure pools or ranks models, and a difference between two levels is printed only under the two-clause rule below.

#### Levels

The **strict** rate is the headline: the episode reached the goal state exactly and ended with a reply. The **leaky** rate beside it also accepts overshoot and collateral damage. They are two different difficulty claims and both are published, so a rate is never read without knowing which one it is. The interval is a task-clustered bootstrap at 2000 resamples (seed 20260922). *min calls* is the structural minimum, which needs no model. *no tool call* is the share of scored episodes that ended without a single tool call, and *stopped short* the share that started and made fewer calls than the minimum; the two are disjoint. A cell whose no-call share is above 0.1 is not published at all, because it would measure whether the model starts rather than the level; stopping short is a difficulty result and is printed, not gated. A saturated level is one this model cannot see past and it appears in no claim below.

*overshoot* is the share of scored episodes that reached the goal and carried the record past it, and the *leaky 95% interval* is the same task-clustered bootstrap on the leaky rate. **Depth is read on leaky pass@1, reaching the goal.** Every depth level offers the whole stage ladder, so below the top level the strict rate also asks the model to stop at the goal; the overshoot column shows how often it did not. The strict rate is published beside it and is first in each table.

Beside the rates is what the level cost: *median model calls*, *median tokens* (prompt, cached input and completion) and *median episode seconds* over the scored episodes. Episode seconds run from the start of the model's work on the task to its end, and a row whose episodes kept no time prints *not recorded*. Seconds belong to the serving and its load as much as to the level; they are printed and decide nothing here.

Concurrency of this run: not recorded.

##### depth

| arm | model | strict pass@1 | 95% interval | leaky pass@1 | leaky 95% interval | overshoot | strict pass@2 | strict pass@5 | median model calls | median tokens | median episode seconds | min calls | no tool call | stopped short | saturated | instrument | incomplete |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `depth:d1` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 0.000 | [0.000, 0.000] | 1.000 | [1.000, 1.000] | 1.000 | 0.000 | 0.000 | 9.000 | 17946.000 | not recorded | 1 | 0.000 | 0.000 | yes | 0 | no |
| `depth:d2` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 0.397 | [0.300, 0.500] | 1.000 | [1.000, 1.000] | 0.600 | 0.505 | 0.617 | 9.000 | 17891.500 | not recorded | 2 | 0.000 | 0.000 | no | 0 | no |
| `depth:d3` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 0.823 | [0.753, 0.890] | 0.993 | [0.983, 1.000] | 0.170 | 0.913 | 0.983 | 4.000 | 6861.000 | not recorded | 3 | 0.000 | 0.003 | no | 0 | no |
| `depth:d5` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 0.860 | [0.787, 0.923] | 0.973 | [0.930, 1.000] | 0.113 | 0.920 | 0.950 | 6.000 | 10962.000 | not recorded | 5 | 0.000 | 0.017 | no | 0 | no |
| `depth:d8` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 0.997 | [0.990, 1.000] | 0.997 | [0.990, 1.000] | 0.000 | 1.000 | 1.000 | 9.000 | 17950.000 | not recorded | 8 | 0.000 | 0.003 | yes | 0 | no |

##### distractor

| arm | model | strict pass@1 | 95% interval | leaky pass@1 | leaky 95% interval | overshoot | strict pass@2 | strict pass@5 | median model calls | median tokens | median episode seconds | min calls | no tool call | stopped short | saturated | instrument | incomplete |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `distractor:r0@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 1.000 | [1.000, 1.000] | 1.000 | [1.000, 1.000] | 0.000 | 1.000 | 1.000 | 3.000 | 4970.000 | not recorded | 2 | 0.000 | 0.000 | yes | 0 | no |
| `distractor:r2@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 0.990 | [0.980, 1.000] | 0.997 | [0.990, 1.000] | 0.000 | 1.000 | 1.000 | 3.000 | 4987.000 | not recorded | 2 | 0.000 | 0.000 | yes | 0 | no |
| `distractor:r4@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 0.993 | [0.983, 1.000] | 1.000 | [1.000, 1.000] | 0.000 | 1.000 | 1.000 | 3.000 | 5000.000 | not recorded | 2 | 0.000 | 0.000 | yes | 0 | no |
| `distractor:r8@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 0.980 | [0.957, 0.997] | 1.000 | [1.000, 1.000] | 0.000 | 0.997 | 1.000 | 3.000 | 5022.000 | not recorded | 2 | 0.000 | 0.000 | yes | 0 | no |
| `distractor:r14@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 0.997 | [0.990, 1.000] | 1.000 | [1.000, 1.000] | 0.000 | 1.000 | 1.000 | 3.000 | 5056.000 | not recorded | 2 | 0.000 | 0.000 | yes | 0 | no |

#### Instrument arms (control arms, not difficulty levels)

These are instrument arms. A control such as `depth:d1+h8` exists to separate depth from history, not to be a difficulty level, and it must not be read as one.

Concurrency of this run: not recorded.

| arm | model | strict pass@1 | 95% interval | leaky pass@1 | leaky 95% interval | overshoot | strict pass@2 | strict pass@5 | median model calls | median tokens | median episode seconds | min calls | no tool call | stopped short | saturated | instrument | incomplete |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `depth:d1+h8` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 0.210 | [0.137, 0.287] | 0.773 | [0.673, 0.863] | 0.563 | 0.307 | 0.417 | 10.000 | 28141.500 | not recorded | 1 | 0.000 | 0.000 | no | 0 | no |
| `depth:d2+h5` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 0.170 | [0.110, 0.240] | 0.733 | [0.637, 0.823] | 0.563 | 0.262 | 0.433 | 9.000 | 20868.000 | not recorded | 2 | 0.000 | 0.100 | no | 0 | no |
| `distractor:r0+len(r8)@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 1.000 | [1.000, 1.000] | 1.000 | [1.000, 1.000] | 0.000 | 1.000 | 1.000 | 3.000 | 5021.000 | not recorded | 2 | 0.000 | 0.000 | yes | 0 | no |
| `distractor:r2+len(r14)@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 1.000 | [1.000, 1.000] | 1.000 | [1.000, 1.000] | 0.000 | 1.000 | 1.000 | 3.000 | 5059.000 | not recorded | 2 | 0.000 | 0.000 | yes | 0 | no |

#### Cost per episode

Measured from each episode's own usage, never estimated. Cached and uncached input are billed at different rates and are kept apart; reasoning tokens are part of the completion tokens and are not added again. Dollars are tokens times the rate read on 2026-09-30; a model with no rate declared has no dollar figure, and a provider-reported cost is printed beside the computed one and never reconciled.

##### Calls and tokens per episode

Over each arm's scored episodes. Tokens are prompt, cached input and completion together. The 90th percentile is the smallest value that at least nine episodes in ten stay at or under. *tokens per strict pass* is the mean tokens divided by strict pass@1, what one strict pass costs at this level, and is n/a where nothing passed.

| arm | model | mean model calls | median model calls | mean tool calls | median tool calls | mean tokens | median tokens | 90th percentile tokens | tokens per strict pass |
|---|---|---|---|---|---|---|---|---|---|
| `depth:d1` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 9.000 | 9.000 | 8.000 | 8.000 | 17943.383 | 17946.000 | 18023 | n/a |
| `depth:d2` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 6.677 | 9.000 | 5.680 | 8.000 | 13057.480 | 17891.500 | 18026 | 32918.017 |
| `depth:d3` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 4.850 | 4.000 | 3.850 | 3.000 | 8746.143 | 6861.000 | 17949 | 10622.846 |
| `depth:d5` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 6.303 | 6.000 | 5.303 | 5.000 | 11678.810 | 10962.000 | 13215 | 13580.012 |
| `depth:d8` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 8.997 | 9.000 | 7.997 | 8.000 | 17941.790 | 17950.000 | 18035 | 18001.796 |
| `depth:d1+h8` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 10.257 | 10.000 | 9.350 | 9.000 | 32614.113 | 28141.500 | 43235 | 155305.302 |
| `depth:d2+h5` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 8.847 | 9.000 | 7.907 | 8.000 | 23145.357 | 20868.000 | 33108 | 136149.157 |
| `distractor:r0@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 3.157 | 3.000 | 2.157 | 2.000 | 5367.643 | 4970.000 | 4988 | 5367.643 |
| `distractor:r2@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 3.207 | 3.000 | 2.210 | 2.000 | 5527.897 | 4987.000 | 5017 | 5583.734 |
| `distractor:r4@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 3.170 | 3.000 | 2.170 | 2.000 | 5360.210 | 5000.000 | 5041 | 5396.185 |
| `distractor:r8@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 3.250 | 3.000 | 2.257 | 2.000 | 5814.643 | 5022.000 | 5055 | 5933.310 |
| `distractor:r14@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 3.017 | 3.000 | 2.017 | 2.000 | 5088.387 | 5056.000 | 5083 | 5105.405 |
| `distractor:r0+len(r8)@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 3.343 | 3.000 | 2.343 | 2.000 | 5984.750 | 5021.000 | 5045 | 5984.750 |
| `distractor:r2+len(r14)@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 3.210 | 3.000 | 2.210 | 2.000 | 5627.360 | 5059.000 | 5107 | 5627.360 |

##### Time per episode

Over each arm's scored episodes that kept time. *episode seconds* run from the start of the model's work on the task to its end; *model seconds* are the part spent waiting on the model and *harness seconds* the rest, the tool calls and the harness between them. *setup seconds* are the tool server's start before the episode: what the instrument costs, not the task. An arm whose episodes kept no time prints *not recorded*; no figure here is a guess or a zero standing in for one.

Time belongs to the serving and its load as much as to the task. It is this run's own, and is not to be compared with another card's unless both were served the same way at the same concurrency.

Concurrency of this run: not recorded.

| arm | model | median episode seconds | 90th percentile episode seconds | median model seconds | 90th percentile model seconds | median harness seconds | 90th percentile harness seconds | median setup seconds |
|---|---|---|---|---|---|---|---|---|
| `depth:d1` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `depth:d2` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `depth:d3` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `depth:d5` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `depth:d8` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `depth:d1+h8` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `depth:d2+h5` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `distractor:r0@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `distractor:r2@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `distractor:r4@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `distractor:r8@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `distractor:r14@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `distractor:r0+len(r8)@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `distractor:r2+len(r14)@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |

##### Token totals and dollars

| arm | model | prompt tokens | cached input tokens | completion tokens | reasoning share | computed $ | reported $ |
|---|---|---|---|---|---|---|---|
| `depth:d1` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 5236049 | 0 | 146966 | 0.000 | n/a | n/a |
| `depth:d2` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 3811976 | 0 | 105268 | 0.000 | n/a | n/a |
| `depth:d3` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 2553925 | 0 | 69918 | 0.000 | n/a | n/a |
| `depth:d5` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 3408345 | 0 | 95298 | 0.000 | n/a | n/a |
| `depth:d8` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 5233657 | 0 | 148880 | 0.000 | n/a | n/a |
| `depth:d1+h8` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 9615899 | 0 | 168335 | 0.000 | n/a | n/a |
| `depth:d2+h5` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 6796393 | 0 | 147214 | 0.000 | n/a | n/a |
| `distractor:r0@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 1571942 | 0 | 38351 | 0.000 | n/a | n/a |
| `distractor:r2@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 1618718 | 0 | 39651 | 0.000 | n/a | n/a |
| `distractor:r4@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 1569058 | 0 | 39005 | 0.000 | n/a | n/a |
| `distractor:r8@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 1703171 | 0 | 41222 | 0.000 | n/a | n/a |
| `distractor:r14@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 1489497 | 0 | 37019 | 0.000 | n/a | n/a |
| `distractor:r0+len(r8)@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 1753329 | 0 | 42096 | 0.000 | n/a | n/a |
| `distractor:r2+len(r14)@k16` | Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | 1648241 | 0 | 39967 | 0.000 | n/a | n/a |

#### Adjacent levels

A difference is paired over the shared seeds inside each resample. A pair is *distinguishable* only when its paired 95% interval excludes zero **and** the difference is at least delta* = 0.15 pass-rate points; otherwise it reads *too small for this design to call*, with its difference and interval shown.

##### depth, on reaching the goal (leaky pass@1)

How depth is read. The same pairing and rule, on the leaky rate, with saturation judged on that rate.

| model | knob | levels | delta leaky pass@1 | 95% paired interval | verdict |
|---|---|---|---|---|---|
| Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | depth | 1 vs 2 | n/a | n/a | excluded: saturated on leaky: depth:d1, depth:d2 |
| Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | depth | 2 vs 3 | n/a | n/a | excluded: saturated on leaky: depth:d2, depth:d3 |
| Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | depth | 3 vs 5 | n/a | n/a | excluded: saturated on leaky: depth:d3, depth:d5 |
| Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | depth | 5 vs 8 | n/a | n/a | excluded: saturated on leaky: depth:d5, depth:d8 |

##### every knob, strict pass@1

| model | knob | levels | delta strict pass@1 | 95% paired interval | verdict |
|---|---|---|---|---|---|
| Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | depth | 1 vs 2 | n/a | n/a | excluded: saturated: depth:d1 |
| Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | depth | 2 vs 3 | -0.427 | [-0.527, -0.323] | distinguishable |
| Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | depth | 3 vs 5 | -0.037 | [-0.140, 0.060] | too small for this design to call |
| Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | depth | 5 vs 8 | n/a | n/a | excluded: saturated: depth:d8 |
| Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | distractor | 0 vs 2 | n/a | n/a | excluded: saturated: distractor:r0@k16, distractor:r2@k16 |
| Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | distractor | 2 vs 4 | n/a | n/a | excluded: saturated: distractor:r2@k16, distractor:r4@k16 |
| Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | distractor | 4 vs 8 | n/a | n/a | excluded: saturated: distractor:r4@k16, distractor:r8@k16 |
| Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 | distractor | 8 vs 14 | n/a | n/a | excluded: saturated: distractor:r8@k16, distractor:r14@k16 |

#### Ordering

- Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218, depth: strict pass@1 across levels [1, 2, 3, 5, 8] is 0.000, 0.397, 0.823, 0.860, 0.997; non-increasing: no.
  - leaky pass@1 across levels [1, 2, 3, 5, 8] is 1.000, 1.000, 0.993, 0.973, 0.997; non-increasing: no.
  - Strict at d1 to d5 includes a stop-at-the-goal test that d8 cannot have: every depth arm offers the whole stage ladder, so below the top level the model can carry the record past the goal (overshoot), and at d8 no stage lies above the goal. Leaky measures reaching the goal at every level and is comparable across the whole axis, so depth is read on leaky, with the overshoot column showing how often the model did not stop at the goal.
- Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218, distractor: strict pass@1 across levels [0, 2, 4, 8, 14] is 1.000, 0.990, 0.993, 0.980, 0.997; non-increasing: no.
  - leaky pass@1 across levels [0, 2, 4, 8, 14] is 1.000, 0.997, 1.000, 1.000, 1.000; non-increasing: no.

#### Provenance

- models: Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218@b968826d9c46dd6066d109eabc6255188de91218 at 127.0.0.1:8000
- decoding: temperature=1.0, top_p=1.0, reasoning_effort=low, max_tokens=2048
- S = 60, n = 5, k on the card: 1, 2, 5; every k up to n is in the artifact
- bootstrap: 2000 resamples, seed 20260922
- delta* = 0.15; saturation at or below 0.05 and at or above 0.95; instrument threshold 0.02; no-call threshold 0.1
- budget: 100000000 tokens, 21600.0 s wall clock, or the provider out of credit, whichever first
- rates read on 2026-09-30
- concurrency: not recorded
- each episode capped at 32 model calls; an episode that reaches the cap ends as `turn_limit`, the model's own failure
- Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 served locally: vllm 0.29.0 on NVIDIA L4, revision b968826d9c46dd6066d109eabc6255188de91218, flags VLLM_USE_FLASHINFER_SAMPLER=0 --revision b968826d9c46dd6066d109eabc6255188de91218 --served-model-name Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218 --quantization fp8 --max-model-len 16384 --enable-auto-tool-choice --tool-call-parser hermes --chat-template <chat template sha256:b4d28698abae82732da6a74bb08a623934fa81b775aea50908246e9fc1323333> --generation-config vllm

## gpt-5-nano-2025-08-07

### What each difficulty level is worth

Rendered from the calibration artifact for poisson-tasks 0.0.1 (domain `03ade70a2fb8c7dbd9369fef45f1e3dac9b409b8965cdf79ad372a80a5ab640c`, generator `3a379aa5bc4e2bc9e1d2c97357b2dfbcd4bc42e12d64e158fc2af1416c326fd4`, vocabulary `9f3a8c4f4711574e947ec8b3396ff552c9b7aa730fbb5d565db4f10776653037`), run through the `null` harness at verifiers 0.3.1 over S = 60 seeds from the eval split (seed list `2061672b2321df0981ca56b1d0a2446fe17c59865bd3e47702b214741daca725`) at n = 5 independent attempts per task.

**This card is pinned to the generator hash above and is stale the moment `tasks.py` changes.** It is not regenerated automatically; a card whose generator hash differs from the package's is stale and says so here.

**A resumed run is the same run in this sense and no other.** A run that was interrupted and resumed serves the same tasks, each with its full number of attempts, none run twice and none skipped. It does not reproduce the interrupted attempts byte for byte: the decoding is deliberately not deterministic, so a resumed attempt is a fresh attempt and not an identical copy of the one it replaces.

Every number is one model's. No figure pools or ranks models, and a difference between two levels is printed only under the two-clause rule below.

#### Levels

The **strict** rate is the headline: the episode reached the goal state exactly and ended with a reply. The **leaky** rate beside it also accepts overshoot and collateral damage. They are two different difficulty claims and both are published, so a rate is never read without knowing which one it is. The interval is a task-clustered bootstrap at 2000 resamples (seed 20260922). *min calls* is the structural minimum, which needs no model. *no tool call* is the share of scored episodes that ended without a single tool call, and *stopped short* the share that started and made fewer calls than the minimum; the two are disjoint. A cell whose no-call share is above 0.1 is not published at all, because it would measure whether the model starts rather than the level; stopping short is a difficulty result and is printed, not gated. A saturated level is one this model cannot see past and it appears in no claim below.

*overshoot* is the share of scored episodes that reached the goal and carried the record past it, and the *leaky 95% interval* is the same task-clustered bootstrap on the leaky rate. **Depth is read on leaky pass@1, reaching the goal.** Every depth level offers the whole stage ladder, so below the top level the strict rate also asks the model to stop at the goal; the overshoot column shows how often it did not. The strict rate is published beside it and is first in each table.

Beside the rates is what the level cost: *median model calls*, *median tokens* (prompt, cached input and completion) and *median episode seconds* over the scored episodes. Episode seconds run from the start of the model's work on the task to its end, and a row whose episodes kept no time prints *not recorded*. Seconds belong to the serving and its load as much as to the level; they are printed and decide nothing here.

Concurrency of this run: not recorded.

##### depth

| arm | model | strict pass@1 | 95% interval | leaky pass@1 | leaky 95% interval | overshoot | strict pass@2 | strict pass@5 | median model calls | median tokens | median episode seconds | min calls | no tool call | stopped short | saturated | instrument | incomplete |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `depth:d1` | gpt-5-nano-2025-08-07 | 0.547 | [0.473, 0.617] | 0.993 | [0.983, 1.000] | 0.447 | 0.757 | 0.950 | 2.000 | 2256.000 | not recorded | 1 | 0.003 | 0.000 | no | 0 | no |
| `depth:d2` | gpt-5-nano-2025-08-07 | 0.397 | [0.307, 0.483] | 0.957 | [0.927, 0.980] | 0.560 | 0.540 | 0.717 | 5.000 | 5638.500 | not recorded | 2 | 0.023 | 0.003 | no | 0 | no |
| `depth:d3` | gpt-5-nano-2025-08-07 | 0.237 | [0.167, 0.307] | 0.667 | [0.597, 0.730] | 0.427 | 0.365 | 0.550 | 5.000 | 5591.000 | not recorded | 3 | 0.023 | 0.243 | no | 0 | no |
| `depth:d5` | gpt-5-nano-2025-08-07 | 0.177 | [0.110, 0.247] | 0.713 | [0.653, 0.770] | 0.537 | 0.267 | 0.433 | 9.000 | 9904.500 | not recorded | 5 | 0.013 | 0.237 | no | 0 | no |
| `depth:d8` | gpt-5-nano-2025-08-07 | 0.870 | [0.823, 0.913] | 0.870 | [0.823, 0.913] | 0.000 | 0.972 | 1.000 | 9.000 | 10141.500 | not recorded | 8 | 0.010 | 0.080 | no | 0 | no |

##### distractor

| arm | model | strict pass@1 | 95% interval | leaky pass@1 | leaky 95% interval | overshoot | strict pass@2 | strict pass@5 | median model calls | median tokens | median episode seconds | min calls | no tool call | stopped short | saturated | instrument | incomplete |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `distractor:r0@k16` | gpt-5-nano-2025-08-07 | 0.917 | [0.883, 0.950] | 0.917 | [0.883, 0.950] | 0.000 | 0.990 | 1.000 | 3.000 | 3378.000 | not recorded | 2 | 0.053 | 0.017 | no | 0 | no |
| `distractor:r2@k16` | gpt-5-nano-2025-08-07 | 0.903 | [0.863, 0.940] | 0.953 | [0.927, 0.977] | 0.000 | 0.983 | 1.000 | 3.000 | 3327.500 | not recorded | 2 | 0.017 | 0.010 | no | 0 | no |
| `distractor:r4@k16` | gpt-5-nano-2025-08-07 | 0.910 | [0.863, 0.950] | 0.957 | [0.917, 0.987] | 0.000 | 0.973 | 1.000 | 3.000 | 3351.000 | not recorded | 2 | 0.003 | 0.007 | no | 0 | no |
| `distractor:r8@k16` | gpt-5-nano-2025-08-07 | 0.910 | [0.870, 0.947] | 0.963 | [0.940, 0.983] | 0.000 | 0.987 | 1.000 | 3.000 | 3361.500 | not recorded | 2 | 0.010 | 0.003 | no | 0 | no |
| `distractor:r14@k16` | gpt-5-nano-2025-08-07 | 0.960 | [0.937, 0.980] | 0.977 | [0.960, 0.990] | 0.000 | 0.998 | 1.000 | 3.000 | 3404.500 | not recorded | 2 | 0.000 | 0.003 | yes | 0 | no |

#### Instrument arms (control arms, not difficulty levels)

These are instrument arms. A control such as `depth:d1+h8` exists to separate depth from history, not to be a difficulty level, and it must not be read as one.

Concurrency of this run: not recorded.

| arm | model | strict pass@1 | 95% interval | leaky pass@1 | leaky 95% interval | overshoot | strict pass@2 | strict pass@5 | median model calls | median tokens | median episode seconds | min calls | no tool call | stopped short | saturated | instrument | incomplete |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `depth:d1+h8` | gpt-5-nano-2025-08-07 | 0.587 | [0.503, 0.663] | 0.940 | [0.903, 0.973] | 0.353 | 0.763 | 0.950 | 2.000 | 3132.000 | not recorded | 1 | 0.033 | 0.000 | no | 0 | no |
| `depth:d2+h5` | gpt-5-nano-2025-08-07 | 0.257 | [0.197, 0.323] | 0.853 | [0.807, 0.897] | 0.597 | 0.418 | 0.650 | 7.000 | 9401.000 | not recorded | 2 | 0.063 | 0.047 | no | 0 | no |
| `distractor:r0+len(r8)@k16` | gpt-5-nano-2025-08-07 | 0.897 | [0.853, 0.937] | 0.897 | [0.853, 0.937] | 0.000 | 0.978 | 1.000 | 3.000 | 3351.500 | not recorded | 2 | 0.053 | 0.037 | no | 0 | no |
| `distractor:r2+len(r14)@k16` | gpt-5-nano-2025-08-07 | 0.860 | [0.813, 0.900] | 0.917 | [0.880, 0.950] | 0.000 | 0.970 | 1.000 | 3.000 | 3565.000 | not recorded | 2 | 0.020 | 0.020 | no | 0 | no |

#### Cost per episode

Measured from each episode's own usage, never estimated. Cached and uncached input are billed at different rates and are kept apart; reasoning tokens are part of the completion tokens and are not added again. Dollars are tokens times the rate read on 2026-09-25; a model with no rate declared has no dollar figure, and a provider-reported cost is printed beside the computed one and never reconciled.

##### Calls and tokens per episode

Over each arm's scored episodes. Tokens are prompt, cached input and completion together. The 90th percentile is the smallest value that at least nine episodes in ten stay at or under. *tokens per strict pass* is the mean tokens divided by strict pass@1, what one strict pass costs at this level, and is n/a where nothing passed.

| arm | model | mean model calls | median model calls | mean tool calls | median tool calls | mean tokens | median tokens | 90th percentile tokens | tokens per strict pass |
|---|---|---|---|---|---|---|---|---|---|
| `depth:d1` | gpt-5-nano-2025-08-07 | 4.243 | 2.000 | 3.243 | 1.000 | 4698.530 | 2256.000 | 10225 | 8594.872 |
| `depth:d2` | gpt-5-nano-2025-08-07 | 5.853 | 5.000 | 4.853 | 4.000 | 6531.833 | 5638.500 | 10394 | 16466.807 |
| `depth:d3` | gpt-5-nano-2025-08-07 | 5.790 | 5.000 | 4.790 | 4.000 | 6633.000 | 5591.000 | 10661 | 28026.761 |
| `depth:d5` | gpt-5-nano-2025-08-07 | 7.117 | 9.000 | 6.117 | 8.000 | 8284.217 | 9904.500 | 12182 | 46891.792 |
| `depth:d8` | gpt-5-nano-2025-08-07 | 8.923 | 9.000 | 7.923 | 8.000 | 10227.837 | 10141.500 | 11937 | 11756.134 |
| `depth:d1+h8` | gpt-5-nano-2025-08-07 | 3.933 | 2.000 | 2.933 | 1.000 | 6307.473 | 3132.000 | 14973 | 10751.375 |
| `depth:d2+h5` | gpt-5-nano-2025-08-07 | 6.427 | 7.000 | 5.427 | 6.000 | 8731.077 | 9401.000 | 12685 | 34017.182 |
| `distractor:r0@k16` | gpt-5-nano-2025-08-07 | 3.413 | 3.000 | 2.413 | 2.000 | 3767.470 | 3378.000 | 5024 | 4109.967 |
| `distractor:r2@k16` | gpt-5-nano-2025-08-07 | 3.300 | 3.000 | 2.300 | 2.000 | 3612.227 | 3327.500 | 4571 | 3998.775 |
| `distractor:r4@k16` | gpt-5-nano-2025-08-07 | 3.373 | 3.000 | 2.373 | 2.000 | 3703.210 | 3351.000 | 4701 | 4069.462 |
| `distractor:r8@k16` | gpt-5-nano-2025-08-07 | 3.367 | 3.000 | 2.367 | 2.000 | 3761.097 | 3361.500 | 4691 | 4133.073 |
| `distractor:r14@k16` | gpt-5-nano-2025-08-07 | 3.370 | 3.000 | 2.370 | 2.000 | 3823.433 | 3404.500 | 5017 | 3982.743 |
| `distractor:r0+len(r8)@k16` | gpt-5-nano-2025-08-07 | 3.363 | 3.000 | 2.363 | 2.000 | 3729.973 | 3351.500 | 5069 | 4159.822 |
| `distractor:r2+len(r14)@k16` | gpt-5-nano-2025-08-07 | 3.400 | 3.000 | 2.400 | 2.000 | 3838.687 | 3565.000 | 4761 | 4463.589 |

##### Time per episode

Over each arm's scored episodes that kept time. *episode seconds* run from the start of the model's work on the task to its end; *model seconds* are the part spent waiting on the model and *harness seconds* the rest, the tool calls and the harness between them. *setup seconds* are the tool server's start before the episode: what the instrument costs, not the task. An arm whose episodes kept no time prints *not recorded*; no figure here is a guess or a zero standing in for one.

Time belongs to the serving and its load as much as to the task. It is this run's own, and is not to be compared with another card's unless both were served the same way at the same concurrency.

Concurrency of this run: not recorded.

| arm | model | median episode seconds | 90th percentile episode seconds | median model seconds | 90th percentile model seconds | median harness seconds | 90th percentile harness seconds | median setup seconds |
|---|---|---|---|---|---|---|---|---|
| `depth:d1` | gpt-5-nano-2025-08-07 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `depth:d2` | gpt-5-nano-2025-08-07 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `depth:d3` | gpt-5-nano-2025-08-07 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `depth:d5` | gpt-5-nano-2025-08-07 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `depth:d8` | gpt-5-nano-2025-08-07 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `depth:d1+h8` | gpt-5-nano-2025-08-07 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `depth:d2+h5` | gpt-5-nano-2025-08-07 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `distractor:r0@k16` | gpt-5-nano-2025-08-07 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `distractor:r2@k16` | gpt-5-nano-2025-08-07 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `distractor:r4@k16` | gpt-5-nano-2025-08-07 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `distractor:r8@k16` | gpt-5-nano-2025-08-07 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `distractor:r14@k16` | gpt-5-nano-2025-08-07 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `distractor:r0+len(r8)@k16` | gpt-5-nano-2025-08-07 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |
| `distractor:r2+len(r14)@k16` | gpt-5-nano-2025-08-07 | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded | not recorded |

##### Token totals and dollars

| arm | model | prompt tokens | cached input tokens | completion tokens | reasoning share | computed $ | reported $ |
|---|---|---|---|---|---|---|---|
| `depth:d1` | gpt-5-nano-2025-08-07 | 1138236 | 40448 | 230875 | 0.697 | 0.149 | n/a |
| `depth:d2` | gpt-5-nano-2025-08-07 | 1617174 | 57984 | 284392 | 0.655 | 0.195 | n/a |
| `depth:d3` | gpt-5-nano-2025-08-07 | 1582333 | 61312 | 346255 | 0.724 | 0.218 | n/a |
| `depth:d5` | gpt-5-nano-2025-08-07 | 2038219 | 76544 | 370502 | 0.676 | 0.250 | n/a |
| `depth:d8` | gpt-5-nano-2025-08-07 | 2592308 | 173952 | 302091 | 0.533 | 0.251 | n/a |
| `depth:d1+h8` | gpt-5-nano-2025-08-07 | 1366448 | 365568 | 160226 | 0.653 | 0.134 | n/a |
| `depth:d2+h5` | gpt-5-nano-2025-08-07 | 2096274 | 245888 | 277161 | 0.626 | 0.217 | n/a |
| `distractor:r0@k16` | gpt-5-nano-2025-08-07 | 835245 | 0 | 294996 | 0.801 | 0.160 | n/a |
| `distractor:r2@k16` | gpt-5-nano-2025-08-07 | 802244 | 0 | 281424 | 0.800 | 0.153 | n/a |
| `distractor:r4@k16` | gpt-5-nano-2025-08-07 | 825480 | 0 | 285483 | 0.793 | 0.155 | n/a |
| `distractor:r8@k16` | gpt-5-nano-2025-08-07 | 832988 | 0 | 295341 | 0.804 | 0.160 | n/a |
| `distractor:r14@k16` | gpt-5-nano-2025-08-07 | 845649 | 0 | 301381 | 0.810 | 0.163 | n/a |
| `distractor:r0+len(r8)@k16` | gpt-5-nano-2025-08-07 | 837666 | 0 | 281326 | 0.808 | 0.154 | n/a |
| `distractor:r2+len(r14)@k16` | gpt-5-nano-2025-08-07 | 855814 | 0 | 295792 | 0.805 | 0.161 | n/a |

#### Adjacent levels

A difference is paired over the shared seeds inside each resample. A pair is *distinguishable* only when its paired 95% interval excludes zero **and** the difference is at least delta* = 0.15 pass-rate points; otherwise it reads *too small for this design to call*, with its difference and interval shown.

##### depth, on reaching the goal (leaky pass@1)

How depth is read. The same pairing and rule, on the leaky rate, with saturation judged on that rate.

| model | knob | levels | delta leaky pass@1 | 95% paired interval | verdict |
|---|---|---|---|---|---|
| gpt-5-nano-2025-08-07 | depth | 1 vs 2 | n/a | n/a | excluded: saturated on leaky: depth:d1, depth:d2 |
| gpt-5-nano-2025-08-07 | depth | 2 vs 3 | n/a | n/a | excluded: saturated on leaky: depth:d2 |
| gpt-5-nano-2025-08-07 | depth | 3 vs 5 | -0.047 | [-0.130, 0.037] | too small for this design to call |
| gpt-5-nano-2025-08-07 | depth | 5 vs 8 | -0.157 | [-0.220, -0.090] | distinguishable |

##### every knob, strict pass@1

| model | knob | levels | delta strict pass@1 | 95% paired interval | verdict |
|---|---|---|---|---|---|
| gpt-5-nano-2025-08-07 | depth | 1 vs 2 | 0.150 | [0.037, 0.267] | distinguishable |
| gpt-5-nano-2025-08-07 | depth | 2 vs 3 | 0.160 | [0.073, 0.247] | distinguishable |
| gpt-5-nano-2025-08-07 | depth | 3 vs 5 | 0.060 | [-0.030, 0.147] | too small for this design to call |
| gpt-5-nano-2025-08-07 | depth | 5 vs 8 | -0.693 | [-0.763, -0.623] | distinguishable |
| gpt-5-nano-2025-08-07 | distractor | 0 vs 2 | 0.013 | [-0.040, 0.063] | too small for this design to call |
| gpt-5-nano-2025-08-07 | distractor | 2 vs 4 | -0.007 | [-0.050, 0.037] | too small for this design to call |
| gpt-5-nano-2025-08-07 | distractor | 4 vs 8 | 0.000 | [-0.053, 0.053] | too small for this design to call |
| gpt-5-nano-2025-08-07 | distractor | 8 vs 14 | n/a | n/a | excluded: saturated: distractor:r14@k16 |

#### Ordering

- gpt-5-nano-2025-08-07, depth: strict pass@1 across levels [1, 2, 3, 5, 8] is 0.547, 0.397, 0.237, 0.177, 0.870; non-increasing: no.
  - leaky pass@1 across levels [1, 2, 3, 5, 8] is 0.993, 0.957, 0.667, 0.713, 0.870; non-increasing: no.
  - Strict at d1 to d5 includes a stop-at-the-goal test that d8 cannot have: every depth arm offers the whole stage ladder, so below the top level the model can carry the record past the goal (overshoot), and at d8 no stage lies above the goal. Leaky measures reaching the goal at every level and is comparable across the whole axis, so depth is read on leaky, with the overshoot column showing how often the model did not stop at the goal.
- gpt-5-nano-2025-08-07, distractor: strict pass@1 across levels [0, 2, 4, 8, 14] is 0.917, 0.903, 0.910, 0.910, 0.960; non-increasing: no.
  - leaky pass@1 across levels [0, 2, 4, 8, 14] is 0.917, 0.953, 0.957, 0.963, 0.977; non-increasing: no.

#### Provenance

- models: gpt-5-nano-2025-08-07@gpt-5-nano-2025-08-07 at api.openai.com
- decoding: temperature=1.0, top_p=1.0, reasoning_effort=low, max_tokens=2048
- S = 60, n = 5, k on the card: 1, 2, 5; every k up to n is in the artifact
- bootstrap: 2000 resamples, seed 20260922
- delta* = 0.15; saturation at or below 0.05 and at or above 0.95; instrument threshold 0.02; no-call threshold 0.1
- budget: 100000000 tokens, 43200 s wall clock, or the provider out of credit, whichever first
- rates read on 2026-09-25
- concurrency: not recorded
- gpt-5-nano-2025-08-07 hosted at api.openai.com
