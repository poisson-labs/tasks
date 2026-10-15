# What a task is

A task is a request to move one record of a mock ledger up a fixed ladder of stages,
using tools that are given to the model and nothing else. It is generated together with
its verifier, its reference solution and a set of wrong answers, from an `(arm, seed)`
pair and a fixed vocabulary table -- no model call, no network call, and the same
bytes on every run, process and platform. An **arm** is one setting of one dial (a
*knob*), such as `depth:d3`, depth at level 3 (a *level* is one setting of a knob);
the seed picks which task of that arm. [knobs-and-arms.md](knobs-and-arms.md) lists
the knobs.

`poisson-tasks generate --show` prints all of this for one task. Read that beside this page.

## The domain

Twelve ledger classes (`invoice`, `payment`, `budget`, ...). Each holds records; each
record stands at a stage from 0 to 8 along a shared eight-name ladder (`review`,
`sample`, `measure`, `monitor`, `compare`, `bundle`, `route`, `label`).

A record moves one stage at a time, and each move is a tool call:

* the **first** stage call carries the record's `entry_code`, which the task states;
* every **later** stage call carries the `chain_token` the previous call returned.

The chain token is a keyed hash of the class, the record and the stage. There is no way
to compute the next call's argument without having made the previous call, so a task of
depth *d* takes at least *d* calls whatever the model knows.

Every tool call returns one fixed-width line of exactly 52 bytes:

```
000002 ok           1a7d6b332220792a7a901aaf9bb6823a
 ^seq   ^status      ^payload
```

A call that is wrong -- an unknown tool, an absent record, a bad token, a stage that is
not ready -- returns a status word saying so and **changes nothing**. The domain never
half-applies a call.

Beside the stage tools the block holds **read tools** (`lookup_region`, `scan_capacity`,
...). They answer questions about a catalogue and mutate nothing. They are what the
distractor knob adds and removes.

## What a bundle carries

`generate(arm, seed)` returns a `TaskBundle`. The fields a user reads:

| field | what |
|---|---|
| `task_id` | a digest over everything below; two equal ids are the same task |
| `arm_id` | which arm generated it, e.g. `depth:d3` |
| `seed`, `split` | the draw. `eval` and `train` draw record ids from disjoint word lists, so no eval task can equal a train task |
| `system_prompt`, `prompt` | what the model is shown. `prompt` is a string on a plain arm, and a message list on a control arm, which seeds history |
| `tools` | the tool block, as JSON schemas, in the order the model sees them |
| `goal` | `(class, record_id, stage)` -- what counts as done |
| `reference_calls`, `reference_observations` | one correct solution, and what the domain returns for it |
| `negative_controls` | wrong answers, keyed by the outcome each should earn |
| `verifier` | the strictness this task is judged under |
| `pins` | the pin-ledger measurements taken off this bundle (see [knobs-and-arms.md](knobs-and-arms.md)) |
| `engine_hash`, `generator_hash` | what produced it. A run whose hashes differ from the pre-registration's is a different instrument |

`initial_state` and `expected_final_state` are the ledger before and after, as sorted
`(class, record_id, stage, token)` rows.

## The verdict

`verify(bundle, turns, ended_with_reply, turn_limit_hit, fmt)` returns a `Verdict`. It is
a pure function of those five things: no clock, no network, no model.

The outcome vocabulary is closed and **ordered**. The first label that matches wins, so
a run that both made a malformed call and ended in the wrong state is `malformed_call`:

| outcome | what happened |
|---|---|
| `verifier_error` | the verifier could not reach a verdict. An instrument condition, never a model's fault |
| `replay_mismatch` | the harness's record of the episode does not replay to the state it claims |
| `api_error` | the serving stack failed |
| `wall_timeout` | the episode ran out of wall clock |
| `malformed_call` | a call the parser or the block rejects (see the four clauses below) |
| `turn_limit` | the turn budget ran out |
| `overshoot` | the record went past the goal stage |
| `wrong_state` | the episode ended with the ledger somewhere other than the goal |
| `collateral_mutation` | the goal was reached, but something else moved too |
| `passed` | the goal, and nothing else |

The first four are conditions the instrument reports; the rest are what the model did.
`verify` itself never returns `replay_mismatch`, `api_error` or `wall_timeout` -- those
are assigned by whatever ran the episode, because its five arguments cannot see them.

**The format check** has four clauses. Clause 1 is about the raw text the model emitted
and needs the serving stack's own parser, so it is checked per model rather than here.
Clauses 2 to 4 are checked at the call level and are what the `malformed_call_clause_*`
controls exercise: a call naming a tool outside the block, a call missing a required
argument, and a call carrying an argument the schema does not allow.

**Strict and leaky.** A strict verifier passes an episode only if the ledger ends exactly
at the goal with nothing else touched. A leaky verifier passes it if the goal record
reached the goal stage, whatever else moved. A bundle carries one strictness; the verdict
reports both, as `strict_label` and `leaky_pass`, so a run can be read either way without
being generated twice.
