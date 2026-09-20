# Gap log

Append-only. Every entry records the date, what was needed, what the public API
offers today, the workaround **not** taken, and the ask.

This log exists because of one rule: from `proofload` we import only `Episode`
and `Rollout`, plus the CLI (A1). Anything else we need becomes an entry here,
never a workaround. The same goes for the other pinned dependencies.

Seeded 2026-09-11 from the spec's verification pass, which read Proofload at
`d5094a1`, the `verifiers==0.3.1` wheel, vLLM `v0.29.0` and the model cards.
Nothing is ever deleted: an entry that closes is marked closed and kept.

The spec's §2.6 also carries upstream notes that are **not** gaps, and they are
not repeated here: VN-1 to VN-6 (verifiers), VL-1 to VL-3 (vLLM) and CN-1,
CN-2 (Colab).

---

## PG-1 · Run-level constants

- **Date:** 2026-09-11
- **Needed:** one target callable that serves every arm, with the knob level
  passed as a run-level constant.
- **Available:** any key in the sweep file enters `config_hash`, which moves the
  seeds and breaks cell matching in `diff`. So the arms have to ride the target
  path instead, one callable per arm.
- **Workaround not taken:** writing the level as a cfg axis and accepting that
  cells can't pair across levels.
- **Ask:** a documented run-level constant that stays out of config identity.
  Filed with Proofload as **A23**.

## PG-2 · Pairing is behaviour, not contract

- **Date:** 2026-09-11
- **Needed:** a guarantee that seeds are `f(run_salt, config_hash, replicate)`
  and that `diff` matches cells on `config_hash`.
- **Available:** both hold in source, but neither is documented, and
  `derive_seed` is not exported.
- **Workaround not taken:** importing `derive_seed` and depending on a private.
- **Ask:** document or export the pairing contract. Filed as **A23**, which
  shares one ADR with A26.

## PG-3 · No family across diffs

- **Date:** 2026-09-11
- **Needed:** one correction family over the two models' primary diffs.
- **Available:** BH runs within a single diff. Each model runs in its own sweep,
  so the primary family is two single-cell diffs.
- **Workaround not taken:** pooling both models into one sweep to get them into
  one family, which would need one GPU serving two models.
- **Ask:** a family across diffs. Meanwhile the pre-registered Holm correction
  over the two p-values runs in the analysis notebook (A20).

## PG-4 · The power gate is unpaired, at base rate 0.5

- **Date:** 2026-09-11
- **Needed:** an MDE for a paired design at the observed base rate.
- **Available:** a two-proportion MDE at base rate 0.5, unpaired.
- **Workaround not taken:** computing our own N and declaring it instead of the
  gate's.
- **Ask:** a paired mode, and an observed-base-rate mode. The gate's number is
  used as it stands.

## PG-5 · No union events, and `meta` stays out of `diff`

- **Date:** 2026-09-11
- **Needed:** to test a composite outcome, such as leaky-pass.
- **Available:** an event is `outcome == event`, and `diff` never reads `meta`.
- **Workaround not taken:** relabelling stored rows to smuggle a composite into
  the outcome column.
- **Ask:** union events, or a documented relabel path. The leaky verdict stays
  descriptive, through `inspect`.

## PG-6 · No ordered-axis test within a run

- **Date:** 2026-09-11
- **Needed:** a dose-response test across a knob's levels inside one run.
- **Available:** pairwise diffs between arms.
- **Workaround not taken:** none. Dose-response is assembled from paired
  pairwise diffs, and the steady-rise rule is declared in the
  pre-registration.
- **Ask:** regression on the axes.

## PG-7 · Dependency conflict with verifiers

- **Date:** 2026-09-11
- **Needed:** Proofload's LiteLLM and OTel capture next to verifiers 0.3.1.
- **Available:** `proofload[agent]` and `[all]` pin `openai<2`, while verifiers
  0.3.1 requires `openai>=2.9.0`.
- **Workaround not taken:** unpinning `openai` in Proofload's extras, or
  installing them anyway and hoping.
- **Ask:** openai 2 compatibility for `[agent]`. Filed with Proofload as
  **A24**. This repo installs Proofload **core** only, and the verifiers trace
  is the trace.

## PG-8 · Doc drift on the rollout contract — closed 2026-09-11

- **Date:** 2026-09-11
- **Needed:** one statement of the rollout contract to build against.
- **Available:** the source says `(cfg, seed)`; Product Map §2, TC&O §12 and
  Phase 4 Experiment Specs §1 each said `(config, seed, i)`.
- **Workaround not taken:** writing a three-argument target to satisfy the
  docs.
- **Ask:** none outstanding. All three docs were corrected on 2026-09-11, and
  no doc now gives `(config, seed, i)`. **Closed**, and kept for the record.

## PG-9 · One horizon per diff

- **Date:** 2026-09-11
- **Needed:** a refusal, or a loud warning, when two runs' horizons differ.
- **Available:** `diff` compares at the smaller of the two horizons and marks
  later events unobserved, reporting the truncated count. A design with
  level-dependent turn budgets therefore loses events silently.
- **Workaround not taken:** none. The spec declares one common horizon `H`
  (N17), which is the API used as intended.
- **Ask:** `diff` refuses, or warns prominently, when the horizons differ.

## PG-10 · Errored rows are never retried

- **Date:** 2026-09-11
- **Needed:** a retry for a pair whose rollout raised transiently.
- **Available:** `store.missing()` counts an errored row as present, so
  `--resume` skips it. That pair is lost for good.
- **Workaround not taken:** deleting rows from the store to force a re-run.
- **Ask:** `sweep --resume --retry-errored`. Meanwhile the adapter never raises
  per episode, and a dead server stops the run instead (A17).

## PG-11 · The local backend is serial

- **Date:** 2026-09-11
- **Needed:** more than one episode in flight against one local model server.
- **Available:** the local backend runs episodes serially, in-process, so the
  GPU sits mostly idle. That, more than model size, sets the compute bill.
- **Workaround not taken:** running two sweeps at once against one server,
  which would break seed derivation's accounting and the store's batching.
- **Ask:** a local `--concurrency`, as Modal already has. Filed with Proofload
  as **A25**.

## PG-12 · No documented stop for a target

- **Date:** 2026-09-11
- **Needed:** a way for a target to end a run cleanly, leaving it resumable.
- **Available:** only raising something `_call_in_process` doesn't catch, which
  is behaviour rather than contract.
- **Workaround not taken:** `sys.exit` or `os._exit`, either of which would
  lose the pending batch.
- **Ask:** a documented stop signal.

## PG-13 · No store export hook

- **Date:** 2026-09-11
- **Needed:** to mirror a run's store to Drive while the run is going (A19).
- **Available:** the on-disk layout — `<run>/manifest.json` and
  `<run>/episodes/part-NNNNN.parquet`, with `.tmp` files mid-write — which is
  behaviour, not contract.
- **Workaround not taken:** reading the store through its internals rather than
  the files.
- **Ask:** a documented layout, or a `store sync` verb.

## PG-14 · Seeds are 32-bit

- **Date:** 2026-09-11
- **Needed:** distinct seeds within one run, so a replicate can't be a copy.
- **Available:** `derive_seed` truncates SHA-256 to 4 bytes, so two
  `(cell, replicate)` pairs in a run share a seed with probability about
  N(N−1)/2³³. For a near-greedy target, a shared seed is a duplicated
  replicate that the power gate still counts.
- **Workaround not taken:** patching `derive_seed`, or salting again inside the
  target.
- **Ask:** 64-bit seeds, or a documented guarantee of distinct seeds within a
  run. Filed with Proofload as **A26**, in one ADR with A23. Meanwhile salts are
  vetted through the public `--salt` and `inspect` (A21).

## PG-15 · The hub's taskset listing can't be enumerated

- **Date:** 2026-09-11
- **Scope:** this is a **Prime Intellect Environments Hub** gap, not a
  Proofload one. It carries a PG number because the log had one sequence when it
  was seeded.
- **Needed:** a live enumeration of the hub's tasksets, for KC9's landscape
  verification.
- **Available:** the listing at `app.primeintellect.ai/dashboard/environments`
  needs a login and JavaScript, and no public listing endpoint was found. The
  figure of 23 tasksets comes from Prime Intellect's own `verifiers v1`
  announcement, which matches the landscape check's own count.
- **Workaround not taken:** reporting that published figure as though the hub
  had been enumerated. The KC9 re-run of 2026-09-11 records this leg as
  corroboration instead.
- **Ask:** a public listing endpoint, or an enumeration by someone with hub
  access. **Owed before the pre-registration freezes** (§4 stage 4), since KC9
  rests on it.

---

## PG-16 · The audit field is arm-dependent, so the verdict state is too

- **Date:** 2026-09-11
- **Scope note:** this is an internal design gap, not an upstream one. It gets a
  PG number because the log has one sequence.
- **Needed:** a records value that TG-M3 can compare exactly against
  `expected_final_state` for `passed` (§2.3), and that the D control's arm
  transform leaves alone, so N14's field-by-field bundle diff still sees only
  `prompt` and `seq_start` change.
- **Available:** TG-ADR-36 defines the audit field as the `seq` of the last
  successful transition, and TG-ADR-35 makes `seq_start` an argument that N14
  varies by arm. So the audit field of a completed record differs between the
  `dL+hH` control and the plain `dL` arm by exactly `H − dL`. Measured in
  TG-M1's oracle: `test_e5_seq_start_is_an_argument_not_a_scenario_field`
  asserts every other record field is equal across two `seq_start`s and that the
  audit field moves by the offset.
- **Workaround not taken:** quietly dropping the audit field from
  `records_bytes`, or quietly making it relative to `seq_start`. Either would
  have hidden the choice inside TG-M1's oracle, two modules before the module
  that has to live with it.
- **Ask:** TG-M3's Session A picks one, and the pick goes in the spec before the
  verifier is frozen:
  1. `expected_final_state` is computed per arm from that arm's `seq_start`, and
     N14's list of fields the D control may change gains it; or
  2. the verdict compares records excluding the audit field, and §2.3 says so;
     or
  3. the audit field records the call index within the episode rather than the
     `seq`, which costs TG-ADR-36 its wording.

  Not blocking TG-M1 or TG-M2: the engine's behaviour is the same under all
  three, and only the verdict's comparison changes.
- **Taylor's lean, 2026-09-11, recorded and not binding:** option 2, exclude the
  audit field from `passed`. The reasoning is that the audit field is instrument
  bookkeeping rather than domain state, which is the same split TG-ADR-35 drew
  between the records and the sequence counter. TG-M3's Session A still makes
  the call and still has to justify it against the other two.
- **Closed 2026-09-14 by TG-M3's Session A, at `b8f3bfe` on `tg-m3-session-a`:
  option 2.** The verdict compares the records without the audit field. A records
  value is a sorted tuple of `(class, record_id, stage, token)` and there is no
  audit field in it, so `initial_state` and `expected_final_state` both carry the
  projection and `verify` compares on exactly it. `mutations` is TG-M1's and is
  unchanged: it still reports `(class, id, "audit")` triples and `Verdict.mutations`
  still carries them, because that field is diagnostic output and not the predicate.

  **The deciding argument is N14, not that the audit field is bookkeeping.** Taylor's
  lean and option 2 agree, and the lean's reasoning is not what carried it. Option 1
  makes `expected_final_state` differ between `depth:d1+h8` and `depth:d1`, so N14's
  list of fields the D control may change grows from the two §2.2 names to three — and
  the field that joins it is *the one the verdict compares*. Option 3 costs TG-ADR-36
  its wording, re-opens a module two steps back, and is not even reachable: the engine
  would have to know `seq_start` to subtract it, and `DomainState` carries `next_seq`
  and never `seq_start` (TG-ADR-35). Option 2 is the only one of the three that leaves
  N14 at the two fields §2.2 names.

  **Measured, not asserted** (Master Action List §18 rule 14). Option 2 is only free if
  no call can move a record's audit field without moving its stage. `apply` writes it in
  the one branch that also writes `stage` and `token`, and
  `test_pg16_2_the_audit_field_moves_if_and_only_if_the_stage_moves` measures that over
  the status codes the engine emits, with `test_pg16_3` as a property over random
  sequences. So the projection is as discriminating as the full records for `passed`
  and for `collateral_mutation` alike: a record cannot have been mutated without its
  stage moving.

  **What option 1 would also have cost, found by the mutation pass and not by reading.**
  Mutant `m01b`, a consistent option-1 implementation, fails
  `test_ov3_a_passing_episode_with_a_malformed_turn_is_still_passed`: under option 1 an
  episode that makes one rejected call before an otherwise-correct solution no longer
  passes, because the rejected call advances `seq` and shifts the audit field. That is
  the failure TG-ADR-35 names in its own words — "an extra rejected call can't fail an
  otherwise-correct episode" — reappearing through the verdict rather than the state.

  **What would reopen it:** a design that needs the verdict to distinguish two final
  states that differ only in when a transition happened. Nothing in §2.3's vocabulary
  does; a label about *ordering* rather than *outcome* would.

---

## PG-17 · No public read of an episode's `meta`

- **Date:** 2026-09-20
- **Needed:** to read what a stored episode recorded in `meta` (`scenario_hash`,
  `task_id`, `arm_id`, the level) from a finished run, so that A2 ("two scripted runs,
  with the stores compared"), A3 ("`meta` carries the level on every episode") and A6
  ("recorded, so any episode can be regenerated") can be tested against what
  `proofload sweep` actually stored.
- **Available:** `inspect` prints a row's config, seed, `t` and any stored trace spans,
  and no `meta` field. `diff`, `report` and `check` never read `meta`, which is
  deliberate (PG-5; `defining-outcomes.md`). So no verb reaches a `meta` field.
- **Workaround not taken:** `proofload.store.Store(...).read(...)`, an internal, which A1
  forbids importing.
- **Taken, and named:** TG-M5's oracle reads `<run>/episodes/part-NNNNN.parquet` with
  pyarrow, the on-disk layout PG-13 already asks Proofload to document. It is a test-side
  read only, and it depends on that layout and on `meta` being a JSON string column, so a
  layout change moves one helper (`read_rows`) and nothing in the adapter.
- **Ask:** `proofload inspect --json`, or a `--meta KEY` selector, or the documented
  layout PG-13 asks for, which would turn the interim into a contract.
