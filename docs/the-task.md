# What a task is

A task is a request to move one record of a mock ledger up a fixed ladder of stages,
using tools that are given to the model and nothing else. It is generated together with
its verifier, its reference solution and a set of wrong answers, from an `(arm, seed)`
pair and a fixed vocabulary table -- no model call, no network call, and the same
bytes on every run, process and platform. An **arm** is one setting of one dial (a
*knob*), such as `depth:d3`, depth at level 3 (a *level* is one setting of a knob);
the seed picks which task of that arm. [knobs-and-arms.md](knobs-and-arms.md) lists
the knobs.

`poisson-tasks generate --arm depth:d3 --show` prints all of this for one task. Read that beside this page.

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
half-applies a call. A stage call repeated on a record that has already made that stage is
one of these: it answers `not_ready` and moves nothing, so on this ledger a duplicate write
has nothing to break.

Three more status words are answered in front of the domain, by the dials that plan them,
in the same fixed-width line: `unavailable` (the faults dial: nothing changed, and the same
call works when made again), `timeout` (the timeouts dial, and on your own tools the landed
dial: whether the call went through is not known) and `rate_limited` (the ratelimits dial,
with `retry-after=1s` at the start of the payload: nothing changed, and the hint is read, not
waited on). The sequence number advances on these as on every call.

Beside the stage tools a task needs, the block holds **read tools** (`lookup_region`,
`scan_capacity`, ...), which answer questions about a catalogue and mutate nothing. The
decoy-tools dial (`distractor`) puts decoys in their place: stage tools of other ledger
classes, so at its top level the block holds the two tools the task needs, fourteen
decoys and no read tool.

## What a task carries

Generating a task gives one object holding all of it: what the model is shown (the system
prompt, the request and the tool block, in the order the model sees it), the goal, one
correct solution with what the domain returns for each call, the wrong answers the task
ships with, each keyed by the outcome it should earn, the ledger before and after, and the
hashes that say what produced it. Two tasks with equal ids are the same task.
[python.md](python.md) lists its fields.

The request is one string, or a list of messages when the arm seeds earlier conversation
into it: the history dial above level 0, and the depth and faults control arms.

## The verdict

The verdict on an episode is reached from the task and the episode alone: no clock, no
network, no model.

The outcome vocabulary is closed. Four of the labels are conditions the instrument reports,
assigned by whatever ran the episode, and never the model's fault:

| outcome | what happened |
|---|---|
| `verifier_error` | the verifier could not reach a verdict |
| `replay_mismatch` | the harness's record of the episode does not replay to the state it claims |
| `api_error` | the serving stack failed |
| `wall_timeout` | the episode ran out of wall clock |

The other six are what the model did. An episode that ends with the ledger exactly at the
goal, nothing else moved, and a final reply is `passed`, whatever happened on the way.
Otherwise the first of these that matches is the label, so an episode that both made a
malformed call and ended in the wrong state is `malformed_call`:

| outcome | what happened |
|---|---|
| `passed` | the goal, nothing else, and a final reply |
| `malformed_call` | a call the parser or the block rejects (see the clauses below) |
| `turn_limit` | the turn budget ran out before the model replied |
| `overshoot` | the record went past the goal stage |
| `wrong_state` | the episode ended with the ledger somewhere other than the goal |
| `collateral_mutation` | the goal was reached, but something else moved too |

**The format check** has four clauses. Clause 1 is about the raw text the model emitted
and needs the serving stack's own parser, so it is checked per model rather than here.
Clauses 2 to 4 are checked on each call, and are what the `malformed_call_clause_*` wrong
answers exercise: a call whose arguments are not a JSON object (clause 2), a call naming a
tool outside the block (clause 3), and a call whose arguments the tool's schema rejects,
with one missing, one it does not list, or a value that is not a string (clause 4; every
argument of the built-in tools is a string).

**Strict and leaky.** A strict verifier passes an episode only if the ledger ends exactly
at the goal with nothing else touched, and the model ended with a reply. A leaky verifier
passes it if the goal record reached the goal stage, whatever else moved. A task carries
one strictness; the verdict reports both, so a run can be read either way without the
tasks being generated twice.
