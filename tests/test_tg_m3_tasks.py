"""The frozen tests for TG-M3, task and verifier generation: G1-G16, the outcome
vocabulary, the format check and the two strictnesses.

Frozen on 2026-09-14 against spec v0 rev. 3.2 with the amendments of 2026-09-11
(TG-ADR-35, TG-ADR-36) and 2026-09-13 (TG-ADR-37, TG-ADR-38), and with TG-ADR-39,
which is a recorded decision and **not** in the spec.  The module is written against
this file, which is not edited to suit it.  Where the spec's text could not be used
as written, this docstring is authoritative.

The module is `poisson_tasks.tasks`
------------------------------------
TG-M1 is `engine.py` and TG-M2 is `knobs.py`.  2.3 is "Task and verifier generation"
and its type is `TaskBundle`, so the module is `tasks.py` rather than `generate.py`,
which would have read `from poisson_tasks.generate import generate`.

The public surface these tests pin
----------------------------------
`poisson_tasks.tasks.__all__` is exactly, and in this order::

    TaskBundle  VerifierSpec  Verdict  FormatSpec  Turn
    OUTCOMES
    generate  generate_contrast  verify  scenario_for
    structure_space  structural_fingerprint
    encode_record_id  decode_record_id

2.3's Interface list is `generate`, `verify` and `VerifierSpec.strictness`.  An extra
public symbol is a spec violation, so each of the eight beyond that list is named by an
invariant that cannot otherwise be tested, and each is recorded here:

* `TaskBundle`, `Verdict`, `FormatSpec`, `Turn` - the types 2.3's two signatures use.
* `OUTCOMES` - 2.3 says the outcome vocabulary "is closed".  Closure is a property of
  the module, and a test cannot assert a closed set the module does not name.
* `generate_contrast` - **G11's home.**  G11 is "a batch that violates any ledger row
  emits nothing", and every ledger row is an equality *across* the arms of one knob
  (TG-M2's CP2: one arm satisfies all of them vacuously).  `generate(arm, seed)` is one
  arm, so nothing in 2.3's Interface list can refuse on a ledger row at all.  The
  contrast is the unit the ledger is defined over, so it is the unit generation refuses
  on.
* `scenario_for` - **A8's home.**  The adapter's replay check needs `replay(scenario,
  calls, seq_start)` and the bundle does not carry the scenario (TG-ADR-37, TG-ADR-38).
  The scenario is drawn "from the task seed alone" (2.2's Terms), so it is a pure
  function of `(seed, split)` and re-derivable by anyone holding those two - which is
  what makes N1 true by construction rather than by check.  See *The scenario is not a
  bundle field* below.
* `structure_space` - named by G16 in those words, with its own *Test:* line.
* `structural_fingerprint` - G15 defines the fingerprint and A21 step 3 checks it per
  cell, from the notebook, over bundles it regenerated.  Neither can run on a name the
  module does not export.
* `encode_record_id`, `decode_record_id` - G14's *Test:* line is `decode(encode(s)) ==
  s` over a sweep of 2^20 seeds.  Through `generate` that is 2^20 bundles, and `decode`
  has no other route at all.

Decisions these tests make, where the spec leaves the shape open
----------------------------------------------------------------
**1. PG-16: the verdict compares the records without the audit field.**  8's open
question, opened 2026-09-11 while TG-M1 was written and assigned to this file "before
the verifier is frozen".  Option 2 of the three, which is also Taylor's recorded
non-binding lean - but not for the reason the lean gives.

The deciding argument is **N14**, not "the audit field is bookkeeping".  TG-ADR-36
makes the audit field the `seq` of the last successful transition and TG-ADR-35 makes
`seq_start` an argument N14 varies by arm, so a completed record's audit field differs
between `depth:d1+h8` and `depth:d1` by exactly `H - dL`.  Option 1 - compute
`expected_final_state` per arm - makes the bundle field differ across the two arms, so
N14's list of fields the D control may change grows from the two 2.2 names to three,
and the field that grows onto it is *the one the verdict compares*.  Option 3 - make
the audit field a call index - costs TG-ADR-36 its wording, re-opens TG-M1 two modules
back, and is not even reachable: the engine would have to know `seq_start` to subtract
it, and `DomainState` carries `next_seq` and never `seq_start` (TG-ADR-35).  Option 2
is the only one of the three that leaves N14 at the two fields 2.2 names.

**And it is information-preserving, which is the part that had to be measured rather
than asserted** (standing rule 14).  `apply` writes the audit field only inside the one
branch that also writes `stage` and `token` (`engine.py`'s `_stage_call`), so a record's
audit field moves if and only if its stage moves.  `test_pg16_2` measures that over the
status codes the engine can emit and `test_pg16_3` over random call sequences, rather
than reading it off the source - which is the half of standing rule 14 a source read
would have got wrong in either direction.  So dropping the audit field from the compared
value loses no discrimination in either place that reads it: `passed` compares the final
records, and `collateral_mutation` asks whether another record was mutated, and a record
cannot have been mutated without its stage moving.

So the shape, and it is a shape and not a comment: **a records value is a sorted tuple
of `(class, record_id, stage, token)` rows.**  There is no audit field in it.
`initial_state` and `expected_final_state` are both that.  `mutations` is TG-M1's and is
unchanged - it still reports `(class, id, "audit")` triples, and `Verdict.mutations`
still carries them, because that field is diagnostic output and not the predicate.

**2. The scenario is not a bundle field, and it is a pure function of `(seed, split)`.**
2.3 says a consumer holding only the bundle cannot re-derive the reference observations,
because the bundle does not carry the scenario.  Taken alone that also makes `verify`
impossible - it has to reach the engine to know the final records, and `replay` and
`init_state` both need a scenario - and makes A8's adapter-side replay impossible for
the same reason.  2.2's Terms resolve it: the scenario is "everything drawn from the
task seed alone", so it is a derivation and not a datum.  `scenario_for(seed, split)`
is that derivation, `verify` calls it with `bundle.seed` and `bundle.split`, and G9 is
untouched - the verdict still depends on nothing outside the bundle and the turns.

This is also what makes N1 hold **by construction**: the arm is not an argument to
`scenario_for`, so no arm transform can move a scenario.  `test_g3_1` pins the signature
for exactly that reason.

**3. `verify` assigns seven of the ten outcomes.  Three are the adapter's.**  The
vocabulary is closed at ten and shared with TG-M5, so `OUTCOMES` carries all ten in
2.3's table order.  But `replay_mismatch` is E8's and 2.5 step 6 runs the replay check
*before* computing the verdict; `api_error` and `wall_timeout` are A4's fault-injection
labels and name conditions - a transport failure, a wall-clock deadline - that `verify`'s
five arguments cannot express.  So `verify` returns one of `verifier_error`,
`malformed_call`, `turn_limit`, `overshoot`, `wrong_state`, `collateral_mutation`,
`passed`, and `test_g10_3` asserts it never returns the other three.  Naming the split
is what stops a later build from quietly assigning an instrument label from inside the
verifier, which A4 exists to prevent.

**4. `malformed_call` is evaluated after pass/fail, not before it.**  The table says the
first matching label wins and lists `malformed_call` above `passed`, and
`malformed_call`'s own definition opens "the episode fell short of `passed`".  Both are
satisfied only if the strict predicate is computed first and the label order is applied
to what is left.  So a turn that fails the format check in an episode that otherwise
passes is `passed`, and `Verdict.format_clause` still names the clause that fired.

**5. The optional `spec` argument.**  G16's *Test:* line runs the census and the
chi-square "on a reduced vocabulary, where brute force is possible".  Nothing in 2.3
offers a route to one, so `generate`, `generate_contrast`, `scenario_for` and
`structure_space` each take `spec: EngineSpec | None = None`, defaulting to the frozen
table.  `EngineSpec.from_mapping` is TG-M1's and already builds a spec from any table.

**6. `generate` generates both splits.**  G12 says "v0 emits `eval` only", which is the
pre-registration's choice among what the generator offers, in the same shape as
TG-ADR-39 (2): TG-M2 declined to check a level against `levels(knob)` because 2.2 calls
those the *candidate* levels.  G12's own first clause - eval and train draw from two
disjoint lists, so no eval instance can equal a train instance - is a statement about
both splits and is untestable if one of them refuses.  *Escape hatch:* one line in
`generate`, and `test_g12_4` is the test that would move.

**7. `negative_controls` carries a declared closed label set, and `overshoot` is absent
at the top stage.**  G8 wants one control per system label; the labels a call sequence
can produce are `overshoot`, `wrong_state`, `collateral_mutation`, `turn_limit` and
`malformed_call` at clauses 2, 3 and 4 - seven.  `passed` is `reference_calls` itself and
`verifier_error` is fault-injected, so neither is a generated control.  At a goal of the
last stage there is no stage above it, so **`overshoot` is not generated at stage 8** and
G7's leaky-accepts-strict-rejects pair is carried by `collateral_mutation` alone there.
`test_g7_2` is what pins that, so a reader does not later read the missing key as a bug.

**8. The lowest-numbered format clause that fired is the one reported.**  2.3 numbers
the four clauses and then writes "the clause that fired", singular, while one call can
break two at once - a tool outside the block whose arguments are also not an object.
Without a rule the reported clause is whatever the implementation checked first, and two
runs of the same episode under two builds would report different clauses for the same
call.  `test_fc_5` pins it.

**9. The tool block is the target class's stage tools plus the orthogonal reads, and
`K_D = 16` is what that comes to on the frozen table.**  2.2 writes knob D's block as
"the target class's 8 stage tools" plus "8 orthogonal read tools", `K_D = 16` - three
literals that are all consequences of the frozen table having 8 stages.  Built as a
count, the generator cannot run on the reduced vocabulary decision 5 needs; built as the
rule, `K_D` is TG-M2's literal cited and not re-minted (`test_sf9`), and the reduced
table works by construction.

**10. The scenario carries the target record id in every ledger class, under one entry
code.**  TG-M1 left this open in as many words - "whether one id may exist in several
classes is a scenario question, and TG-M2 answers it" - and TG-M2 draws no scenarios, so
it arrives here.  It is forced: a functional distractor is a required tool's twin in
another class (2.2), E7 rejects a call against a record that does not exist rather than
redirecting it, and `collateral_mutation` is how distractor misuse becomes observable.
If the id lived in the target class alone, every distractor call would be `no_such_rec`,
no negative control could produce `collateral_mutation`, and G8 would fail on a label the
whole of knob R rests on.  The shared entry code is the same argument one level down: a
distractor that mirrors the required tool exactly has to be able to *succeed*.

**11. Two named seams, and why a frozen test file names them.**  `generate` calls the
module-global `verify` for G4's gate, and the module-global `_check_pins` - TG-M2's
`check_pins`, aliased under an underscore the way `knobs.py` itself aliases its imports -
for G11's.  Both are fault-injected (`test_g4_4`, `test_g11_1`), because the alternative
is a deliberately broken generator as a fixture, and a gate that is only exercised by a
correct generator is not a gate.  Naming a private alias in a test is a cost; the
escape hatch is a build that routes both through some other injectable seam, in which
case those two tests move and nothing else does.

**12. `verify` rebuilds the starting state and checks the bundle against it.**  The
verifier derives `init_state(scenario_for(seed, split), seq_start)` and asserts its
records value equals `bundle.initial_state`.  A bundle whose stored initial state
disagrees with its own derivation is a defective bundle, not a failed episode, so it is
`verifier_error` and never a system label (`test_g10_2`).

Shapes the spec names but does not define
-----------------------------------------
* ``TaskBundle`` is frozen and carries 2.3's fields in 2.3's order, plus nothing:
  ``task_id arm_id seed split scenario_hash system_prompt prompt tools seq_start
  template_id prompt_slots initial_state expected_final_state goal reference_calls
  reference_observations negative_controls verifier pins engine_hash generator_hash``.
  ``pins`` is TG-M2's ``PinRecord``.
* ``goal`` is ``(ledger class, record id, stage index)``.  2.3 names the field and never
  its shape, and every label in the table is written against "the target record" and "the
  goal stage", so the verdict needs both and the class is in the key (TG-ADR-36).
* ``Turn(content, calls, finish_reason)``, frozen.  ``calls`` is a tuple of
  ``(name, arguments)`` pairs, the engine's own call shape, with ``arguments`` left as
  parsed so that format-check clause 2 - arguments that are not a JSON object - is
  representable at all.
* ``FormatSpec(name, markers)``, frozen.  ``markers`` is the call markers the pinned
  parser extracts: ``("<tool_call>", "<function=")`` for ``qwen3_coder`` and
  ``("[TOOL_CALLS]",)`` for ``mistral``.
* ``VerifierSpec(strictness)``, frozen, one field.  2.3 names only ``strictness`` and
  TG-M2's N11 reads only ``strictness``.  The target and the goal live on the bundle.
* ``Verdict(strict_label, leaky_pass, label, mutations, format_clause)``, frozen.
  ``format_clause`` is the integer clause that fired, or ``None``.
* ``negative_controls`` is a ``dict[str, tuple]`` as 2.3 writes it, keyed by the labels
  above.
* A **records value** is a sorted tuple of ``(class, record_id, stage, token)``.  See
  decision 1.

What is deliberately not tested here
------------------------------------
* **N17's scripted `diff` and N18's revision predicate.**  Both are filed at 2.5 as
  owed to TG-M5's tests, and **nothing covers either one today**.  This file does
  not either: TG-M3 imports nothing from Proofload and no model string reaches a bundle.
  `test_n18_3` asserts that TG-M3, like TG-M2 before it, holds **no** revision
  predicate, so the gap stays visible and a later reader cannot take two modules'
  silence for coverage.  TG-M2's `n18_2` makes the same assertion about TG-M2 and this
  file does not weaken it.
* **Format-check clause 1's generated control.**  G8 assigns clauses 2-4 to TG-M3 "at
  the call level" and sends clause 1 - content carrying the markers with no parsed call -
  through each model's stack at stage 0b, because it depends on the family's raw format
  (A16).  The *clause* is pinned here with a synthetic turn (`test_fc_1`); the
  *generated negative control* for it is not, and `test_g8_2` pins that
  `negative_controls` carries clauses 2, 3 and 4 and not clause 1.
* **Whether a real cell's `k` clears `100*N**2`.**  G16's threshold is pinned as a
  literal and `structure_space` is pinned against a brute-force count on a reduced
  vocabulary.  The census over the pilot's real arms is a run, not a test (KC14).
* **The mutation pass.**  G8's "a clause no control catches is a build failure" is a
  report, not an assertion in this file: the mutation table is kept with the project's
  records, and re-run against `src/` as built.
"""

from __future__ import annotations

import ast
import collections
import dataclasses
import functools
import inspect
import json
import math
import os
import pathlib
import subprocess
import sys
import textwrap

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# --------------------------------------------------------------------------
# frozen literals
# --------------------------------------------------------------------------

DATA = pathlib.Path(__file__).resolve().parent.parent / "src" / "poisson_tasks" / "data"
TABLE_PATH = DATA / "vocabulary-v2.json"
TABLE = json.loads(TABLE_PATH.read_text())
L_OBS = TABLE["L_obs"]
BAND_LO, BAND_HI = TABLE["token_band"]
STAGE_NAMES = tuple(TABLE["stage_names"])
QUALIFIERS = tuple(TABLE["qualifiers"])
ENTRY_CODES = tuple(TABLE["entry_codes"])
CATALOGUE_ITEMS = tuple(TABLE["catalogue_items"])
PAGE_KEYS = tuple(sorted(TABLE["page_keys"]))
N_STAGES = len(STAGE_NAMES)

TASKS_EXPORTS = (
    "TaskBundle", "VerifierSpec", "Verdict", "FormatSpec", "Turn",
    "OUTCOMES",
    "generate", "generate_contrast", "verify", "scenario_for",
    "structure_space", "structural_fingerprint",
    "encode_record_id", "decode_record_id",
)
# `from __future__ import annotations` binds the name `annotations` in the module.  The
# same exception TG-M2's SF2 makes, and for the same reason: it is a compiler directive,
# not a symbol a caller could use.
FUTURE_NAMES = ("annotations",)

# 2.3's Interface list, and the fields a bundle carries, in 2.3's order.  TG-ADR-38's
# three - `template_id`, `prompt_slots`, `reference_observations` - are in the spec now
# and are not drafted here.
BUNDLE_FIELDS = (
    "task_id", "arm_id", "seed", "split", "scenario_hash",
    "system_prompt", "prompt", "tools", "seq_start",
    "template_id", "prompt_slots",
    "initial_state", "expected_final_state", "goal",
    "reference_calls", "reference_observations", "negative_controls",
    "verifier", "pins", "engine_hash", "generator_hash",
)

# 2.3's outcome vocabulary, closed, in the table's order.  The first label that matches
# wins, so this order is load-bearing and not decoration.
OUTCOME_ORDER = (
    "verifier_error",
    "replay_mismatch",
    "api_error",
    "wall_timeout",
    "malformed_call",
    "turn_limit",
    "overshoot",
    "wrong_state",
    "collateral_mutation",
    "passed",
)
INSTRUMENT_OUTCOMES = ("verifier_error", "replay_mismatch", "api_error", "wall_timeout")
SYSTEM_OUTCOMES = (
    "malformed_call", "turn_limit", "overshoot", "wrong_state", "collateral_mutation",
    "passed",
)
# The three the adapter assigns and `verify` must never return.  `replay_mismatch` is
# E8's and 2.5 runs the replay check before the verdict; `api_error` and `wall_timeout`
# are A4's, and name conditions `verify`'s five arguments cannot express.
ADAPTER_ONLY_OUTCOMES = ("replay_mismatch", "api_error", "wall_timeout")
VERIFIER_OUTCOMES = tuple(o for o in OUTCOME_ORDER if o not in ADAPTER_ONLY_OUTCOMES)

# G8: one generated negative control per system label a call sequence can produce.
# `passed` is `reference_calls` itself and `verifier_error` is fault-injected, so
# neither is generated.  Clause 1 of the format check is stage 0b's (A16).
NEGATIVE_CONTROL_LABELS = (
    "overshoot",
    "wrong_state",
    "collateral_mutation",
    "turn_limit",
    "malformed_call_clause_2",
    "malformed_call_clause_3",
    "malformed_call_clause_4",
)

# 2.3's format check.  Four clauses, numbered as the spec numbers them.
FORMAT_CLAUSES = (1, 2, 3, 4)

# 2.5's two pinned parsers and the markers each extracts.
QWEN_FMT = ("qwen3_coder", ("<tool_call>", "<function="))
MISTRAL_FMT = ("mistral", ("[TOOL_CALLS]",))

# 2.2 and TG-ADR-16.  Candidate levels, not the pilot defaults.
DEPTH_LEVELS = (1, 2, 3, 5, 8)
DISTRACTOR_LEVELS = (0, 2, 4, 8, 14)
K_D = 16
K_R = 16
D_R = 2
SLACK = 4  # 8: `S = 4`, answered in rev. 3

# G16's threshold, written out rather than computed, so a build cannot satisfy it by
# redefining the arithmetic.  "Far larger than N" means k >= 100*N**2.
N_PILOT = 93
N_PROBE = 27
K_FLOOR_PILOT = 864_900
K_FLOOR_PROBE = 72_900

# G14.  A record id is four words from the split's frozen 256-word list, joined by the
# table's separator, encoding a 32-bit seed as base-256 digits.
WORD_LIST_SIZE = 256
RECORD_ID_WORDS = TABLE["record_id_word_count"]
RECORD_ID_SEPARATOR = TABLE["record_id_separator"]
SEED_SPACE = WORD_LIST_SIZE ** RECORD_ID_WORDS
G14_SWEEP = 1 << 20

GEN_VERSION = "0.0.1"
STRICTNESS = ("strict", "leaky")
SPLITS = ("eval", "train")


# --------------------------------------------------------------------------
# the shared helpers
# --------------------------------------------------------------------------


def tasks():
    """The module under test.  Imported here and not at module scope, so this file
    still collects on a bare tree while every test in it fails."""
    import poisson_tasks.tasks as m

    return m


def knobs():
    import poisson_tasks.knobs as m

    return m


def engine():
    import poisson_tasks.engine as m

    return m


@functools.lru_cache(maxsize=2)
def es():
    """The frozen spec, built once.  `EngineSpec.load` parses the whole vocabulary
    table, and the property tests below reach for it per example."""
    return engine().EngineSpec.load()


def encoding():
    from poisson_tasks.tokenizer import reference_encoding

    return reference_encoding()


def ntok(text: str) -> int:
    return len(encoding().encode(text))


def spec(knob="depth", level=3, control=None, strictness="strict", split="eval"):
    return knobs().ArmSpec(
        knob=knob, level=level, control=control,
        strictness=strictness, split=split, generator_version=GEN_VERSION,
    )


def depth_arms(low=1, high=8, control=True, **kw):
    """The pilot's shape: the low arm, the high arm and the low+high control."""
    arms = [spec(level=low, **kw), spec(level=high, **kw)]
    if control:
        arms.append(spec(level=low, control=high, **kw))
    return tuple(arms)


def distractor_arms(low=0, high=8, control=True, **kw):
    arms = [spec(knob="distractor", level=low, **kw), spec(knob="distractor", level=high, **kw)]
    if control:
        arms.append(spec(knob="distractor", level=low, control=high, **kw))
    return tuple(arms)


def records_of(bundle_or_value):
    """A records value as a dict, from a bundle field or from a bundle.

    A records value is a sorted tuple of `(class, record_id, stage, token)` (decision 1).
    """
    value = getattr(bundle_or_value, "expected_final_state", bundle_or_value)
    return {(row[0], row[1]): (row[2], row[3]) for row in value}


def target_of(bundle):
    """The `(class, record_id)` the goal names."""
    return (bundle.goal[0], bundle.goal[1])


def goal_stage(bundle) -> int:
    return bundle.goal[2]


def turn(calls=(), content="", finish_reason="tool_calls"):
    return tasks().Turn(content=content, calls=tuple(calls), finish_reason=finish_reason)


def turns_for(calls, content=""):
    """One call per turn.  N16's minimum is exactly this: each call waits on the previous
    call's token, so each needs its own turn.

    An episode that made no call is still one turn, not none: format-check clause 1 is a
    statement about a turn that carries a marker and parses to nothing, and a fixture
    with no turns at all cannot make it.
    """
    if not calls:
        return (turn(calls=(), content=content),)
    return tuple(turn(calls=(call,), content=content) for call in calls)


def fmt(pair=QWEN_FMT):
    return tasks().FormatSpec(name=pair[0], markers=tuple(pair[1]))


def run(bundle, calls, *, ended_with_reply=True, turn_limit_hit=False, spec_fmt=QWEN_FMT,
        content=""):
    """Verify a call sequence as an episode that ran it one call per turn."""
    return tasks().verify(
        bundle, turns_for(calls, content=content),
        ended_with_reply=ended_with_reply, turn_limit_hit=turn_limit_hit,
        fmt=fmt(spec_fmt),
    )


def reduced_table(n_stages=2, n_qualifiers=2, n_reads=2, n_items=2, n_pages=2):
    """A reduced vocabulary table, for G16's brute-force count and chi-square.

    Brute force over the real table is not possible - 16 slots alone give 16! orders -
    and G16's own *Test:* line says both run on a reduced vocabulary.  Everything the
    engine validates is kept consistent: the status-code set is untouched, the layout is
    untouched, and every name still comes from the frozen table's own words (E6).
    """
    t = json.loads(json.dumps(TABLE))
    t["stage_names"] = list(STAGE_NAMES[:n_stages])
    t["qualifiers"] = list(QUALIFIERS[:n_qualifiers])
    t["read_verbs"] = list(TABLE["read_verbs"][:n_reads])
    t["facets"] = list(TABLE["facets"][:n_reads])
    t["catalogue_items"] = list(CATALOGUE_ITEMS[:n_items])
    t["catalogue_values"] = {k: TABLE["catalogue_values"][k] for k in t["catalogue_items"]}
    t["page_keys"] = list(PAGE_KEYS[:n_pages])
    t["vocabulary_version"] = "v1-reduced"
    return t


@functools.lru_cache(maxsize=4)
def reduced_spec(**kw):
    """Cached: `from_mapping` re-canonicalises the whole table, and G16's draws ask for
    it once per generate otherwise."""
    return engine().EngineSpec.from_mapping(reduced_table(**kw))


def chi_square_p(counts, k):
    """A chi-square goodness-of-fit p-value against the uniform over `k` cells.

    Computed here rather than imported, because scipy is not a dependency and the whole
    point of G16's uniformity clause is that the draws are checked, not asserted.  The
    survival function of chi-square with `k - 1` degrees of freedom, by the regularised
    upper incomplete gamma function `Q(df/2, x/2)`, which `math.gamma` and a series give
    to well past the precision a p-value needs.
    """
    n = sum(counts)
    expected = n / k
    stat = sum((c - expected) ** 2 / expected for c in counts)
    return _gamma_q((k - 1) / 2.0, stat / 2.0)


def _gamma_q(s, x):
    """Q(s, x), the regularised upper incomplete gamma function."""
    if x <= 0:
        return 1.0
    if x < s + 1.0:
        # the series for P(s, x), then Q = 1 - P
        term = 1.0 / s
        total = term
        n = 0
        while n < 10_000:
            n += 1
            term *= x / (s + n)
            total += term
            if abs(term) < abs(total) * 1e-15:
                break
        return 1.0 - total * math.exp(-x + s * math.log(x) - math.lgamma(s))
    # the continued fraction for Q(s, x)
    tiny = 1e-300
    b = x + 1.0 - s
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 10_000):
        an = -i * (i - s)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    return h * math.exp(-x + s * math.log(x) - math.lgamma(s))


# --------------------------------------------------------------------------
# SF - the public surface, and what the module may not reach
# --------------------------------------------------------------------------


def test_sf1_all_is_exactly_the_specs_interface_list_plus_the_eight_named():
    """The surface is 2.3's list, the types its signatures use, and the eight the
    module docstring justifies one by one.  An extra public symbol is a spec violation.
    """
    assert tuple(tasks().__all__) == TASKS_EXPORTS


def test_sf2_no_public_symbol_beyond_all():
    m = tasks()
    public = {n for n in vars(m) if not n.startswith("_")}
    assert public - set(TASKS_EXPORTS) - set(FUTURE_NAMES) == set()


def test_sf3_the_five_types_are_frozen():
    m = tasks()
    for name in ("TaskBundle", "VerifierSpec", "Verdict", "FormatSpec", "Turn"):
        cls = getattr(m, name)
        assert dataclasses.is_dataclass(cls), name
        assert cls.__dataclass_params__.frozen, name


def test_sf4_task_bundle_carries_2_3s_fields_and_no_others():
    """2.3's Interface list, in 2.3's order, with TG-ADR-38's three among them.

    The order is asserted because 2.3 writes one and a reader checking a bundle against
    the spec reads them in that order.  A field beyond the list is a spec violation in
    the same way an extra public symbol is - and the two fields named below are the two
    a build would most plausibly add: the scenario, which TG-ADR-37 keeps out, and an
    audit field, which PG-16 decides against.
    """
    fields = tuple(f.name for f in dataclasses.fields(tasks().TaskBundle))
    assert fields == BUNDLE_FIELDS
    for late in ("template_id", "prompt_slots", "reference_observations"):
        assert late in fields, late
    assert "scenario" not in fields
    assert "audit" not in fields


def test_sf5_verifier_spec_carries_strictness_alone():
    fields = tuple(f.name for f in dataclasses.fields(tasks().VerifierSpec))
    assert fields == ("strictness",)


def test_sf6_verdict_carries_the_five_fields_2_3_names():
    fields = tuple(f.name for f in dataclasses.fields(tasks().Verdict))
    assert fields == ("strict_label", "leaky_pass", "label", "mutations", "format_clause")


def test_sf7_the_two_signatures_are_the_specs():
    """`generate(arm, seed)` and `verify(bundle, turns, ended_with_reply, turn_limit_hit,
    fmt)`, with the one optional `spec` decision 5 adds and nothing else."""
    m = tasks()
    assert tuple(inspect.signature(m.generate).parameters) == ("arm", "seed", "spec")
    assert inspect.signature(m.generate).parameters["spec"].default is None
    assert tuple(inspect.signature(m.verify).parameters) == (
        "bundle", "turns", "ended_with_reply", "turn_limit_hit", "fmt", "spec",
    )
    assert inspect.signature(m.verify).parameters["spec"].default is None
    assert tuple(inspect.signature(m.scenario_for).parameters) == ("seed", "split", "spec")


def test_sf8_generation_imports_no_network_no_model_and_no_verifiers():
    """G2's static half, and the rule that generation makes no model or network call.
    An `ast` walk over every import in the module: no `verifiers`, no network library,
    no `proofload`, and nothing that could make generation non-deterministic."""
    source = pathlib.Path(inspect.getfile(tasks())).read_text()
    banned = {
        "verifiers", "requests", "urllib", "socket", "aiohttp", "http", "proofload",
        "random", "time", "datetime", "secrets", "uuid", "openai",
    }
    seen = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            seen |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            seen.add(node.module.split(".")[0])
    assert seen & banned == set(), sorted(seen & banned)
    assert {"poisson_tasks"} & seen or any(
        n.startswith("poisson_tasks") for n in seen
    ), "TG-M3 reaches TG-M1 and TG-M2 by import, and mints neither's literals"


def test_sf9_tg_m1_and_tg_m2_literals_are_cited_and_not_re_minted():
    """TG-M3 mints no literal another module already froze.

    `L_obs` and the token band are TG-M1's; the candidate levels, `K_D`, `K_R`, `d_R`
    and N9's band are TG-M2's.  A second copy here would be a number read back and
    compared with itself (standing rule 8), and the two copies would drift silently on
    the next vocabulary version.  Checked at module level only: a local computing a
    width is not a second freeze.
    """
    source = pathlib.Path(inspect.getfile(tasks())).read_text()
    minted = set()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            for const in ast.walk(node.value) if node.value is not None else ():
                if isinstance(const, ast.Constant) and isinstance(const.value, int):
                    minted.add(const.value)
    assert L_OBS not in minted, f"L_obs ({L_OBS}) is TG-M1's; cite it, do not re-mint it"
    assert BAND_LO not in minted and BAND_HI not in minted
    assert DEPTH_LEVELS[-1] not in minted or "levels" in source


# --------------------------------------------------------------------------
# G1, G2 - determinism, and no model or network
# --------------------------------------------------------------------------


def canon(value):
    """Every bundle field as JSON-able data, deterministically."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: canon(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): canon(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [canon(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def bundle_bytes(bundle) -> bytes:
    """A canonical rendering of a whole bundle, for G1's byte equality.

    Built from the public fields only, so it is independent of whatever `task_id`
    happens to cover: G1 asserts on both, and a `task_id` that missed a field cannot
    hide that field's drift from this.
    """
    return json.dumps(canon(bundle), sort_keys=True, separators=(",", ":")).encode("utf-8")


# `task_id`'s construction, pinned the way TG-M1 pinned `engine_hash`'s: a domain
# separator and a canonical form over every field but the id itself.  TG-ADR-38 leaves
# it to TG-M3 to state whether the id covers its three new fields, and the answer is
# yes, by covering all twenty.  It has to be pinned as a construction rather than
# measured as a difference: all three fields are determined by the arm, the scenario and
# the engine, so no pair of bundles differing only in one of them exists to compare.
# The separator keeps the pre-rename spelling on purpose: it is tasks.py's literal,
# and those bytes are hash input rather than a name (2026-09-22).
TASK_ID_DOMAIN = b"task-generator/task_id/1\n"


def task_id_input(bundle) -> bytes:
    body = {k: v for k, v in canon(bundle).items() if k != "task_id"}
    return TASK_ID_DOMAIN + json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def test_g1_1_generate_repeats_within_one_process():
    a = spec(level=3)
    assert tasks().generate(a, 12345) == tasks().generate(a, 12345)


_CHILD = textwrap.dedent(
    """
    import hashlib, json, sys
    sys.path.insert(0, {tests!r})
    import test_tg_m3_tasks as O
    import poisson_tasks.tasks as T

    b = T.generate(O.spec(level={level}), {seed})
    print(json.dumps({{
        "file": T.__file__,
        "task_id": b.task_id,
        "digest": hashlib.sha256(O.bundle_bytes(b)).hexdigest(),
    }}))
    """
)


def _run_child(level, seed, hashseed):
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = hashseed
    src = _CHILD.format(
        tests=str(pathlib.Path(__file__).resolve().parent), level=level, seed=seed,
    )
    p = subprocess.run([sys.executable, "-c", src], capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def test_g1_2_two_processes_and_two_hash_seeds_agree_byte_for_byte():
    """G1: byte-identical across runs and processes.  Two children at PYTHONHASHSEED 0
    and 1, because a set or dict iteration order that leaked into a rendered prompt, a
    slot order or a hash would show up here and nowhere else."""
    a = _run_child(3, 777, "0")
    b = _run_child(3, 777, "1")
    assert a["digest"] == b["digest"]
    assert a["task_id"] == b["task_id"]
    assert a["file"] == b["file"]


def test_g1_3_task_id_is_a_content_hash_that_moves_with_the_content():
    """`task_id` is stable, and it is a *content* hash: two bundles that differ in
    anything a consumer can see have different ids."""
    m = tasks()
    base = m.generate(spec(level=3), 21)
    assert base.task_id == m.generate(spec(level=3), 21).task_id
    others = [
        m.generate(spec(level=3), 22),
        m.generate(spec(level=5), 21),
        m.generate(spec(level=3, control=8), 21),
        m.generate(spec(level=3, split="train"), 21),
        m.generate(spec(level=3, strictness="leaky"), 21),
    ]
    assert len({base.task_id} | {o.task_id for o in others}) == 1 + len(others)


def test_g1_4_task_id_is_the_digest_of_every_other_field():
    """TG-ADR-38 asks TG-M3 to state whether `task_id` covers its three fields.  It
    covers all twenty, because it is taken over the whole bundle rather than a listed
    subset - so a field added later is covered without anyone remembering to add it.

    Recomputed here independently, the way TG-M1's tests recompute `engine_hash`, so
    the claim is measured rather than read off the source.
    """
    import hashlib

    for arm, seed in ((spec(level=3), 21), (spec(level=1, control=8), 4), (spec(level=8), 99)):
        b = tasks().generate(arm, seed)
        assert b.task_id == hashlib.sha256(task_id_input(b)).hexdigest()


def test_g1_5_task_id_moves_when_any_one_field_moves():
    """The other direction, and the one that makes `test_g1_4` more than a restatement:
    perturb one field of a real bundle and the recomputed digest moves.  Run over
    TG-ADR-38's three, which are the fields the question was about."""
    import hashlib

    b = tasks().generate(spec(level=3), 21)
    for field, value in (
        ("template_id", b.template_id + ".x"),
        ("prompt_slots", b.prompt_slots + (("extra", "word"),)),
        ("reference_observations", b.reference_observations[:-1]),
    ):
        moved = dataclasses.replace(b, **{field: value})
        assert hashlib.sha256(task_id_input(moved)).hexdigest() != b.task_id, field


def test_g2_1_generation_runs_with_sockets_disabled():
    """G2: generation makes no model call and no network call, and a test enforces it.

    The static half is `test_sf8`.  This is the dynamic half: a fresh interpreter in
    which every `socket.socket` raises, so a generator that opened one - directly or
    through a library the static scan missed - fails here.  A fresh interpreter because
    the reference encoding is cached, and it has to be built under the dead socket too.
    """
    src = textwrap.dedent(
        f"""
        import socket, sys
        class _Dead(socket.socket):
            def __init__(self, *a, **k):
                raise OSError("G2: generation opened a socket")
        socket.socket = _Dead
        socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(OSError("G2"))
        sys.path.insert(0, {str(pathlib.Path(__file__).resolve().parent)!r})
        import test_tg_m3_tasks as O
        import poisson_tasks.tasks as T
        print(T.generate(O.spec(level=3), 5).task_id)
        """
    )
    p = subprocess.run([sys.executable, "-c", src], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip()


def test_g2_2_verify_is_pure_within_one_process():
    """G9's other half: two verdicts over equal inputs are equal.  A verifier that read
    a clock, an RNG or a file would not be."""
    b = tasks().generate(spec(level=3), 9)
    assert run(b, b.reference_calls) == run(b, b.reference_calls)


# --------------------------------------------------------------------------
# G3 - scenario independence, and N14's field-by-field diff
# --------------------------------------------------------------------------

# N14 as it falls on a real bundle.  2.2 writes N14 over "the fields its definition
# names", and the definition's fields are the *knob's* - goal stage, required count,
# prompt `Messages`, `seq_start`, designated slots, filler.  A bundle has twenty-one
# fields, so the diff has to say which bundle field each of those reaches.  Three
# partitions, and every bundle field is in exactly one of them:
#
#   INDEPENDENT   equal across any two arms of one knob at one seed.  These are the
#                 pins: N1 (`scenario_hash`), N3 (`system_prompt`), N4 (`tools`),
#                 N6 (`template_id`), N11 (`verifier`), N12 (the two hashes), plus the
#                 seed, the split and `initial_state`, which no arm transform touches.
#   IDENTITY      moves with the arm by definition: the arm id, the content hash over
#                 it, and the pin record measured from it.
#   TRANSFORMED   may move, and only because a field the knob's definition names moved.
#
# `expected_final_state` is TRANSFORMED, because the goal stage is what it records and
# the goal stage is the knob.  What PG-16 decides is the *other* comparison: it does not
# move between `depth:d1` and `depth:d1+h8`, which are at one level and differ only in
# `seq_start`, so N14 stays at the two fields 2.2 names for the D control.  That is
# `test_pg16_1`, and it is the assertion option 1 would have had to give up.
N14_INDEPENDENT = (
    "seed", "split", "scenario_hash", "system_prompt", "tools", "template_id",
    "initial_state", "verifier", "engine_hash", "generator_hash",
)
N14_IDENTITY = ("arm_id", "task_id", "pins")
N14_TRANSFORMED = (
    "prompt", "seq_start", "prompt_slots", "goal", "expected_final_state",
    "reference_calls", "reference_observations", "negative_controls",
)


def test_n14_0_the_three_partitions_cover_every_bundle_field_exactly_once():
    """The control for the three tests below.  Without it a field could be dropped from
    all three lists and every N14 test would still pass while nothing checked it."""
    partitioned = N14_INDEPENDENT + N14_IDENTITY + N14_TRANSFORMED
    assert len(partitioned) == len(set(partitioned)) == len(BUNDLE_FIELDS)
    assert set(partitioned) == set(BUNDLE_FIELDS)


def test_g3_1_the_scenario_is_a_function_of_the_seed_and_the_split_alone():
    """2.2's Terms: the scenario is "everything drawn from the task seed alone".  So the
    arm is not an argument, and N1 - scenario equality across a knob's arms - holds by
    construction rather than by check.  `test_g3_2` is the check anyway, because a
    generator could still draw *outside* `scenario_for`."""
    m = tasks()
    assert tuple(inspect.signature(m.scenario_for).parameters) == ("seed", "split", "spec")
    assert m.scenario_for(11, "eval") == m.scenario_for(11, "eval")
    assert m.scenario_for(11, "eval") != m.scenario_for(12, "eval")
    assert m.scenario_for(11, "eval") != m.scenario_for(11, "train")


def test_g3_2_every_depth_arm_at_one_seed_shares_one_scenario_hash():
    """N1, through the arms the pilot actually sweeps."""
    made = tasks().generate_contrast(depth_arms(1, 8), 404)
    assert len({b.scenario_hash for b in made.values()}) == 1
    assert len(made) == 3


def test_g3_3_every_distractor_arm_at_one_seed_shares_one_scenario_hash():
    made = tasks().generate_contrast(distractor_arms(0, 8), 404)
    assert len({b.scenario_hash for b in made.values()}) == 1
    assert len(made) == 3


def test_g3_4_a_generated_depth_contrast_satisfies_the_whole_ledger():
    """G3 says N1, N2 and N14 hold for every generated batch, and the ledger is how they
    are measured.  `check_pins` over the generated contrast refuses nothing and reports
    nothing - which is TG-M2's CP5, run for the first time against real bundles."""
    report = knobs().check_pins(tasks().generate_contrast(depth_arms(1, 8), 55))
    assert report.refused is False, report.violations
    assert report.violations == ()
    assert report.reported == ()


def test_g3_5_a_generated_distractor_contrast_refuses_nothing():
    """Knob R's, where N5 *reports* the tool-block token difference rather than refusing
    it - so this contrast is the one where `reported` is allowed to be non-empty."""
    report = knobs().check_pins(tasks().generate_contrast(distractor_arms(0, 8), 55))
    assert report.refused is False, report.violations
    assert [row for row, _ in report.reported] in ([], ["N5"])


def test_n14_1_the_level_diff_moves_only_transformed_fields():
    """d1 against d8: the knob changes the goal stage and the required count, and every
    INDEPENDENT field is equal across them."""
    made = tasks().generate_contrast(depth_arms(1, 8, control=False), 77)
    low, high = made["depth:d1"], made["depth:d8"]
    for field in N14_INDEPENDENT:
        assert getattr(low, field) == getattr(high, field), field
    for field in N14_IDENTITY:
        assert getattr(low, field) != getattr(high, field), field
    assert low.goal[2] == 1 and high.goal[2] == 8
    assert target_of(low) == target_of(high)


def test_n14_2_the_d_control_moves_only_its_prompt_and_seq_start():
    """N14's D-control row, and the reason PG-16 had to be decided here.

    2.2 lets the D control change the prompt `Messages` and `seq_start`, and nothing
    else.  `reference_observations` moves with them, because the control's reference
    episode starts at `seq_start = H - dL + 1` and an observation carries its `seq` -
    which is a field the definition names moving, not a second one appearing.
    `reference_calls` does **not** move: the control runs its own `dL` chain from stage
    0, on the same scenario, so it makes the same calls.
    """
    made = tasks().generate_contrast(depth_arms(1, 8), 77)
    plain, control = made["depth:d1"], made["depth:d1+h8"]
    for field in N14_INDEPENDENT:
        assert getattr(plain, field) == getattr(control, field), field
    assert plain.prompt != control.prompt
    assert plain.seq_start == 1
    assert control.seq_start == 8
    assert plain.reference_calls == control.reference_calls
    assert plain.reference_observations != control.reference_observations
    assert plain.goal == control.goal
    assert plain.prompt_slots == control.prompt_slots
    assert plain.negative_controls == control.negative_controls
    assert plain.expected_final_state == control.expected_final_state


def test_pg16_1_expected_final_state_is_equal_across_the_d_control_and_its_plain_arm():
    """**PG-16, decided.**  The verdict's compared value carries no audit field, so it
    does not move with `seq_start`, so N14's list for the D control stays at the two
    fields 2.2 names.  That is the whole of the decision, and this is the test that
    would move if a later build took option 1 instead."""
    made = tasks().generate_contrast(depth_arms(1, 8), 78)
    plain, control = made["depth:d1"], made["depth:d1+h8"]
    assert plain.expected_final_state == control.expected_final_state
    assert plain.initial_state == control.initial_state
    rows = {len(row) for row in plain.expected_final_state}
    assert rows == {4}, "a records row is (class, record_id, stage, token) and nothing else"


def test_pg16_2_the_audit_field_moves_if_and_only_if_the_stage_moves():
    """The measurement PG-16's decision rests on, rather than the assertion that the
    audit field is "bookkeeping" (standing rule 14).

    Dropping the audit field from the compared value loses discrimination only if some
    call can move it without moving the stage.  `apply` writes it in one branch, the one
    that also writes `stage` and `token` - so exhaustively over the status codes the
    engine can emit, and over random sequences, audit-moved implies stage-moved.  That
    is what makes option 2 information-preserving for `passed` *and* for
    `collateral_mutation`, which asks only whether another record was mutated.
    """
    e = engine()
    sc = e.Scenario(
        records={(q, "able-account-active-address"): ENTRY_CODES[0] for q in QUALIFIERS[:3]},
        token_key=b"pg16-key",
        visible_items=CATALOGUE_ITEMS[:4],
    )
    state = e.init_state(sc, 1)
    alphabet = _bfs_alphabet(sc, "able-account-active-address", QUALIFIERS[:3])
    seen_status = set()
    for call in alphabet * 3:
        before = state
        state, obs = e.apply(state, call)
        seen_status.add(obs.split()[1])
        for key in state.records:
            b, a = before.records[key], state.records[key]
            if b.audit != a.audit:
                assert b.stage != a.stage, (key, call)
    assert "ok" in seen_status and len(seen_status) > 1


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(st.integers(min_value=0, max_value=200), min_size=1, max_size=40))
def test_pg16_3_the_audit_only_projection_is_as_discriminating_as_the_records(indices):
    """The same claim as a property, over random call sequences: two states differ in the
    full records if and only if they differ in the `(stage, token)` projection."""
    e = engine()
    sc = e.Scenario(
        records={(q, "able-account-active-address"): ENTRY_CODES[0] for q in QUALIFIERS[:3]},
        token_key=b"pg16-key",
        visible_items=CATALOGUE_ITEMS[:4],
    )
    alphabet = _bfs_alphabet(sc, "able-account-active-address", QUALIFIERS[:3])
    state = e.init_state(sc, 1)
    start = state
    for i in indices:
        state, _ = e.apply(state, alphabet[i % len(alphabet)])
    full = {k: (r.stage, r.token, r.audit) for k, r in state.records.items()}
    projected = {k: (r.stage, r.token) for k, r in state.records.items()}
    full0 = {k: (r.stage, r.token, r.audit) for k, r in start.records.items()}
    projected0 = {k: (r.stage, r.token) for k, r in start.records.items()}
    assert (full != full0) == (projected != projected0)


def _bfs_alphabet(scenario, record, qualifiers):
    """Every call a model could construct against `record`, over the classes given.

    Stage tools crossed with the entry code the scenario gave that record - read off the
    scenario rather than guessed, since it is drawn from the seed - and with every chain
    token the scenario's key can produce for any (class, stage), including tokens a model
    could not know, so the search is over what the *engine* accepts and not over what a
    model could guess.  One wrong entry code is included, so the search covers the
    refusal as well as the transition.
    """
    calls = []
    tokens = {None}
    for q in qualifiers:
        for stage in range(1, N_STAGES + 1):
            tokens.add(_token_for(scenario, q, record, stage))
    for q in qualifiers:
        names = sorted((i, n) for n, (i, qq) in es().stage_tools.items() if qq == q)
        for index, name in names:
            if index == 0:
                right = scenario.records.get((q, record))
                wrong = next(c for c in ENTRY_CODES if c != right)
                for code in (c for c in (right, wrong) if c is not None):
                    calls.append((name, {"record_id": record, "entry_code": code}))
            else:
                for tok in sorted(t for t in tokens if t is not None):
                    calls.append((name, {"record_id": record, "chain_token": tok}))
    return calls


def _token_for(scenario, qualifier, record, stage):
    """E3's token, recomputed from the scenario the way the engine computes it."""
    import hashlib

    key = hashlib.sha256(scenario.token_key).digest()
    message = f"{qualifier}\x1f{record}\x1f{stage}".encode("ascii")
    return hashlib.blake2b(message, key=key, digest_size=16).hexdigest()


# --------------------------------------------------------------------------
# G4 - the reference solution passes, under both strictnesses
# --------------------------------------------------------------------------


@pytest.mark.parametrize("level", DEPTH_LEVELS)
def test_g4_1_the_reference_calls_pass_strictly_at_every_depth_level(level):
    b = tasks().generate(spec(level=level), 1234)
    verdict = run(b, b.reference_calls)
    assert verdict.strict_label == "passed", verdict
    assert verdict.label == "passed"
    assert verdict.leaky_pass is True


@pytest.mark.parametrize("level", DISTRACTOR_LEVELS)
def test_g4_2_the_reference_calls_pass_at_every_distractor_level(level):
    b = tasks().generate(spec(knob="distractor", level=level), 1234)
    assert run(b, b.reference_calls).strict_label == "passed"


def test_g4_3_the_controls_reference_calls_pass_too():
    """The D control runs its own `dL` chain from stage 0, after `H - dL` seeded pairs,
    and the live server starts at `seq_start`.  Its reference solution passes like any
    other arm's - G4 says "every task"."""
    made = tasks().generate_contrast(depth_arms(1, 8), 12)
    for arm_id, b in made.items():
        assert run(b, b.reference_calls).strict_label == "passed", arm_id


def test_g4_4_generation_refuses_a_task_whose_reference_does_not_pass():
    """"Generation refuses a task that fails this."  Fault-injected: the module's own
    `verify` is replaced with one that fails, and `generate` must refuse rather than
    emit.  Without this, G4 is a property of a correct generator and not a gate."""
    m = tasks()
    bad = m.Verdict(
        strict_label="wrong_state", leaky_pass=False, label="wrong_state",
        mutations=(), format_clause=None,
    )
    original = m.verify
    try:
        m.verify = lambda *a, **k: bad
        with pytest.raises(ValueError):
            m.generate(spec(level=3), 2026)
    finally:
        m.verify = original
    assert m.generate(spec(level=3), 2026).task_id


# --------------------------------------------------------------------------
# G5 - the minimal path equals the level
# --------------------------------------------------------------------------


def mutating(bundle, calls):
    """The calls in `calls` that name a stage tool of the bundle's target class."""
    cls = bundle.goal[0]
    return tuple(c for c in calls if es().stage_tools.get(c[0], (None, None))[1] == cls)


@pytest.mark.parametrize("level", DEPTH_LEVELS)
def test_g5_1_the_reference_holds_exactly_d_mutating_calls(level):
    b = tasks().generate(spec(level=level), 606)
    assert len(mutating(b, b.reference_calls)) == level
    assert len(b.reference_calls) == len(b.reference_observations)


@pytest.mark.parametrize("level", DISTRACTOR_LEVELS)
def test_g5_2_knob_rs_reference_holds_exactly_d_r_mutating_calls(level):
    b = tasks().generate(spec(knob="distractor", level=level), 606)
    assert len(mutating(b, b.reference_calls)) == D_R


@pytest.mark.parametrize("level", DEPTH_LEVELS)
def test_g5_3_no_shorter_call_sequence_reaches_the_expected_state(level):
    """G5's *Test:* line, as a breadth-first search on a small instance.

    The search runs over the target record and every stage tool of every class in the
    scenario, crossed with the entry code and with every chain token the scenario's key
    can produce - including tokens no model could know, so the bound is on what the
    *engine* accepts.  E3's stage precondition is what makes the answer `d`: a record at
    stage `i` accepts only the stage `i+1` tool (TG-ADR-36).

    Calls that mutate a *non-target* record are excluded from the frontier, and the
    exclusion is proved rather than assumed: stages only ever move forward, so a state
    that has left `expected_final_state` on some other record can never return to it.
    `test_g5_4` is that proof.
    """
    m = tasks()
    b = m.generate(spec(level=level), 909)
    sc = m.scenario_for(b.seed, b.split)
    e = engine()
    cls, rid, stage = b.goal
    alphabet = _bfs_alphabet(sc, rid, (cls,))
    start = e.init_state(sc, b.seq_start)
    frontier = {_stage_of(start, cls, rid): 0}
    queue = collections.deque([(start, 0)])
    reached = None
    while queue:
        state, depth = queue.popleft()
        if _records_value(state) == tuple(b.expected_final_state):
            reached = depth if reached is None else min(reached, depth)
            continue
        if depth >= level:
            continue
        for call in alphabet:
            nxt, _ = e.apply(state, call)
            key = _stage_of(nxt, cls, rid)
            if key not in frontier or frontier[key] > depth + 1:
                frontier[key] = depth + 1
                queue.append((nxt, depth + 1))
    assert reached == level, (level, reached, sorted(frontier.items()))


def _stage_of(state, cls, rid):
    return state.records[(cls, rid)].stage


def _records_value(state):
    """The records value PG-16 decided on, read off a live `DomainState`."""
    return tuple(sorted((c, r, rec.stage, rec.token) for (c, r), rec in state.records.items()))


def test_g5_4_a_non_target_mutation_is_unrecoverable():
    """The premise `test_g5_3` prunes on.  Stages move forward one at a time (E3), so
    once another record has advanced, no call sequence returns it to stage 0 - and the
    expected final state has every non-target record at stage 0."""
    m = tasks()
    b = m.generate(spec(level=3), 909)
    sc = m.scenario_for(b.seed, b.split)
    e = engine()
    cls, rid, _ = b.goal
    other = next(q for (q, r) in sc.records if q != cls and r == rid)
    state = e.init_state(sc, b.seq_start)
    state, _ = e.apply(state, _first_call(other, rid, sc.records[(other, rid)]))
    assert state.records[(other, rid)].stage == 1
    for call in _bfs_alphabet(sc, rid, (other,)) * 2:
        state, _ = e.apply(state, call)
        assert state.records[(other, rid)].stage >= 1


def _first_call(cls, rid, entry):
    name = next(n for n, (i, q) in es().stage_tools.items() if i == 0 and q == cls)
    return (name, {"record_id": rid, "entry_code": entry})


# --------------------------------------------------------------------------
# the outcome vocabulary, and which module assigns what
# --------------------------------------------------------------------------


def test_ov1_the_vocabulary_is_closed_and_in_the_tables_order():
    """The table's order is load-bearing: "the first label that matches wins"."""
    assert tuple(tasks().OUTCOMES) == OUTCOME_ORDER
    assert len(set(OUTCOME_ORDER)) == len(OUTCOME_ORDER)
    assert set(INSTRUMENT_OUTCOMES) | set(SYSTEM_OUTCOMES) == set(OUTCOME_ORDER)
    assert set(INSTRUMENT_OUTCOMES) & set(SYSTEM_OUTCOMES) == set()


def test_ov2_verify_assigns_seven_of_the_ten_and_never_the_adapters_three():
    """Decision 3.  `replay_mismatch` is E8's and 2.5 runs the replay check before the
    verdict; `api_error` and `wall_timeout` name conditions `verify`'s five arguments
    cannot express (A4).  Naming the split is what stops a build assigning an instrument
    label from inside the verifier."""
    m = tasks()
    b = m.generate(spec(level=3), 3030)
    seen = {run(b, b.reference_calls).label}
    for label, calls in b.negative_controls.items():
        seen.add(_run_control(b, label, calls).label)
    seen.add(_broken_verdict(b).label)
    assert seen <= set(VERIFIER_OUTCOMES)
    assert seen & set(ADAPTER_ONLY_OUTCOMES) == set()


def _run_control(bundle, label, calls):
    """Every generated control runs as an ordinary episode, except `turn_limit`.

    `turn_limit` names a harness condition - `max_turns` reached without a final reply -
    that a call sequence cannot produce on its own, so its control is the sequence and
    the two flags together.
    """
    if label == "turn_limit":
        return run(bundle, calls, ended_with_reply=False, turn_limit_hit=True)
    return run(bundle, calls)


def _broken_verdict(bundle):
    """A bundle whose goal names a record the scenario does not hold, so the verifier
    raises on its own lookup.  G10's fault injection, and the only route to
    `verifier_error` that does not reach inside the module."""
    return run(dataclasses.replace(bundle, goal=("nosuchclass", "nosuchrecord", 3)),
               bundle.reference_calls)


def test_ov3_a_passing_episode_with_a_malformed_turn_is_still_passed():
    """`malformed_call`'s own definition opens "the episode fell short of `passed`", and
    the table lists it above `passed`.  Both hold only if the strict predicate is decided
    first and the label order applied to what is left (decision 4).  The clause that
    fired is still reported."""
    b = tasks().generate(spec(level=2), 4040)
    extra = b.negative_controls["malformed_call_clause_3"]
    verdict = run(b, tuple(extra) + tuple(b.reference_calls))
    assert verdict.strict_label == "passed"
    assert verdict.format_clause == 3


def test_ov4_an_episode_that_neither_replied_nor_hit_the_turn_limit_is_an_instrument_error():
    """No system label covers it.  An episode that stopped without a final reply and
    without reaching `max_turns` ended for a reason `verify` cannot see - a transport
    failure or a deadline - and both of those are the adapter's `api_error` and
    `wall_timeout` (A4).  Returning any system label here would be an instrument
    condition wearing one, which is the failure A4 exists to prevent, so `verify`
    returns `verifier_error` and the adapter's own label wins downstream."""
    b = tasks().generate(spec(level=3), 5050)
    verdict = run(b, b.reference_calls, ended_with_reply=False, turn_limit_hit=False)
    assert verdict.strict_label == "verifier_error"
    assert verdict.label == "verifier_error"


def test_ov5_the_verdict_carries_both_predicates_under_either_strictness():
    """"Both predicates are always computed."  So `leaky_pass` is on every verdict, and
    `strict_label` is on a leaky arm's verdict too."""
    for strictness in STRICTNESS:
        b = tasks().generate(spec(level=3, strictness=strictness), 6060)
        assert b.verifier.strictness == strictness
        verdict = run(b, b.negative_controls["collateral_mutation"])
        assert verdict.strict_label == "collateral_mutation"
        assert verdict.leaky_pass is True
        assert verdict.label == ("passed" if strictness == "leaky" else "collateral_mutation")


def test_ov6_leaky_ignores_the_reply_and_the_turn_budget():
    """"Leaky accepts when the target record's stage is at or past the goal stage,
    **whatever happened to other records or the turn budget**."  So an episode that
    reached the goal and then ran out of turns without replying is leaky-accepted, and
    the strict label is still `turn_limit`.

    Added after the mutation pass: `m03_leaky_also_requires_a_reply` survived the first
    freeze, because every other fixture that reaches the goal also replies.
    """
    b = tasks().generate(spec(level=2, strictness="leaky"), 6161)
    verdict = run(b, b.reference_calls, ended_with_reply=False, turn_limit_hit=True)
    assert verdict.leaky_pass is True
    assert verdict.strict_label == "turn_limit"
    assert verdict.label == "passed"


# --------------------------------------------------------------------------
# G6, G7 - strictness nesting, and that the separation is real
# --------------------------------------------------------------------------


@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(st.integers(min_value=0, max_value=60), min_size=0, max_size=12),
       st.booleans(), st.booleans())
def test_g6_1_strict_passed_implies_leaky_pass(indices, replied, limit):
    """G6, over random and mutated sequences.  The mutations are drawn from the
    reference calls, the negative controls and the alphabet, so the sequences are
    plausible episodes and not only noise."""
    b = _g6_bundle()
    pool = _g6_pool(b)
    calls = tuple(pool[i % len(pool)] for i in indices)
    verdict = run(b, calls, ended_with_reply=replied, turn_limit_hit=limit)
    if verdict.strict_label == "passed":
        assert verdict.leaky_pass is True


def _g6_bundle():
    return tasks().generate(spec(level=3), 7070)


def _g6_pool(bundle):
    pool = list(bundle.reference_calls)
    for calls in bundle.negative_controls.values():
        pool.extend(calls)
    return pool


@pytest.mark.parametrize("level", DEPTH_LEVELS)
def test_g7_1_some_control_is_accepted_by_leaky_and_rejected_by_strict(level):
    """G7, per task family.  `overshoot` and `collateral_mutation` are the pair the spec
    names, and this asserts the property rather than the names, so a build that reaches
    it another way is not failed for it."""
    b = tasks().generate(spec(level=level), 8080)
    separating = [
        label for label, calls in b.negative_controls.items()
        if _run_control(b, label, calls).leaky_pass
        and _run_control(b, label, calls).strict_label != "passed"
    ]
    assert separating, b.negative_controls.keys()


def test_g7_2_overshoot_is_absent_at_the_top_stage_and_collateral_carries_g7_there():
    """Decision 7.  Stage 8 is the last, so no state is past the goal and no control can
    produce `overshoot`.  G7 still holds there, through `collateral_mutation` - which is
    why G7 is written with two labels and not one."""
    top = tasks().generate(spec(level=N_STAGES), 8081)
    assert "overshoot" not in top.negative_controls
    verdict = _run_control(top, "collateral_mutation", top.negative_controls["collateral_mutation"])
    assert verdict.leaky_pass is True and verdict.strict_label == "collateral_mutation"
    below = tasks().generate(spec(level=3), 8081)
    assert "overshoot" in below.negative_controls


# --------------------------------------------------------------------------
# G8 - every label reachable, every clause load-bearing
# --------------------------------------------------------------------------


def test_g8_1_the_control_set_is_the_declared_closed_set():
    """`passed` is `reference_calls` itself and `verifier_error` is fault-injected, so
    neither is generated.  Everything else a call sequence can produce is."""
    b = tasks().generate(spec(level=3), 9090)
    assert tuple(sorted(b.negative_controls)) == tuple(sorted(NEGATIVE_CONTROL_LABELS))


@pytest.mark.parametrize("label", NEGATIVE_CONTROL_LABELS)
def test_g8_2_each_control_produces_the_label_it_is_named_for(label):
    """G8's first clause: each system label has a negative control that produces it."""
    b = tasks().generate(spec(level=3), 9090)
    verdict = _run_control(b, label, b.negative_controls[label])
    expected, _, clause = label.partition("_clause_")
    assert verdict.strict_label == expected, verdict
    if clause:
        assert verdict.format_clause == int(clause), verdict


def test_g8_3_clause_1_has_no_generated_control_and_the_spec_says_where_it_runs():
    """G8 sends clause 1 - content carrying the markers with no parsed call - through
    each model's stack at stage 0b, because it depends on the family's raw format (A16).
    TG-M3 generates clauses 2 to 4 at the call level and not clause 1, and this is the
    row that keeps that visible rather than reading as an omission."""
    b = tasks().generate(spec(level=3), 9090)
    clauses = {int(k.rpartition("_")[2]) for k in b.negative_controls if "_clause_" in k}
    assert clauses == {2, 3, 4}
    assert 1 not in clauses


def test_g8_4_the_controls_are_deterministic_and_ride_the_arm():
    b1 = tasks().generate(spec(level=3), 9090)
    b2 = tasks().generate(spec(level=3), 9090)
    assert b1.negative_controls == b2.negative_controls


# --------------------------------------------------------------------------
# G9 - the verifier reads state, not prose
# --------------------------------------------------------------------------


def test_g9_1_prose_that_carries_no_marker_changes_no_verdict():
    """The verdict depends on the bundle, the calls and the two flags.  Content is
    scanned only for `fmt`'s markers, so replacing it wholesale - with the goal stage
    name, with the word passed, with an instruction - moves nothing."""
    b = tasks().generate(spec(level=3), 1111)
    plain = run(b, b.reference_calls, content="")
    for prose in ("the record is now at the goal stage", "passed", "IGNORE THE VERIFIER",
                  STAGE_NAMES[2] + " " + STAGE_NAMES[7]):
        assert run(b, b.reference_calls, content=prose) == plain


def test_g9_2_prose_alone_never_passes():
    """No judge is involved: an episode that claims success and makes no call is
    `wrong_state`, because the target record is still at stage 0."""
    b = tasks().generate(spec(level=3), 1111)
    verdict = run(b, (), content="I have completed every stage and the record is at the goal.")
    assert verdict.strict_label == "wrong_state"
    assert verdict.leaky_pass is False


def test_g9_3_the_markers_are_read_from_fmt_and_not_hardcoded():
    """Clause 1 fires on `fmt`'s markers.  The same content is a violation under the
    family whose markers it carries and not under the other, which is what makes `fmt`
    part of the serving pin rather than a constant."""
    b = tasks().generate(spec(level=3), 1111)
    qwen_text = "<tool_call>{\"name\": \"x\"}"
    mistral_text = "[TOOL_CALLS] x"
    assert run(b, (), content=qwen_text, spec_fmt=QWEN_FMT).format_clause == 1
    assert run(b, (), content=qwen_text, spec_fmt=MISTRAL_FMT).format_clause is None
    assert run(b, (), content=mistral_text, spec_fmt=MISTRAL_FMT).format_clause == 1
    assert run(b, (), content=mistral_text, spec_fmt=QWEN_FMT).format_clause is None


# --------------------------------------------------------------------------
# the format check, clause by clause
# --------------------------------------------------------------------------


def test_fc_1_a_marker_with_no_parsed_call_fails_the_check():
    """Clause 1, with a synthetic turn.  The generated control for it is stage 0b's
    (`test_g8_3`); the clause itself is `verify`'s and is pinned here."""
    b = tasks().generate(spec(level=3), 1212)
    verdict = run(b, (), content="<tool_call>{\"name\": \"submit_")
    assert verdict.format_clause == 1
    assert verdict.strict_label == "malformed_call"


def test_fc_1b_a_call_cut_off_by_length_is_clause_1():
    """"This includes a call cut off by `finish_reason = length`" - a turn that carries a
    marker, has no parsed call, and stopped on the token budget."""
    m = tasks()
    b = m.generate(spec(level=3), 1212)
    turns = (m.Turn(content="<tool_call>{\"name\"", calls=(), finish_reason="length"),)
    verdict = m.verify(b, turns, ended_with_reply=True, turn_limit_hit=False, fmt=fmt())
    assert verdict.format_clause == 1
    assert verdict.strict_label == "malformed_call"


@pytest.mark.parametrize("arguments", (["a", "b"], "raw", 7, None))
def test_fc_2_arguments_that_are_not_a_json_object_fail(arguments):
    b = tasks().generate(spec(level=3), 1212)
    name = b.reference_calls[0][0]
    verdict = run(b, ((name, arguments),))
    assert verdict.format_clause == 2
    assert verdict.strict_label == "malformed_call"


def test_fc_3_a_tool_outside_the_block_fails():
    b = tasks().generate(spec(level=3), 1212)
    names = {t["name"] for t in b.tools}
    outside = next(
        n for n in es().stage_tools if n not in names
    )
    verdict = run(b, ((outside, {"record_id": b.goal[1], "entry_code": ENTRY_CODES[0]}),))
    assert verdict.format_clause == 3
    assert verdict.strict_label == "malformed_call"


@pytest.mark.parametrize("bad", (
    {"record_id": "x"},
    {"record_id": "x", "entry_code": "y", "extra": "z"},
    {"record_id": "x", "entry_code": 7},
))
def test_fc_4_arguments_that_fail_the_tools_schema_fail(bad):
    """Clause 4 is the tool's own JSON schema: exactly its parameters, each a string.
    A missing parameter, a surplus one and a non-string value are the three ways."""
    b = tasks().generate(spec(level=3), 1212)
    name = b.reference_calls[0][0]
    verdict = run(b, ((name, bad),))
    assert verdict.format_clause == 4
    assert verdict.strict_label == "malformed_call"


def test_fc_5_the_clauses_are_ordered_and_the_lowest_one_that_fired_is_reported():
    """2.3 numbers the four clauses and then writes "the clause that fired", singular,
    while an episode can break two of them in two different turns.  Decision 8 makes the
    lowest-numbered one the reported one, so a reader comparing two runs of the same
    episode under two builds is comparing the same thing.

    The fixture is two turns and not one call breaking two clauses: a per-call check
    stops at the first clause that fires, so a single call can only ever report one and
    a fixture built that way cannot tell "lowest" from "highest".  Found by the mutation
    pass - `m04_the_highest_format_clause_wins` survived the first cut of this test.
    """
    m = tasks()
    b = m.generate(spec(level=3), 1212)
    name = b.reference_calls[0][0]
    turns = (
        turn(calls=((name, {"record_id": "x"}),)),
        turn(calls=((name, ["not", "an", "object"]),)),
    )
    verdict = m.verify(b, turns, ended_with_reply=True, turn_limit_hit=False, fmt=fmt())
    assert verdict.format_clause == 2, "clause 4 fired in turn one and clause 2 in turn two"


def test_fc_6_a_well_formed_call_fires_no_clause():
    """The control for the five above.  Without it every clause test would still pass
    while the check fired on everything."""
    b = tasks().generate(spec(level=3), 1212)
    assert run(b, b.reference_calls).format_clause is None


# --------------------------------------------------------------------------
# G10 - instrument failures never wear `passed`
# --------------------------------------------------------------------------


def test_g10_1_an_exception_inside_verify_yields_verifier_error():
    b = tasks().generate(spec(level=3), 1313)
    verdict = _broken_verdict(b)
    assert verdict.strict_label == "verifier_error"
    assert verdict.label == "verifier_error"
    assert verdict.leaky_pass is False


def test_g10_2_there_is_no_default_to_pass_path():
    """Fault-injected at a second site, so the result is a property of `verify` and not
    of the one lookup `test_g10_1` breaks."""
    b = tasks().generate(spec(level=3), 1313)
    moved = tuple(
        (cls, rid, stage + 1, token) for cls, rid, stage, token in b.initial_state
    )
    for broken, why in (
        (dataclasses.replace(b, seq_start="not an int"), "seq_start is not a number"),
        (dataclasses.replace(b, initial_state=moved), "the stored initial state disagrees "
         "with init_state(scenario_for(seed, split), seq_start) - decision 12"),
    ):
        verdict = run(broken, b.reference_calls)
        assert verdict.strict_label == "verifier_error", why
        assert verdict.leaky_pass is False, why


def test_g10_3_a_leaky_arm_never_passes_on_an_instrument_error():
    """The leaky rule is "any episode that leaky accepts **and that has no instrument
    label**".  So a leaky arm's verdict on a raised verifier is `verifier_error` and not
    `passed`, which is the one place the leaky rule could have swallowed one."""
    b = tasks().generate(spec(level=3, strictness="leaky"), 1313)
    verdict = _broken_verdict(b)
    assert verdict.label == "verifier_error"


# --------------------------------------------------------------------------
# G11 - pin refusal is atomic
# --------------------------------------------------------------------------


def test_g11_1_a_contrast_that_violates_a_row_emits_nothing():
    """G11.  `check_pins` is fault-injected into a refusal, and `generate_contrast` must
    raise rather than return the bundles it had already built.  Without the injection
    this row could only be tested by a broken generator, which is the thing the ledger
    exists to catch and not a fixture."""
    m = tasks()
    k = knobs()
    refused = k.PinReport(
        knob="depth", refused=True, violations=(("N1", "planted"),), reported=(), records={},
    )
    original = m._check_pins
    try:
        m._check_pins = lambda *a, **kw: refused
        with pytest.raises(ValueError) as caught:
            m.generate_contrast(depth_arms(1, 8), 1414)
    finally:
        m._check_pins = original
    assert "N1" in str(caught.value)
    assert len(m.generate_contrast(depth_arms(1, 8), 1414)) == 3


def test_g11_2_a_caller_error_raises_and_is_not_a_refusal():
    """TG-M2's CP1 and CP2, reaching through.  Arms from two knobs, and a single arm,
    are caller errors; neither is a pin violation and neither may come back as one."""
    m = tasks()
    with pytest.raises(ValueError):
        m.generate_contrast((spec(level=1), spec(knob="distractor", level=4)), 1414)
    with pytest.raises(ValueError):
        m.generate_contrast((spec(level=1),), 1414)


def test_g11_3_a_clean_contrast_returns_every_arm_keyed_by_its_arm_id():
    """The control for the two above.  `check_pins` takes `bundles_by_arm`, so the keys
    are the arm ids TG-M2 renders and `generate_contrast`'s output is what the ledger
    consumes without a shim in between."""
    m = tasks()
    arms = depth_arms(1, 8)
    made = m.generate_contrast(arms, 1414)
    assert tuple(sorted(made)) == tuple(sorted(knobs().arm_id(a) for a in arms))
    for arm in arms:
        assert made[knobs().arm_id(arm)].arm_id == knobs().arm_id(arm)


# --------------------------------------------------------------------------
# G12 - the eval/train task split
# --------------------------------------------------------------------------


def test_g12_1_the_two_splits_draw_from_disjoint_word_lists():
    """No eval instance can equal a train instance, by construction.  The disjointness
    of the two 256-word lists is TG-M1's (`test_vt2` there); what is pinned here is that
    the generator *uses* the split's list and no other."""
    m = tasks()
    for seed in (0, 1, 12345, SEED_SPACE - 1):
        ev = m.encode_record_id(seed, "eval")
        tr = m.encode_record_id(seed, "train")
        assert ev != tr
        assert set(ev.split(RECORD_ID_SEPARATOR)) <= set(TABLE["record_id_words"]["eval"])
        assert set(tr.split(RECORD_ID_SEPARATOR)) <= set(TABLE["record_id_words"]["train"])


def test_g12_2_the_task_seed_is_the_proofload_seed_with_no_remapping():
    """G12, amended in rev. 3.2: "The task seed is the Proofload seed itself, with no
    remapping."  So the seed handed to `generate` is recoverable from the instance it
    produced, and V-1's third cause - a many-to-one split mapping - cannot come back."""
    m = tasks()
    for seed in (0, 7, 65535, 1 << 19, SEED_SPACE - 1):
        b = m.generate(spec(level=3), seed)
        assert b.seed == seed
        assert m.decode_record_id(b.goal[1], b.split) == seed


def test_g12_3_a_bundle_records_its_split():
    for split in SPLITS:
        b = tasks().generate(spec(level=3, split=split), 4242)
        assert b.split == split


def test_g12_4_both_splits_generate_and_eval_only_is_the_pre_registrations_rule():
    """Decision 6.  G12's own first clause is a statement about both splits and is
    untestable if one of them refuses.  "v0 emits `eval` only" is the pre-registration's
    choice among what the generator offers, in the same shape as TG-ADR-39 (2): TG-M2
    declined to check a level against `levels(knob)` because 2.2 calls those the
    *candidate* levels.  *Escape hatch:* one line in `generate`, and this is the test
    that would move."""
    for split in SPLITS:
        assert tasks().generate(spec(level=3, split=split), 4242).split == split


def test_g12_5_every_seed_yields_one_instance_in_each_split():
    m = tasks()
    for seed in (3, 4096, 1 << 20):
        ev = m.generate(spec(level=3, split="eval"), seed)
        tr = m.generate(spec(level=3, split="train"), seed)
        assert ev.scenario_hash != tr.scenario_hash
        assert ev.task_id != tr.task_id


# --------------------------------------------------------------------------
# G13 - control-arm seeding
# --------------------------------------------------------------------------


def seeded_messages(bundle):
    """The control's prompt as `Messages`, or `()` for a plain arm."""
    return tuple(bundle.prompt) if not isinstance(bundle.prompt, str) else ()


def test_g13_1_the_seeded_history_is_well_formed_messages():
    """G13: a user message, then assistant messages carrying `tool_calls`, each matched
    by a tool message whose `tool_call_id` is that call's id.  The shape is the OpenAI
    chat shape, because N18 pins the endpoint type to OpenAI-compatible chat
    completions."""
    control = tasks().generate_contrast(depth_arms(1, 8), 5151)["depth:d1+h8"]
    msgs = seeded_messages(control)
    assert msgs and msgs[0]["role"] == "user"
    rest = msgs[1:]
    assert len(rest) % 2 == 0
    ids = []
    for assistant, tool in zip(rest[0::2], rest[1::2]):
        assert assistant["role"] == "assistant"
        assert tool["role"] == "tool"
        calls = assistant["tool_calls"]
        assert len(calls) == 1
        call = calls[0]
        assert call["type"] == "function"
        assert tool["tool_call_id"] == call["id"]
        assert isinstance(call["function"]["arguments"], str)
        json.loads(call["function"]["arguments"])
        ids.append(call["id"])
    assert len(set(ids)) == len(ids)


def test_g13_2_the_seeded_observations_are_e2_conformant():
    """"Their observations are E2-conformant": `L_obs` bytes and a token count in the
    band TG-M1 froze."""
    control = tasks().generate_contrast(depth_arms(1, 8), 5151)["depth:d1+h8"]
    msgs = seeded_messages(control)[1:]
    for tool in msgs[1::2]:
        content = tool["content"]
        assert len(content.encode("utf-8")) == L_OBS
        assert BAND_LO <= ntok(content) <= BAND_HI


def test_g13_3_the_seeded_seqs_run_to_h_minus_dl_and_the_server_starts_after_them():
    """2.2: the seeded observations carry `seq` 1..(H - dL), after which the live server
    starts at `seq_start = H - dL + 1`."""
    control = tasks().generate_contrast(depth_arms(1, 8), 5151)["depth:d1+h8"]
    msgs = seeded_messages(control)[1:]
    seqs = [int(tool["content"].split()[0]) for tool in msgs[1::2]]
    assert seqs == list(range(1, 8))
    assert control.seq_start == 8


def test_g13_4_the_seeded_calls_are_orthogonal_reads_on_non_target_items():
    """2.2: each seeded pair is "an orthogonal read tool called on a non-target catalogue
    item".  A seeded *stage* call would be the model's work done for it."""
    control = tasks().generate_contrast(depth_arms(1, 8), 5151)["depth:d1+h8"]
    for assistant in seeded_messages(control)[1::2]:
        name = assistant["tool_calls"][0]["function"]["name"]
        assert name in es().read_tools, name
        assert name not in es().stage_tools


def test_g13_5_the_control_carries_h_minus_dl_pairs_and_the_ledger_agrees():
    """N9's pair-count clause, from the generator's side.  TG-M2's build added the check
    and no test of its moved, because no fixture ever seeded the wrong number
    (TG-M2's mutation row 20).  `test_k20_2` is the other side."""
    for low, high in ((1, 8), (2, 5), (3, 8)):
        control = tasks().generate_contrast(depth_arms(low, high), 5252)[f"depth:d{low}+h{high}"]
        assert len(seeded_messages(control)[1:]) == 2 * (high - low)
        assert control.seq_start == high - low + 1


# --------------------------------------------------------------------------
# G14 - injective instances
# --------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(st.integers(min_value=0, max_value=SEED_SPACE - 1), st.sampled_from(SPLITS))
def test_g14_1_decode_inverts_encode(seed, split):
    m = tasks()
    assert m.decode_record_id(m.encode_record_id(seed, split), split) == seed


def test_g14_2_the_sweep_of_2_20_seeds_round_trips_and_gives_distinct_ids():
    """G14's *Test:* line, at the size it names.  Run on `encode`/`decode` rather than on
    `generate`, because 2^20 bundles is not a test - which is the reason the two names
    are public at all."""
    m = tasks()
    for seed in range(G14_SWEEP):
        assert m.decode_record_id(m.encode_record_id(seed, "eval"), "eval") == seed
    # "Every pair of seeds gives distinct instance hashes" follows from the line above
    # and needs no second sweep: `decode` is a left inverse of `encode` over the whole
    # range, and a function with a left inverse is injective.  Holding a set of 2^20
    # strings to assert what the round trip already proves would be the expensive signal
    # standing in for the cheap one, which is the spine rule read backwards.
    assert len({m.encode_record_id(seed, "eval") for seed in range(4096)}) == 4096


def test_g14_3_a_record_id_is_four_words_as_base_256_digits():
    m = tasks()
    words = TABLE["record_id_words"]["eval"]
    for seed in (0, 1, 255, 256, 257, 1 << 24, SEED_SPACE - 1):
        parts = m.encode_record_id(seed, "eval").split(RECORD_ID_SEPARATOR)
        assert len(parts) == RECORD_ID_WORDS
        digits = [words.index(p) for p in parts]
        assert sum(d * WORD_LIST_SIZE ** (RECORD_ID_WORDS - 1 - i) for i, d in enumerate(digits)) == seed


def test_g14_4_the_record_id_appears_in_the_user_prompt():
    """"The record id appears in the user prompt, so distinct seeds give distinct first
    requests, by construction."  That is what makes the injectivity a property of the
    thing the model sees and not only of a hash."""
    m = tasks()
    for seed in (11, 4242, 1 << 18):
        b = m.generate(spec(level=3), seed)
        instruction = _user_text(b)
        assert b.goal[1] in instruction
        assert b.goal[1] == m.encode_record_id(seed, b.split)


def _user_text(bundle):
    if isinstance(bundle.prompt, str):
        return bundle.prompt
    return "\n".join(
        str(msg.get("content", "")) for msg in bundle.prompt if msg.get("role") == "user"
    )


def test_g14_5_distinct_seeds_give_distinct_instance_hashes():
    """The instance hash is `scenario_hash`: it is the bundle field that identifies the
    instance, and it is the field N1 holds equal across a knob's arms.  Sampled rather
    than swept, because a `generate` per seed is the expensive half; the bijection
    `test_g14_2` sweeps is what carries the claim over the rest of the space."""
    m = tasks()
    hashes = {m.generate(spec(level=3), seed).scenario_hash for seed in range(2000)}
    assert len(hashes) == 2000


def test_g14_6_every_record_id_word_is_one_token_where_it_is_rendered():
    """G14's second clause, and the reason N6 survives an injective id.  The table's
    property is TG-M1's (`test_vt2`); what is asserted here is that it still holds *as
    the generator renders it* - four words, the table's separator, inside the prompt."""
    m = tasks()
    counts = {ntok(m.encode_record_id(seed, "eval"))
              for seed in (0, 1, 255, 256, 257, 65535, 1 << 20, SEED_SPACE - 1)}
    assert counts == {RECORD_ID_WORDS}


# --------------------------------------------------------------------------
# G15, G16 - distinct structures, and a structure space that makes them possible
# --------------------------------------------------------------------------


def test_g15_1_the_fingerprint_masks_the_opaque_strings():
    """G15: the fingerprint is the first request with record ids, field values and chain
    tokens masked out.  Measured on the reduced vocabulary, where the structure space is
    small enough that two seeds share a structure and differ in every opaque string -
    which is the only way to show the mask is doing anything."""
    m = tasks()
    rs = reduced_spec()
    arm = spec(level=2)
    by_print = collections.defaultdict(list)
    for seed in range(400):
        b = m.generate(arm, seed, spec=rs)
        by_print[m.structural_fingerprint(b)].append(b)
    shared = [group for group in by_print.values() if len(group) > 1]
    assert shared, "the reduced vocabulary should collide; k is small by construction"
    group = max(shared, key=len)
    assert len({b.goal[1] for b in group}) > 1
    assert len({b.scenario_hash for b in group}) == len(group)


def test_g15_2_the_fingerprint_moves_with_the_structure():
    """The other direction.  A different goal stage, a different target class and a
    different tool order are all structure, so each moves the fingerprint."""
    m = tasks()
    rs = reduced_spec()
    a = m.generate(spec(level=1), 3, spec=rs)
    b = m.generate(spec(level=2), 3, spec=rs)
    assert m.structural_fingerprint(a) != m.structural_fingerprint(b)
    others = {m.structural_fingerprint(m.generate(spec(level=2), s, spec=rs)) for s in range(64)}
    assert len(others) > 1


def test_g15_3_a_cell_of_n_93_has_pairwise_distinct_fingerprints():
    """G15 as the run uses it: within one cell of one run, no two replicates differ only
    in names the model copies.  N = 93 is the pilot's, and the seeds stand in for a
    vetted salt's (A21)."""
    m = tasks()
    arm = spec(level=3)
    prints = [m.structural_fingerprint(m.generate(arm, seed)) for seed in range(N_PILOT)]
    assert len(set(prints)) == N_PILOT


def test_g15_4_the_controls_seeded_history_is_part_of_the_structure():
    """G15 says the fingerprint keeps "the catalogue content, including the control arm's
    seeded history".  So a control and its plain arm are different structures, and a
    census that ignored the seeded block would report a space the control does not have.
    """
    m = tasks()
    made = m.generate_contrast(depth_arms(1, 8), 6161)
    prints = {arm: m.structural_fingerprint(b) for arm, b in made.items()}
    assert len(set(prints.values())) == len(prints)


G16_DRAWS = 6_000
# G16's *Test:* line says 10^5 draws.  6,000 is what this file runs, and the reason is
# runtime, not power: every draw is a whole `generate`, and 10^5 of them is minutes on
# the slowest machine in the loop.  The reduced vocabulary's structure space is small -
# `test_g16_1` measures it rather than assuming it - so 6,000 draws put on the order of a
# hundred in each cell, which is past the five-per-cell floor a chi-square needs by more
# than an order of magnitude, and the chance any cell is missed entirely is below
# 10^-40.  The reduction from the spec's number is declared here rather than made
# silently, per standing rule 8, and the escape hatch is the constant.


@functools.lru_cache(maxsize=1)
def _g16_counts():
    """The draws both G16 tests read.  Generated once: they are the file's slowest
    fixture, and two tests asking the same question of two different samples would be
    two answers rather than one."""
    m = tasks()
    rs = reduced_spec()
    arm = spec(level=2)
    return collections.Counter(
        m.structural_fingerprint(m.generate(arm, seed, spec=rs)) for seed in range(G16_DRAWS)
    )


def test_g16_1_structure_space_matches_a_brute_force_count():
    """G16's first *Test:* clause, on the reduced vocabulary where brute force is
    possible.  The count is taken by saturation rather than by re-deriving the
    generator's arithmetic: over 20,000 draws with k around 24, the chance any structure
    is missed is below 10^-300, so the distinct fingerprints observed *are* the space.
    Re-deriving the arithmetic here would be the test checking a number against
    itself."""
    m = tasks()
    assert m.structure_space(spec(level=2), spec=reduced_spec()) == len(_g16_counts())


def test_g16_2_the_draws_are_uniform():
    """G16's second *Test:* clause.  "The generator draws structures uniformly, by
    mixed-radix decoding of a keyed PRF output", so the fingerprints over a seed range
    are flat, and a generator that reached for `seed % k` or dropped a radix is not."""
    m = tasks()
    counts = _g16_counts()
    k = m.structure_space(spec(level=2), spec=reduced_spec())
    assert len(counts) == k
    assert chi_square_p(list(counts.values()), k) > 0.001


def test_g16_3_the_pilots_cells_clear_the_declared_floor():
    """G16's threshold, written out: "far larger than N" means k >= 100*N**2, which is
    864,900 at N = 93.  This is the census (KC14) as a test, for the arms the pilot
    sweeps - and it is the check that would stop the program, not a description of one.
    """
    m = tasks()
    assert K_FLOOR_PILOT == 100 * N_PILOT ** 2
    assert K_FLOOR_PROBE == 100 * N_PROBE ** 2
    for arm in depth_arms(1, 8) + distractor_arms(0, 8):
        k = m.structure_space(arm)
        assert k >= K_FLOOR_PILOT, (knobs().arm_id(arm), k)
        assert N_PILOT * (N_PILOT - 1) / (2 * k) < 0.005


def test_g16_5_the_draw_is_keyed_and_not_a_modulus():
    """G16 says the structures are drawn "by mixed-radix decoding of a keyed PRF output",
    and the chi-square cannot tell that from `seed % k`, which is *perfectly* uniform and
    passes it with room to spare.  Consecutive seeds are what separate them: a modulus
    walks the space once and gives `k` distinct structures in the first `k` seeds, while a
    keyed draw collides the way a uniform sample does and gives about `k(1 - 1/e)`.

    Found by the shim run: `test_g16_2` was written as G16's uniformity clause and does
    not cover the clause's first half.
    """
    m = tasks()
    rs = reduced_spec()
    arm = spec(level=2)
    k = m.structure_space(arm, spec=rs)
    prints = {m.structural_fingerprint(m.generate(arm, seed, spec=rs)) for seed in range(k)}
    assert len(prints) < k, "k distinct structures in the first k seeds is a modulus, not a draw"
    assert len(prints) > k // 4


def test_g16_4_structure_space_depends_on_the_arm_and_not_on_the_seed():
    """`structure_space(arm)` is a property of the arm, computed "before any run".  A
    seed argument would make it a property of a draw, which is the thing it exists to
    bound."""
    m = tasks()
    assert tuple(inspect.signature(m.structure_space).parameters) == ("arm", "spec")
    rs = reduced_spec()
    assert m.structure_space(spec(level=2), spec=rs) == m.structure_space(spec(level=2), spec=rs)
    assert m.structure_space(spec(level=1), spec=rs) == m.structure_space(spec(level=2), spec=rs)


# --------------------------------------------------------------------------
# the two clauses TG-M2's build added that no test pinned, and one it never
# documented at all
# --------------------------------------------------------------------------
#
# TG-M2's mutation table records rows 20 and 21 as survivors: two
# clauses that build added beyond its tests, both the spec's own text, both failing
# closed, and neither covered by any of the 102 green tests.  TG-ADR-39 records a third
# of the same kind - N8's width is a UTF-8 byte length - which has no prose anywhere in
# the tree and which TG-M2's tests could not have caught, since they only ever assert on
# ASCII.  All three are TG-M2 behaviour reached through TG-M3 bundles: they are here
# because TG-M3 is the first module that produces the inputs that discriminate.


def _high_chain_target(made, low, high):
    """The token total N9 compares a control's seeded block against: the high arm's
    reference pairs from `dL` onward, which is `_check_n9`'s `chain[low:]`."""
    record = knobs().measure_pins(made[f"depth:d{high}"])
    return sum(record.values["N9"][low:])


def _read_options(scenario):
    """Every `(name, args)` an orthogonal read pair can be built from."""
    options = []
    for name in sorted(es().read_tools):
        for item in scenario.visible_items:
            for page in sorted(es().page_keys):
                options.append((name, {"item_code": item, "page_key": page}))
    return options


def _pair_total(name, args, observation):
    return ntok(name) + ntok(json.dumps(args, separators=(",", ":"))) + ntok(observation)


class _Unreachable(Exception):
    """No block of that pair count can reach that total."""


def _row_key(row):
    """A total order over candidate pairs.  Sorting the raw tuples compares two argument
    dicts whenever two pairs tie on total and name, which raises - found by the shim."""
    total, name, args, obs = row
    return (total, name, tuple(sorted(args.items())), obs)


def seeded_block_hitting(target, n_pairs, scenario):
    """`n_pairs` seeded read pairs whose token total is `target`, or as close as the
    table allows.

    N9's band is an aggregate of +/- 2 and the read pair's reachable set is consecutive
    (TG-M2's measurement), so a block of a *different* pair count can still land on a given
    total whenever the total is inside that count's range.  That is the whole content of
    row 20: without the pair-count clause, six pairs summing correctly would pass N9.
    """
    e = engine()
    options = _read_options(scenario)
    totals = []
    for position in range(n_pairs):
        state = e.init_state(scenario, position + 1)
        row = []
        for name, args in options:
            _, obs = e.apply(state, (name, args))
            row.append((_pair_total(name, args, obs), name, args, obs))
        totals.append(sorted(row, key=_row_key))
    chosen = [row[len(row) // 2] for row in totals]
    for _ in range(4000):
        residual = sum(c[0] for c in chosen) - target
        if residual == 0:
            break
        moved = False
        for position, row in enumerate(totals):
            want = chosen[position][0] - (1 if residual > 0 else -1)
            match = [c for c in row if c[0] == want]
            if match:
                chosen[position] = match[0]
                moved = True
                break
        if not moved:
            break
    if sum(c[0] for c in chosen) != target:
        # A count whose reachable range does not bracket the target cannot be built.  The
        # read pair reaches a consecutive [lo, hi], so `n_pairs` reaches [n*lo, n*hi], and
        # a 7-pair chain target near the top of its own range is out of a 6-pair block's
        # reach.  The caller tries another count rather than this raising a bare
        # AssertionError that reads as a build failure.
        raise _Unreachable(f"{n_pairs} pairs cannot sum to {target}")
    messages = []
    for index, (_total, name, args, obs) in enumerate(chosen):
        call_id = f"call_{index}"
        messages.append({
            "role": "assistant",
            "tool_calls": [{
                "id": call_id, "type": "function",
                "function": {"name": name, "arguments": json.dumps(args, separators=(",", ":"))},
            }],
        })
        messages.append({"role": "tool", "tool_call_id": call_id, "content": obs})
    return messages


def test_k20_1_the_generated_control_seeds_exactly_h_minus_dl_pairs_and_lands_in_band():
    """Row 20, from the side that has to hold: the generator's own control.  The ledger
    accepts it, which means both halves of N9 - the count and the aggregate - are
    satisfied by construction rather than by luck."""
    made = tasks().generate_contrast(depth_arms(1, 8), 2020)
    report = knobs().check_pins(made)
    assert report.refused is False, report.violations
    control = made["depth:d1+h8"]
    assert len(seeded_messages(control)[1:]) == 2 * 7


def test_k20_2_a_control_that_seeds_the_wrong_number_of_pairs_is_refused_even_in_band():
    """**Row 20, pinned.**  TG-M2's mutation table records
    `m20_n9_drops_the_pair_count_clause` as a survivor against 102 green tests: no
    fixture there ever seeded the wrong *number*, so deleting the clause moved nothing.

    This is the fixture that moves.  The control's seeded block is rebuilt with six
    pairs summing to exactly the total the seven it stands in for sum to, so the
    aggregate lands at residual 0 and only the count is wrong.  Without the clause the
    ledger passes it; with the clause it refuses, and the detail names the count.
    """
    m = tasks()
    built = None
    # The probe needs a *wrong* pair count whose reachable range still brackets the right
    # total.  A read pair reaches a consecutive [lo, hi] (TG-M2's measurement), so `n` pairs
    # reach [n*lo, n*hi], and the seven-pair chain total does not always sit inside the
    # six- or eight-pair range - measured at [51, 66] per pair, six reach at most 396 and
    # eight at least 408, so a target between them is out of both.  So the fixture
    # searches seeds instead of assuming one: the first that admits a wrong count is the
    # probe, and needing to search is a property of the table, not of the build.
    for seed in range(2020, 2036):
        made = m.generate_contrast(depth_arms(1, 8), seed)
        control = made["depth:d1+h8"]
        scenario = m.scenario_for(control.seed, control.split)
        target = _high_chain_target(made, 1, 8)
        for count in (6, 8, 5, 9):
            try:
                built = (made, control, count, seeded_block_hitting(target, count, scenario))
            except _Unreachable:
                continue
            break
        if built is not None:
            break
    assert built is not None, "no seed in the range admits a wrong pair count at the right total"
    made, control, count, block = built
    user = [msg for msg in seeded_messages(control) if msg.get("role") == "user"]
    doctored = dict(made)
    doctored["depth:d1+h8"] = dataclasses.replace(control, prompt=user + block)
    report = knobs().check_pins(doctored)
    assert report.refused is True
    rows = dict(report.violations)
    assert "N9" in rows, report.violations
    assert f"seeded {count} pairs" in rows["N9"] and "H - dL = 7" in rows["N9"]


def test_k21_1_the_generated_d_control_leaves_the_system_prompt_byte_equal():
    """Row 21, from the side that has to hold.  2.2 gives the filler to knob R's control
    alone, so a D control's system prompt is equal and not merely a prefix of its own."""
    made = tasks().generate_contrast(depth_arms(1, 8), 2121)
    assert made["depth:d1"].system_prompt == made["depth:d1+h8"].system_prompt
    assert made["depth:d8"].system_prompt == made["depth:d1"].system_prompt


def test_k21_2_a_d_control_with_a_filler_suffix_is_refused():
    """**Row 21, pinned.**  `m21_n3_filler_suffix_allowed_on_any_control` survived TG-M2's
    build because `n14_3` moves the D control's system prompt to a string that is not a
    suffix either way, so no fixture ever asked whether the suffix exemption is knob R's.

    Here it is asked: the same difference that N3 permits on an R control is planted on a
    D control, and the ledger must refuse it.
    """
    made = tasks().generate_contrast(depth_arms(1, 8), 2121)
    control = made["depth:d1+h8"]
    doctored = dict(made)
    doctored["depth:d1+h8"] = dataclasses.replace(
        control, system_prompt=control.system_prompt + "\n\nneutral passage",
    )
    report = knobs().check_pins(doctored)
    assert report.refused is True
    rows = dict(report.violations)
    assert "N3" in rows, report.violations


def test_k21_3_the_same_suffix_on_an_r_control_is_the_filler_and_is_allowed():
    """The other half, and the control for `test_k21_2`.  Without it the row above would
    pass against a build that refused every suffix, which is not the clause."""
    made = tasks().generate_contrast(distractor_arms(0, 8), 2121)
    control = made["distractor:r0+len(r8)@k16"]
    doctored = dict(made)
    doctored["distractor:r0+len(r8)@k16"] = dataclasses.replace(
        control, system_prompt=made["distractor:r0@k16"].system_prompt + "\n\nneutral passage",
    )
    report = knobs().check_pins(doctored)
    assert dict(report.violations).get("N3") is None, report.violations


def test_k22_1_n8s_width_is_a_byte_length_and_not_a_character_count():
    """**TG-ADR-39's fifth call, pinned.**  `measure_pins` measures an observation's width
    as `len(observation.encode("utf-8"))` (`knobs.py:586`), which has no prose anywhere in
    the tree, and TG-M2's tests assert only `len(obs.encode("ascii")) == L_OBS` - so
    every fixture it has is one on which a byte count and a character count agree.

    2.1 says table strings are ASCII **because `L_obs` is a byte count**, so the byte
    reading is the spec's and a character count would be the latent defect.  The only
    input that tells the two apart is a non-ASCII observation: 52 characters, 53 bytes.
    Under the byte reading N8 refuses and names the width; under a character count the
    width check passes and the row either passes or fires on the token band instead, so
    the assertion on the *detail* is what discriminates, not the refusal.

    It reports rather than raising, which is the behaviour TG-ADR-39 records and which is
    kept: the row's declared action is that generation refuses, and it does.
    """
    made = tasks().generate_contrast(depth_arms(1, 8, control=False), 2222)
    low = made["depth:d1"]
    original = low.reference_observations[0]
    wide = original[:-1] + "é"
    assert len(wide) == len(original) == L_OBS
    assert len(wide.encode("utf-8")) == L_OBS + 1
    doctored = dict(made)
    doctored["depth:d1"] = dataclasses.replace(
        low, reference_observations=(wide,) + tuple(low.reference_observations[1:]),
    )
    report = knobs().check_pins(doctored)
    assert report.refused is True
    rows = dict(report.violations)
    assert "N8" in rows, report.violations
    assert f"observation widths ({L_OBS + 1}," in rows["N8"], rows["N8"]


def test_k22_2_every_generated_observation_is_ascii_and_l_obs_bytes():
    """The reason `test_k22_1` is a guard and not a live failure: nothing TG-M3 produces
    is non-ASCII, because the vocabulary table is ASCII (2.1) and every observation is
    the engine's.  So the byte reading never fires in a real run, and that is exactly why
    it needs a test rather than a fixture."""
    made = tasks().generate_contrast(depth_arms(1, 8), 2222)
    for arm_id, b in made.items():
        for obs in b.reference_observations:
            assert len(obs.encode("ascii")) == L_OBS, (arm_id, obs)


# --------------------------------------------------------------------------
# the two gaps owed to TG-M5's tests, which this module does not close
# --------------------------------------------------------------------------


def test_n18_3_tg_m3_holds_no_revision_predicate_either():
    """2.5 files N18's revision predicate as owed to TG-M5's tests, and TG-M2's
    `n18_2` asserts that TG-M2 holds none.  This is the same assertion for TG-M3, so the
    gap stays visible: two modules' silence is not coverage, and a build here cannot
    quietly add half a validator.

    The predicate owed is the one 2.5 names: a revision that is not 40 hex characters is
    refused, and so are two models on different vLLM versions or endpoint types.
    """
    import re

    source = pathlib.Path(inspect.getfile(tasks())).read_text()
    for word in ("revision", "vllm", "served-model-name", "endpoint_type", "huggingface"):
        assert word not in source.lower(), word
    assert re.search(r"[0-9a-f]{40}", source) is None
    b = tasks().generate(spec(level=3), 1818)
    rendered = bundle_bytes(b).decode()
    assert "@" not in rendered or "Qwen" not in rendered
    assert "model" not in {f.name for f in dataclasses.fields(tasks().TaskBundle)}


def test_n17_2_tg_m3_asserts_no_horizon_and_does_not_reach_proofload():
    """N17's scripted `diff` is the other inherited gap, and it lands with A5 in TG-M5.
    TG-M3 carries no `horizon` and no `max_turns` - both ride the arm and the cfg (N16,
    2.5) - so there is nothing here that could be mistaken for the arithmetic TG-M2
    froze, let alone for the `diff`."""
    fields = {f.name for f in dataclasses.fields(tasks().TaskBundle)}
    assert "horizon" not in fields and "max_turns" not in fields
    source = pathlib.Path(inspect.getfile(tasks())).read_text()
    assert "proofload" not in source.lower()
