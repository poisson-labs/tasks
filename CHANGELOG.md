# Changelog

All notable changes to Poisson Tasks. The package has not been released; everything below is
unreleased and sits at version `0.0.1`.

## Unreleased

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
