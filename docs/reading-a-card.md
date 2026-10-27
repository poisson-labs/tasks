# Reading a card

A level of a knob is a candidate until a model has been run against it. A **card** says what each level of a knob is worth to one named model, measured on generated tasks and printed with its uncertainty, its cost and every setting it depends on. `poisson-tasks card` builds one from a run, and two cards ship with the package, for `gpt-5-nano` and `Qwen3-8B`. This page explains how to read a card. What the two published cards show is on [published-cards.md](published-cards.md).

Every number on a card is one model's. A card never pools two models or ranks them, and a level's number for one model says nothing about what it is worth to another.

## How a card is measured

The published cards were measured like this; a card from your run is measured the same way with the numbers your settings file asks for, which is usually fewer tasks and fewer attempts (the card then says so).

- **Tasks.** Each level (an *arm*, such as `depth:d3`) is run on 60 generated tasks, one per seed. The sixty seeds are derived from a fixed string, come from the eval split, and are the same at every arm; the card publishes them with their hash.
- **Attempts.** Each task gets 5 independent attempts, so a cell (one arm, one model) is 300 episodes. The decoding is declared in full and is deliberately not deterministic: temperature 1.0, top_p 1.0, `reasoning_effort: low`, a 2,048-token completion limit.
- **Harness.** Every episode runs through the verifiers taskset with the `null` harness, the same path as the one-line `eval` command in [verifiers-export.md](verifiers-export.md): the model sees the task's prompt and its tool block, and nothing else.
- **Scoring.** The export's own reward: `strict` is 1.0 when the generator's verifier gives strict `passed`, and `leaky_pass` is recorded beside it.
- **Turn limit.** An episode ends after 32 model calls, the taskset's own default. An episode that reaches it is scored `turn_limit`, the model's failure, and the card prints the cap in its provenance.
- **Stopping.** A run stops on whichever comes first: its spend or token cap, the provider saying the account is out of credit, the first five episodes all failing before the model answered, or no model call and no finished episode in its first 600 seconds ([commands.md](commands.md) gives each one's line). The published cards' runs stopped on a token budget and a wall-clock limit instead, and their provenance names both. A stopped run keeps every episode already paid for and marks the cell incomplete; it never quietly publishes a smaller sample.
- **Resuming.** A run that is interrupted and resumed serves the same tasks, each with its full number of attempts, none run twice and none skipped. It does not reproduce the interrupted attempts byte for byte, because the decoding is not deterministic.
- **Staleness.** A card is pinned to the generator it was made with: a hash over the bytes of the generator's source files. When those files change, the tasks change and the card is stale. It is not regenerated automatically; a card whose generator hash differs from the installed package's says so. On a card from a run, the generator it was made with is the one the run recorded before its first request (below); a run made before poisson-tasks 0.2.0 recorded none, and its card is read against the generator of the install that built the card.

## The columns

One table per knob, one row per level:

| column | what it means |
|---|---|
| **strict pass@1** | First in every table. The share of attempts that reached the goal state exactly and then ended with a reply: no stage past the goal, no other record touched. It is the mean over tasks of each task's pass rate, so every task weighs the same. |
| **95% interval** | For strict pass@1, from a bootstrap that resamples *tasks* (each task's attempts move together), 2,000 resamples at a fixed seed, so the interval recomputes exactly. |
| **leaky pass@1** | Reaching the goal: also counts an attempt that reached it and then went past it (overshoot) or touched another record (collateral damage). **Depth is read on this rate** (below). |
| **leaky 95% interval** | The same task-resampling bootstrap, on the leaky rate. |
| **overshoot** | Stopping at the goal: the share of scored attempts that reached the goal and carried the record past it. Strict fails these and leaky counts them. |
| **strict pass@2, pass@5** | The chance that at least one of *k* attempts passes, by the unbiased estimator `1 - C(n-c, k) / C(n, k)` per task. Every *k* up to the number of attempts is in the artifact; the card shows 1, 2 and 5. |
| **median model calls** | What the level cost, beside its rates: the median number of model calls over the scored episodes. |
| **median tokens** | The median tokens per scored episode: prompt, cached input and completion together. |
| **median episode seconds** | The median time from the start of the model's work on the task to its end. It reads *not recorded* when the run's episodes kept no time, as on both published cards, which were run before time was kept. Seconds depend on how the model was served and how many episodes ran at once, so they are printed and decide nothing: no comparison, ordering or verdict reads them. |
| **min calls** | The fewest tool calls the task can be solved in, known from the task alone: *d* at depth *d*, 2 for every distractor level. |
| **no tool call** | The share of scored episodes that ended without a single tool call. |
| **stopped short** | The share that made at least one call but fewer than the minimum. Disjoint from *no tool call*. Giving up partway through a long chain is a difficulty result, so this is printed and never gated. |
| **saturated** | `yes` when strict pass@1 is at or below 0.05, or at or above 0.95. A comparison on a rate leaves out a level saturated on that rate. |
| **instrument** | Episodes that failed for a reason that is not the model's: `verifier_error`, `replay_mismatch`, `api_error` or `wall_timeout`. They leave the denominator, and they are counted at the moment they happen, so a resumed run cannot hide them. A cell whose instrument rate is above 0.02 is not published. |
| **incomplete** | `yes` when the run stopped on a limit before the cell was full. |

### How depth is read

Every depth level offers the whole eight-stage ladder, so below the top level a model can carry the record past the goal. The strict rate therefore asks two things at once: reach the goal, and stop there. The two published models do not fail these the same way, so a card reports them apart. **Depth is read on leaky pass@1, reaching the goal**, compared level by level in its own table; the overshoot column shows how often the model did not stop. Strict is still computed, published and compared, and it is first in every table. At d8 no stage lies above the goal, so nothing can overshoot there and strict equals leaky.

### The no-call refusal

**A cell in which more than 10% of scored episodes made no tool call is not published at all, and neither is the card that holds it.** Such a cell measures whether the model starts the task, not how hard the level is. It was added after a first card for `gpt-5-nano` measured mostly that: most of its episodes ended on a reply asking for values the prompt already held. `poisson-tasks card` refuses in the same way, with exit 1.

### The decoy-tools dial is experimental

On both published models the distractor knob (the decoy-tools dial) does not make tasks harder (below), so it is **not a difficulty setting** for current models, and the export's help for the arm option says so. Its levels stay available, and a card that includes it says it is experimental.

### The other tables

- **Control arms** (`depth:d1+h8`, `depth:d2+h5`, `distractor:r0+len(r8)@k16`, `distractor:r2+len(r14)@k16`) have their own table. They exist to separate a knob from what travels with it (depth from history length, decoy tools from prompt length); they are not difficulty levels and are never read as one. See [knobs-and-arms.md](knobs-and-arms.md).
- **Cost per episode** is measured from each episode's own usage and timing, never estimated, and has three tables, one row per arm in each:
  - **Calls and tokens per episode**: the mean and median model calls and tool calls; the mean, median and 90th-percentile tokens (prompt, cached input and completion together); and *tokens per strict pass*, the mean tokens divided by strict pass@1, which is what one strict pass costs at that level and reads *n/a* where nothing passed.
  - **Time per episode**: the median and 90th percentile of *episode seconds*, of the *model seconds* inside them (waiting on the model) and of the *harness seconds* (the tool calls and the harness between them), and the median *setup seconds*, the tool server's start before the episode, which is what the instrument costs and not the task. These are over the scored episodes that kept time. An arm whose episodes kept none reads *not recorded*: a figure that was not measured is never printed as zero. Both published cards read *not recorded* throughout, because neither run kept time.
  - **Token totals and dollars**: prompt, cached input and completion tokens, the reasoning share, and computed and provider-reported dollars. Cached and uncached input are kept apart because they are billed at different rates; reasoning tokens are already inside the completion tokens and are not added again. Dollars are tokens times the rates the run declared, with the date they were read. A model with no declared rate, such as one served on your own GPU, has no dollar figure.

  **Time is each run's own.** It belongs to the serving and its load as much as to the task, so wherever a card prints seconds it also prints the run's *concurrency*, how many episodes were in flight at once, or *not recorded* when the run did not write it down. One card's time is not to be compared with another's unless both were served the same way at the same concurrency, and the combined page compares none.
- **Adjacent levels** compares each level with the next one up, paired over the shared seeds inside each bootstrap resample. A pair is **distinguishable** only when its paired 95% interval excludes zero **and** the difference is at least **0.15** pass-rate points, a resolution fixed before any card was measured. Otherwise it reads *too small for this design to call*, with the difference and interval still shown. Depth has one table on leaky pass@1, reaching the goal, which is how depth is read, and every knob has one on strict.
- **Ordering** asks whether pass@1 is non-increasing across the whole axis, on strict and, for depth, on leaky.
- **Provenance** lists everything a number depends on: the package version, the engine, generator and vocabulary hashes, the seed list's hash, the harness and verifiers version, the model and where it was served (for a locally served model, the serving stack, its version and flags, the GPU and the weights' exact revision), the decoding, the budget, the turn limit, the run's concurrency when it recorded one, and every threshold above.

## What produced it

A run records what produced it before its first request, in a file in its folder, `produced_by.jsonl`, and its card says it in two places: a `made with` row in the result, right after the `run` row, with each hash cut to its first 12 characters, and a section of `card.md`, **What produced it**, with the full hashes. `card --json` and the card's `artifact.json` carry the same record as `produced_by`. For a run on the built-in tasks the row reads like this (the numbers are the run's):

```text
made with  poisson-tasks 0.2.0 · generator b460964dc153 · plan 1f2e3d4c5b6a (first-look) · 10 seeds, list 2061672b2321
```

On your own tools it also names the own-tools generator and your tool file's contract (`own-tools generator 22c8ac690458 · tool spec a2d89128c189 (an OpenAI tools file)`). Each hash says one thing:

- **poisson-tasks and verifiers**: the versions installed when the run started. A resume with another version adds a line to the file, and the row reads `poisson-tasks 0.2.0, resumed with 0.2.1`. A version alone changes no task.
- **generator**: the built-in generator's hash, over its version label and the bytes of its source files. It moves when the generator changes, and then every task changes. On your own tools it is still recorded, so you can see it did not move either.
- **own-tools generator**: on your own tools, the hash over the bytes of the modules that make tasks on them. It moves when they change.
- **tool spec**: on your own tools, your tool file's contract hash: the SHA-256 of the file as canonical JSON. Whitespace, key order and JSON against YAML do not move it; any change to a tool, a description or a value does. The file's own SHA-256, which any byte moves, is recorded beside it. [own-tools.md](own-tools.md) shows how to recompute both.
- **domain and vocabulary** (in `card.md`): the mock domain's table and the table record ids are made of. Neither changes in this release.
- **plan**: the plan's hash, which covers its levels, seeds, attempts, model, endpoint, decoding and turn limit (and on your own tools every `[own]` setting), with the preset's name beside it. It moves with the model, so another model on the same tasks has another plan hash.
- **seeds**: how many, and the hash of the seed list in the order they run.

**A card can be newer than its run.** The card's first paragraph names the install that built the card; the record names the one that ran the episodes. When the two differ, the record is the one to trust for what produced the numbers, and the card is stale when the generator the run recorded is not this install's.

**Runs made before poisson-tasks 0.2.0 recorded none of this.** Their cards read `not recorded: the run was made before poisson-tasks 0.2.0`, and a run started before 0.2.0 and resumed with it reads `not recorded: the run was started before poisson-tasks 0.2.0 (resumed with 0.2.0)`, since what produced its first episodes is not known. The two published cards carry no record either, and `card --published` shows nothing new for them.

`card --compare OTHER_RUN` reads two runs on these records and sets their figures side by side only when they measured the same tasks the same way; [commands.md](commands.md) gives its answers.

## What a card says it means, and what it does not claim

A card from a run ends with two short pieces of text. The first says what the card is: the model, where it was served, how many tasks per level with how many attempts at each, how a rate is read and how two levels are called different. The second is a list of what it does not claim; every line that applies is there, except that of the two lines about reading it beside the published cards a card carries one: the first when its generator is not theirs, which in this release is every card from a run, and the second otherwise.

- It is one model's result on these tasks: it ranks no models, and it says nothing about another model or about tasks other than these. *(always)*
- With fewer than the published 60 tasks per level, the intervals are wide and most pairs of levels will read too small to call; that is the design's resolution, not evidence that the levels are the same. *(a card with fewer tasks per level than the published cards)*
- It cannot be read beside the published cards in this release: they were measured on an earlier build of the generator, and a later release measures them again on the current one. *(a card made by another build of the generator than theirs: in this release, every card from a run)*
- It is not comparable with the published cards: it was not measured the same way, so none of its figures reads against theirs. *(a card measured differently from them in another way, such as its decoding or its strictness)*
- No published card covers this plan: none holds any of its levels, so nothing here can be read beside a published figure. *(a plan that holds no level a published card holds)*
- Its model was served by its user: how it was served is not pinned beyond what the server reported, so a later run of the same weights served differently is not the same measurement. *(a model on Ollama, vLLM or another endpoint you serve)*
- The distractor knob is experimental: it did not make tasks harder for either calibrated model. *(a card that holds the decoy-tools dial)*
- It is pinned to the generator it was made with, which is not the one this install has, so it is stale. *(a card from another build of the generator: the one its run recorded, when it recorded one)*
- Some of its attempts were made by a later run of its folder: a resumed attempt is a fresh attempt, not a copy of the one it replaces. *(a run that was interrupted and resumed)*

A card on your own tools carries other lines, which [own-tools.md](own-tools.md) gives. A card that includes the top depth level also carries the note on how depth is read, above.

## The two published cards

Two cards ship with the package, for `gpt-5-nano` and `Qwen3-8B`, and both are read this way. Neither is current in this release, because both were measured on an earlier build of the generator; [published-cards.md](published-cards.md) says what they show and where the two models agree.

## Measuring your own model

`poisson-tasks run` and `poisson-tasks card` do this from the command line ([commands.md](commands.md)). A first look is 30 episodes; a card of the published design is 4,200, and the published `gpt-5-nano` card cost about $2.52. [python.md](python.md) shows the same steps from Python.
