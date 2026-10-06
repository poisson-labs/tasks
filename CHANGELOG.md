# Changelog

All notable changes to Poisson Tasks. The package has not been released; everything below is
unreleased and sits at version `0.0.1`.

## Unreleased

### The run engine: the estimate, the cap, resume and Ctrl-C

- **What a plan will cost, before anything is spent.** `poisson_tasks.runs.estimate` reads the
  published card of the plan's model (model A's card for a model no card measured, or the card
  named) and gives the plan's episodes, its least and most model calls, the calls, tokens and
  dollars expected at the plan's prices, and which card it read. Every mean is computed from the
  card's records; nothing is a typed number.
- **One folder per plan.** A run goes in `runs/<preset>-<model>/`, then `-2`, `-3` for a second
  run of the same plan or a changed one, with no hash in its name. The folder that holds a plan
  is found by the hash inside its `plan.json`, so a renamed folder is still found; `find_run`
  says whether a folder is new, resumed or complete, names the folder a changed plan came after
  and the fields that changed, and only reads.
- **The cap is a bound on what is spent, not an estimate.** The spend and token caps are checked
  before every model call, through the harness's relay in the run's own process, so the final
  spend is at most the cap plus the calls in flight when it was reached. Before an episode starts,
  the measured spend plus a reservation for every episode in flight must leave room; the
  reservation is the largest episode the run has seen, and before any, the card's 95th
  percentile for the arm. The cap holds the folder's total across runs: running again at the same
  cap sends nothing. An episode the cap cuts short is not an instrument failure and is owed
  again; what its calls cost is in the ledger.
- **The ledger**, `spend.jsonl`, has one line per episode that ended: the arm, the seed, the
  attempt, the tokens and the dollars (`null` without a price). It is append only; a torn last
  line, left by a process that died while writing, is dropped when the ledger is opened.
- **Resume loses nothing and runs nothing twice.** A stopped run keeps every finished episode,
  byte for byte, and a resume runs exactly the episodes owed, through the wheel's own resume. A
  run in which some episodes failed is resumed too: the failed ones run again, and the instrument
  tally keeps the failure.
- **Ctrl-C.** The first stops dispatching and gives the episodes in flight ten seconds to finish
  and be recorded; the run then returns with the interrupted verdict and the ledger written. A
  second stops at once. Nothing the run started is left running.
- **Stops.** The provider saying it is out of credit stops the run after the episode that heard
  it. Five episodes in a row failing before any was scored stop it, with the first error's status
  and the provider's own words; a run in which every episode failed is never done. A run that
  makes no model call and finishes no episode within the watchdog's limit (600 seconds) is
  stopped, with whatever it started, quoting the last lines of `run.log`.
- **`run.log`** holds the run's own progress, the harness's records of warning level and above,
  and any traceback. The key never shows: every run of four or more characters of it is masked
  in the log, in the trace lines and in the first error a run reports.
- **The machine.** The harness runs with `PIP_REQUIRE_VIRTUALENV=1`, so its bootstrap takes uv's
  installer every time, and `UV_NO_MODIFY_PATH=1`, so that installer edits no shell start-up
  file. Besides the run folder, a run writes only what the harness, uv and uv's installer write
  for themselves: `~/.cache/verifiers`, `~/.local/bin/uv` and `uvx`, `~/.cache/uv`, uv's receipt
  in `~/.config/uv`, one `/tmp/vf-port-*` file per episode and one empty uv lock file in the
  temporary folder.
- **`run` and `export` are one path.** `runs.verifiers_config` is the eval config the run uses for
  an arm, as a mapping `eval @` reads: the same taskset, arm, seeds, attempts, model, endpoint,
  key variable's name, decoding and turn cap, with `push` off. A decoding field declared
  `"not sent"` is in no request.
- **`calibration.run_cell`** runs one arm's cell for any design (the seeds, attempts and decoding
  given) through the same runner as `run_arm`, which is unchanged: `run_arm` is `run_cell` with
  the published design.
- **Until the cards ship inside the package**, the estimate reads their records from the
  checkout's `calibration/` folder; a wheel installed on its own refuses the estimate in one line
  that says so, and a run from it reserves nothing before its first episode and says so in
  `run.log`.

### Cost and time on every card

- **Every card shows what each level cost, beside its pass rates.** Every level table and
  the control-arm table gain three columns: median model calls, median tokens and median
  episode seconds.
- **The cost section is three tables**: calls and tokens per episode (means, medians, the
  90th-percentile tokens, and tokens per strict pass); time per episode (the median and 90th
  percentile of episode, model and harness seconds, and the median setup seconds); and the
  token totals and dollars that were already there, unchanged.
- **A record carries its episode's time and the size of its first request**, read from the
  trace by `records_from_run`: `episode_seconds`, `model_seconds`, `harness_seconds`,
  `setup_seconds` and `first_request_prompt_tokens`. Each is optional and left out of the
  written line when it was not recorded, so an `episodes.jsonl` written before these fields
  existed reads and writes back unchanged.
- **A figure that was not recorded is shown as *not recorded*, never as zero.** A phase that
  never ended, or a zero in an episode that made no model call, is missing, and a cell's
  time figures are over the episodes that kept time.
- **Time is printed and never compared.** It belongs to the serving and its load as much as
  to the task. `Provenance` gains an optional `concurrency`, how many episodes ran at once
  (`Provenance.for_run(..., concurrency=...)`); the card prints it wherever it prints seconds,
  and the combined page says it does not compare one card's time with another's. No
  comparison, ordering or verdict reads a time figure, and two cards need not share a
  concurrency to share a page.
- **Both committed cards were rebuilt from their records**, with no new model calls and every
  earlier figure unchanged. Each cell of `artifact.json` gains fourteen keys. Neither run
  kept time or its concurrency, so both cards read *not recorded* for them; the first cards
  with time will come from the next runs.

### Depth read on reaching the goal, one page for every card, and plain words

- **Depth is read on reaching the goal, with stopping at the goal shown beside it.** Every
  depth level offers the whole stage ladder, so below the top level the strict rate also
  asks the model to stop at the goal, and the two calibrated models do not fail these the
  same way. So:
  - every cell now carries its overshoot share and an interval on leaky pass@1;
  - depth's adjacent levels are also compared on leaky pass@1;
  - the card reads depth on that comparison, with the overshoot column beside it.

  Strict stays computed, published and first in every table. Both committed cards were
  rebuilt from their records, with no new model calls and every earlier figure unchanged.
  What it shows:
  - on reaching the goal, depth does not order difficulty for either model: saturated
    everywhere for Qwen3-8B, and for gpt-5-nano only d5 against d8 is distinguishable, with
    d8 higher (its fall from d2 to d3 starts at a saturated level, so it is not called);
  - what depth changes for both models is stopping at the goal.
- **`docs/calibration.md`**, one page for every calibrated model, rendered from the cards:
  where their difficulty orderings agree, read from each card's own verdicts, then each card
  in full. `examples/calibration_card.py --page` prints it. Of 12 adjacent pairs of levels,
  the two models agree on none and disagree on one. Cards measured differently refuse to
  share a page.
- **The distractor dial is experimental.** It does not make tasks harder for either
  calibrated model, so it is not a difficulty setting. `eval --help` says so beside the arm
  option.
- **`verify` accepts a bundle written before a card gained a figure,** checking every figure
  it carries. A missing cell or a changed number is still refused.
- **Plain words.** The card, the calibration module's and the Colab driver's messages and
  help, the notebook, the engine, knobs and adapter modules, the tests' comments and
  docstrings, and `gap-log.md` (one recorded exception to its append-only rule) no longer
  cite internal decision ids, specification sections, private notes or people.
- `LICENSE` reads "Copyright (c) 2026 Taylor Kolasinski / Poisson Labs". `outputs/`, where
  `eval` writes its runs, is ignored.

### Model B's card: Qwen3-8B

- **The second calibration card is in:** `Qwen/Qwen3-8B` at `b968826d`, thinking off, served
  with vLLM 0.29.0 on a Colab L4 (FP8, a 16,384-token context, vLLM's own sampler), each
  episode capped at 32 model calls.
  - 4,200 episodes, all scored, no instrument failure; it published.
  - Records, artifact and instrument tally are in `calibration/qwen3-8b-b968826d/`.
  - `examples/calibration_card.py` now rebuilds any committed card under the provenance its run
    recorded. A test holds both cards to recomputing byte for byte.
- **What it shows:**
  - **Depth runs the opposite way to `gpt-5-nano`:** strict pass@1 rises from 0.000 at d1 to
    0.997 at d8. Qwen reaches the goal at every level (leaky 0.97 or more) but, low on the
    ladder, carries the record past it.
  - **The distractor dial is saturated at every level.**
  - **Seeded history** is what lowers Qwen's leaky rate, to 0.77 and 0.73.
- **Getting it to run took four fixes on Colab, each test-first:**
  - vLLM's FlashInfer sampler could not build its kernel there (no `ninja`), so the pin turns it
    off.
  - Colab's `UV_SYSTEM_PYTHON` broke the harness's setup, so the driver drops it.
  - Long seeded histories outgrew 8,192 tokens, so the context is now 16,384.
  - Qwen looped, so every episode is now capped at 32 model calls.
  - Failures now print the engine's own error and the first episode error. The notebook creates
    its Drive folder.

### An episode ends after 32 model calls

- **The taskset now pins a turn limit**, `agent.max_turns = 32`, beside the measured harness,
  so the documented `eval` command and the calibration run behave the same.
  `--env.agent.max-turns N` overrides it.
- **Why:** verifiers sets no turn limit by default. On model B's second calibration run,
  Qwen3-8B looped in the two long-history control arms: 20 episodes in each made 107 to 112
  model calls on tasks that need one or two. They ended only when the 16,384-token context
  filled, which reads as a setup failure, and the card refused to publish.
- **The number:** four times the deepest task's minimum, eight calls at `depth:d8`. Ordinary
  episodes of both calibrated models end within 18 calls. In the three arms where Qwen
  looped, any cap from 24 to 50 changes 1 episode in 900. An episode that reaches the cap
  is scored `turn_limit`, the model's own failure.
- **The card prints the cap.** Model A's run had none. Its longest episode was 18 calls, so
  its card is what it would be under the cap, and its committed data recomputes byte for
  byte.
- **Added after the fact, and said so:** the limit was added after a run showed the looping.
  The refused runs are kept as evidence.

### Calibration: what each difficulty level is worth

- **`poisson_tasks.calibration`**, a module that measures what each level of `depth` and
  `distractor` is worth to one named model. Per level it computes strict pass@1 (the
  headline) with leaky pass@1 beside it, pass@k by the unbiased estimator for every
  `k <= n`, a 95% interval from a bootstrap that resamples tasks, and the cost each episode
  burned from the provider's own token counts. Neighbouring levels are compared pairwise over
  shared seeds and called distinguishable only when the paired interval excludes zero and the
  difference is at least 0.15. Levels at or below 0.05 or at or above 0.95 are marked
  saturated and left out of every comparison. The design is fixed in code: 60 seeds from the
  eval split, 5 attempts per task, and a declared, non-deterministic decoding.
- **A card, and the refusals that keep it honest.** `build_artifact` computes every figure
  from the per-episode records under a provenance block; `render_document` and
  `render_readme_lines` render them and are never typed by hand. A card refuses to build
  when a cell holds two models, when its instrument-failure rate is above 0.02, when a locally
  served model is missing its serving stack, or when more than 10% of a cell's scored
  episodes made no tool call.
- **A runner that stops cleanly and resumes.** `run_arm` runs one arm through the verifiers
  `eval` body and checks, before each episode, the token budget, the wall-clock limit and
  whether the provider has reported the account out of credit. Instrument failures are
  tallied as they happen, in a file the resume does not rewrite. An interrupted run resumes
  with the same tasks, each with its full number of attempts, none run twice and none skipped.
- **The token limit goes out as `max_completion_tokens`.** OpenAI's reasoning models refuse
  `max_tokens` with an HTTP 400, and vLLM's chat endpoint accepts either.
- **The prompt quotes the record id and the entry code.** Model A's first card had 72.5% of
  its episodes end on a first reply asking for those two values and calling no tool. This
  changes `tasks.py`, so the generator hash, and with it every `task_id`, moved.
- **Two columns and a gate for that failure.** Every cell reports the share of episodes with
  no tool call and the share that stopped short of the task's minimum, and the no-call share
  refuses above 0.10. Phase 1 of a run is a plumbing gate: every episode must make a tool
  call and at least half must reach their minimum.
- **Depth ordering shows leaky beside strict.** Every depth level offers the whole stage
  ladder, so strict below the top level also tests stopping at the goal, which the top level
  cannot.
- **The artifact's call counts are named for what they count**: `tool_calls`, `model_calls`
  and `model_calls_median`. An `artifact.json` written before this change uses the older
  names.
- **Model A's card**: `gpt-5-nano-2025-08-07`, 4,200 episodes, all scored, about $2.52. Its
  records and artifact are in `calibration/gpt-5-nano-2025-08-07/`, and
  `examples/calibration_card.py` recomputes the card from them. Read it with
  `docs/calibration-guide.md`.
- **Model B, prepared**: `poisson_tasks.calibration_run` and
  `notebooks/calibration_model_b.ipynb` serve `Qwen3-8B` at a pinned revision with vLLM
  0.29.0 on a Colab L4 and run the same card, checkpointing to Google Drive so a dropped
  runtime resumes. Not run yet.

### Also since the first public-preparation pass

- **The verifiers export** (`poisson_tasks.export`): a generated task as a verifiers v1
  taskset, scored by the generator's own verifier, with its tool block served over MCP.
- **The standalone model path**: the package is the verifiers taskset id `poisson-tasks`,
  and `eval` runs it with the `null` harness in a local subprocess with no flag.
- **Vocabulary v2**: the record-id word lists are drawn disjoint from every tool name.
- **The rename**: `task-generator` / `task_generator` became `poisson-tasks` /
  `poisson_tasks`. Hash domain separators keep the old spelling, because their bytes are
  hash input.
