"""The tests for tasks.py, task and verifier generation: G1-G16, the outcome
vocabulary, the format check and the two strictnesses.

Where the design could not be used as written, this docstring is authoritative.

The module is `poisson_tasks.tasks`
------------------------------------
The engine is `engine.py` and the knobs are `knobs.py`.  This layer is "Task and verifier
generation" and its type is `TaskBundle`, so the module is `tasks.py` rather than
`generate.py`, which would have read `from poisson_tasks.generate import generate`.

The public surface these tests pin
----------------------------------
`poisson_tasks.tasks.__all__` is exactly, and in this order::

    TaskBundle  VerifierSpec  Verdict  FormatSpec  Turn
    OUTCOMES
    generate  generate_contrast  verify  scenario_for
    structure_space  structural_fingerprint
    encode_record_id  decode_record_id

The design's interface list is `generate`, `verify` and `VerifierSpec.strictness`.  An
extra public symbol is a design violation, so each of the eight beyond that list is named by an
invariant that cannot otherwise be tested, and each is recorded here:

* `TaskBundle`, `Verdict`, `FormatSpec`, `Turn` - the types the two signatures use.
* `OUTCOMES` - the design says the outcome vocabulary "is closed".  Closure is a property of
  the module, and a test cannot assert a closed set the module does not name.
* `generate_contrast` - **G11's home.**  G11 is "a batch that violates any ledger row
  emits nothing", and every ledger row is an equality *across* the arms of one knob
  (the knobs tests' CP2: one arm satisfies all of them vacuously).  `generate(arm, seed)`
  is one arm, so nothing in the interface list can refuse on a ledger row at all.  The
  contrast is the unit the ledger is defined over, so it is the unit generation refuses
  on.
* `scenario_for` - **A8's home.**  The adapter's replay check needs `replay(scenario,
  calls, seq_start)` and the bundle does not carry the scenario.
  The scenario is drawn "from the task seed alone" (the design's definition), so it is a pure
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

Decisions these tests make, where the design leaves the shape open
------------------------------------------------------------------
**1. The verdict compares the records without the audit field.**  The engine left open
whether it should, and this file decides it.  Option 2 of the three - but not for the
reason first given for it.

The deciding argument is **N14**, not "the audit field is bookkeeping".  The engine
makes the audit field the `seq` of the last successful transition and makes
`seq_start` an argument N14 varies by arm, so a completed record's audit field differs
between `depth:d1+h8` and `depth:d1` by exactly `H - dL`.  Option 1 - compute
`expected_final_state` per arm - makes the bundle field differ across the two arms, so
N14's list of fields the D control may change grows from the two the design names to three,
and the field that grows onto it is *the one the verdict compares*.  Option 3 - make
the audit field a call index - changes the engine's audit field, re-opens the engine two modules
back, and is not even reachable: the engine would have to know `seq_start` to subtract
it, and `DomainState` carries `next_seq` and never `seq_start`.  Option 2
is the only one of the three that leaves N14 at the two fields the design names.

**And it is information-preserving, which is the part that had to be measured rather
than asserted**.  `apply` writes the audit field only inside the one
branch that also writes `stage` and `token` (`engine.py`'s `_stage_call`), so a record's
audit field moves if and only if its stage moves.  `test_pg16_2` measures that over the
status codes the engine can emit, rather than reading it off the source - which is the half of the claim a source read
would have got wrong in either direction.  So dropping the audit field from the compared
value loses no discrimination in either place that reads it: `passed` compares the final
records, and `collateral_mutation` asks whether another record was mutated, and a record
cannot have been mutated without its stage moving.

So the shape, and it is a shape and not a comment: **a records value is a sorted tuple
of `(class, record_id, stage, token)` rows.**  There is no audit field in it.
`initial_state` and `expected_final_state` are both that.  `mutations` is the engine's and is
unchanged - it still reports `(class, id, "audit")` triples, and `Verdict.mutations`
still carries them, because that field is diagnostic output and not the predicate.

**2. The scenario is not a bundle field, and it is a pure function of `(seed, split)`.**
The design says a consumer holding only the bundle cannot re-derive the reference observations,
because the bundle does not carry the scenario.  Taken alone that also makes `verify`
impossible - it has to reach the engine to know the final records, and `replay` and
`init_state` both need a scenario - and makes A8's adapter-side replay impossible for
the same reason.  The design's definition resolves it: the scenario is "everything drawn from the
task seed alone", so it is a derivation and not a datum.  `scenario_for(seed, split)`
is that derivation, `verify` calls it with `bundle.seed` and `bundle.split`, and G9 is
untouched - the verdict still depends on nothing outside the bundle and the turns.

This is also what makes N1 hold **by construction**: the arm is not an argument to
`scenario_for`, so no arm transform can move a scenario.  `test_g3_1` pins the signature
for exactly that reason.

**3. `verify` assigns seven of the ten outcomes.  Three are the adapter's.**  The
vocabulary is closed at ten and shared with the Proofload adapter, so `OUTCOMES` carries
all ten in the design's table order.  But `replay_mismatch` is E8's and the adapter
runs the replay check *before* computing the verdict; `api_error` and `wall_timeout`
are A4's fault-injection labels and name conditions - a transport failure, a
wall-clock deadline - that `verify`'s
five arguments cannot express.  So `verify` returns one of `verifier_error`,
`malformed_call`, `turn_limit`, `overshoot`, `wrong_state`, `collateral_mutation`,
`passed`: `test_g8_2` asserts the label of every generated control, `test_g4_1` the
reference solution's and `test_g10_1` a raised verifier's, so none of them can be one of
the other three.  Naming the split
is what stops a later build from quietly assigning an instrument label from inside the
verifier, which A4 exists to prevent.

**4. `malformed_call` is evaluated after pass/fail, not before it.**  The table says the
first matching label wins and lists `malformed_call` above `passed`, and
`malformed_call`'s own definition opens "the episode fell short of `passed`".  Both are
satisfied only if the strict predicate is computed first and the label order is applied
to what is left.  So a turn that fails the format check in an episode that otherwise
passes is `passed`, and `Verdict.format_clause` still names the clause that fired.

**5. The optional `spec` argument.**  G16's *Test:* line runs the census and the
chi-square "on a reduced vocabulary, where brute force is possible".  Nothing in the design
offers a route to one, so `generate`, `generate_contrast`, `scenario_for` and
`structure_space` each take `spec: EngineSpec | None = None`, defaulting to the frozen
table.  `EngineSpec.from_mapping` is the engine's and already builds a spec from any table.

**6. `generate` generates both splits.**  G12 says "v0 emits `eval` only", which is the
pre-registration's choice among what the generator offers, in the same shape as
`knobs.py` declining to check a level against `levels(knob)` because the design calls
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

**8. The lowest-numbered format clause that fired is the one reported.**  The design numbers
the four clauses and then writes "the clause that fired", singular, while one call can
break two at once - a tool outside the block whose arguments are also not an object.
Without a rule the reported clause is whatever the implementation checked first, and two
runs of the same episode under two builds would report different clauses for the same
call.  `test_fc_5` pins it.

**9. The tool block is the target class's stage tools plus the orthogonal reads, and
`K_D = 16` is what that comes to on the frozen table.**  The design writes knob D's block as
"the target class's 8 stage tools" plus "8 orthogonal read tools", `K_D = 16` - three
literals that are all consequences of the frozen table having 8 stages.  Built as a
count, the generator cannot run on the reduced vocabulary decision 5 needs; built as the
rule, `K_D` is `knobs.py`'s literal cited and not re-minted (`test_sf9`), and the reduced
table works by construction.

**10. The scenario carries the target record id in every ledger class, under one entry
code.**  The engine's build left this open in as many words - whether one id may exist
in several classes is a scenario question, for `knobs.py` to answer - and `knobs.py`
draws no scenarios, so it arrives here.  It is forced: a functional distractor is a
required tool's twin in another class (knob R's design), E7 rejects a call against a
record that does not exist rather than redirecting it, and `collateral_mutation` is
how distractor misuse becomes observable.
If the id lived in the target class alone, every distractor call would be `no_such_rec`,
no negative control could produce `collateral_mutation`, and G8 would fail on a label the
whole of knob R rests on.  The shared entry code is the same argument one level down: a
distractor that mirrors the required tool exactly has to be able to *succeed*.

**11. Two named seams, and why this test file names them.**  `generate` calls the
module-global `verify` for G4's gate, and the module-global `_check_pins` - `knobs.py`'s
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

Shapes the design names but does not define
-------------------------------------------
* ``TaskBundle`` is frozen and carries the design's fields in its order, plus nothing:
  ``task_id arm_id seed split scenario_hash system_prompt prompt tools seq_start
  template_id prompt_slots initial_state expected_final_state goal reference_calls
  reference_observations negative_controls verifier pins engine_hash generator_hash``.
  ``pins`` is ``knobs.py``'s ``PinRecord``.
* ``goal`` is ``(ledger class, record id, stage index)``.  The design names the field and never
  its shape, and every label in the table is written against "the target record" and "the
  goal stage", so the verdict needs both and the class is in the key.
* ``Turn(content, calls, finish_reason)``, frozen.  ``calls`` is a tuple of
  ``(name, arguments)`` pairs, the engine's own call shape, with ``arguments`` left as
  parsed so that format-check clause 2 - arguments that are not a JSON object - is
  representable at all.
* ``FormatSpec(name, markers)``, frozen.  ``markers`` is the call markers the pinned
  parser extracts: ``("<tool_call>", "<function=")`` for ``qwen3_coder`` and
  ``("[TOOL_CALLS]",)`` for ``mistral``.
* ``VerifierSpec(strictness)``, frozen, one field.  The design names only ``strictness`` and
  ``knobs.py``'s N11 reads only ``strictness``.  The target and the goal live on the bundle.
* ``Verdict(strict_label, leaky_pass, label, mutations, format_clause)``, frozen.
  ``format_clause`` is the integer clause that fired, or ``None``.
* ``negative_controls`` is a ``dict[str, tuple]`` as the design writes it, keyed by the labels
  above.
* A **records value** is a sorted tuple of ``(class, record_id, stage, token)``.  See
  decision 1.

What is deliberately not tested here
------------------------------------
* **N17's scripted `diff` and N18's revision predicate.**  Both belong to the Proofload
  adapter, and `tests/test_tg_m5_scripted.py` covers them **only with Proofload
  installed**: without it that file is skipped whole, and neither is covered.  This file
  does not cover them either: `tasks.py` imports nothing from Proofload (`test_sf8`) and
  the bundle carries no model field (`test_sf4`), so there is nothing here for either
  check to read.
* **Format-check clause 1's generated control.**  G8 assigns clauses 2-4 to the task layer "at
  the call level" and sends clause 1 - content carrying the markers with no parsed call -
  through each model's own stack, because it depends on the family's raw format
  (A16).  The *clause* is pinned here with a synthetic turn (`test_fc_1`); the
  *generated negative control* for it is not, and `test_g8_1` pins that
  `negative_controls` carries clauses 2, 3 and 4 and not clause 1.
* **Whether a real cell's `k` clears `100*N**2`.**  G16's threshold is pinned as a
  literal and `structure_space` is pinned against a brute-force count on a reduced
  vocabulary.  The census over the pilot's real arms is a run, not a test.
* **G8's "a clause no control catches is a build failure".**  That is a statement about
  deliberately broken builds, not an assertion this file can make about the one build it
  runs against.
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
# the literals these tests pin
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
# same exception the knobs tests' SF2 makes, and for the same reason: it is a compiler directive,
# not a symbol a caller could use.
FUTURE_NAMES = ("annotations",)

# The interface list, and the fields a bundle carries, in the design's order.  The three
# later additions - `template_id`, `prompt_slots`, `reference_observations` - are in the
# design now and are not drafted here.
BUNDLE_FIELDS = (
    "task_id", "arm_id", "seed", "split", "scenario_hash",
    "system_prompt", "prompt", "tools", "seq_start",
    "template_id", "prompt_slots",
    "initial_state", "expected_final_state", "goal",
    "reference_calls", "reference_observations", "negative_controls",
    "verifier", "pins", "engine_hash", "generator_hash",
)

# The outcome vocabulary, closed, in the table's order.  The first label that matches
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

# G8: one generated negative control per system label a call sequence can produce.
# `passed` is `reference_calls` itself and `verifier_error` is fault-injected, so
# neither is generated.  Clause 1 of the format check runs in each model's stack (A16).
NEGATIVE_CONTROL_LABELS = (
    "overshoot",
    "wrong_state",
    "collateral_mutation",
    "turn_limit",
    "malformed_call_clause_2",
    "malformed_call_clause_3",
    "malformed_call_clause_4",
)

# The format check.  Four clauses, numbered as the design numbers them.
FORMAT_CLAUSES = (1, 2, 3, 4)

# The adapter's two pinned parsers and the markers each extracts.
QWEN_FMT = ("qwen3_coder", ("<tool_call>", "<function="))
MISTRAL_FMT = ("mistral", ("[TOOL_CALLS]",))

# Knob D's and knob R's candidate levels, not the pilot defaults.
DEPTH_LEVELS = (1, 2, 3, 5, 8)
DISTRACTOR_LEVELS = (0, 2, 4, 8, 14)
K_D = 16
K_R = 16
D_R = 2
SLACK = 4  # `S = 4`, a settled design value

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
# G14's *Test:* line names a sweep of 2^20 seeds.  2^16 is what this file runs: every word of
# the split's list takes each of the bottom two digit positions inside the first 2^16 seeds,
# so a `decode` that misreads any one word fails the sweep every run, in a sixteenth of the
# time.  The reduction is declared here rather than made silently.
G14_SWEEP = 1 << 16

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
    """The surface is the interface list, the types its signatures use, and the eight the
    module docstring justifies one by one.  An extra public symbol is a design violation.
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
    """The interface list, in the design's order, with the three later additions
    (`template_id`, `prompt_slots`, `reference_observations`) among them.

    The order is asserted because the design writes one and a reader checking a bundle
    against it reads them in that order.  A field beyond the list is a design violation in
    the same way an extra public symbol is - and the two fields named below are the two
    a build would most plausibly add: the scenario, which the design keeps out of the
    bundle, and an audit field, which decision 1 decides against.

    N14's three partitions (below) are checked against the same real field list: every
    field is in exactly one of them, so a field cannot drop out of all three and leave
    every N14 test passing while nothing checks it.
    """
    fields = tuple(f.name for f in dataclasses.fields(tasks().TaskBundle))
    assert fields == BUNDLE_FIELDS
    partitioned = N14_INDEPENDENT + N14_IDENTITY + N14_TRANSFORMED
    assert len(partitioned) == len(set(partitioned))
    assert set(partitioned) == set(fields)
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
    no `proofload`, and nothing that could make generation non-deterministic.

    The walk sees static imports only, so `proofload` is also banned as a word anywhere
    in the source: an `importlib.import_module("proofload")` is a string the walk never
    reads."""
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
    assert "proofload" not in source.lower()
    assert {"poisson_tasks"} & seen or any(
        n.startswith("poisson_tasks") for n in seen
    ), "TG-M3 reaches TG-M1 and TG-M2 by import, and mints neither's literals"


def test_sf9_tg_m1_and_tg_m2_literals_are_cited_and_not_re_minted():
    """`tasks.py` mints no literal another module already froze.

    `L_obs` and the token band are `engine.py`'s; the candidate levels, `K_D`, `K_R`, `d_R`
    and N9's band are `knobs.py`'s.  A second copy here would be a number read back and
    compared with itself, and the two copies would drift silently on
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


# `task_id`'s construction, pinned the way the engine tests pinned `engine_hash`'s: a domain
# separator and a canonical form over every field but the id itself.  The design leaves
# it to tasks.py to state whether the id covers its three newest fields, and the answer is
# yes, by covering all twenty.  It has to be pinned as a construction rather than
# measured as a difference: all three fields are determined by the arm, the scenario and
# the engine, so no pair of bundles differing only in one of them exists to compare.
# The separator keeps the pre-rename spelling on purpose: it is tasks.py's literal,
# and those bytes are hash input rather than a name.
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


def test_g1_4_task_id_is_the_digest_of_every_other_field():
    """The design asks `tasks.py` to state whether `task_id` covers its three newest
    fields.  It covers all twenty, because it is taken over the whole bundle rather than a
    listed subset - so a field added later is covered without anyone remembering to add it.

    Recomputed here independently, the way the engine tests recompute `engine_hash`, so
    the claim is measured rather than read off the source.
    """
    import hashlib

    for arm, seed in ((spec(level=3), 21), (spec(level=1, control=8), 4), (spec(level=8), 99)):
        b = tasks().generate(arm, seed)
        assert b.task_id == hashlib.sha256(task_id_input(b)).hexdigest()


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


# --------------------------------------------------------------------------
# G3 - scenario independence, and N14's field-by-field diff
# --------------------------------------------------------------------------

# N14 as it falls on a real bundle.  The design writes N14 over "the fields its definition
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
# the goal stage is the knob.  What decision 1 decides is the *other* comparison: it does not
# move between `depth:d1` and `depth:d1+h8`, which are at one level and differ only in
# `seq_start`, so N14 stays at the two fields the design names for the D control.  That is
# `test_n14_2`, and it is the assertion option 1 would have had to give up.
N14_INDEPENDENT = (
    "seed", "split", "scenario_hash", "system_prompt", "tools", "template_id",
    "initial_state", "verifier", "engine_hash", "generator_hash",
)
N14_IDENTITY = ("arm_id", "task_id", "pins")
N14_TRANSFORMED = (
    "prompt", "seq_start", "prompt_slots", "goal", "expected_final_state",
    "reference_calls", "reference_observations", "negative_controls",
)


def test_g3_1_the_scenario_is_a_function_of_the_seed_and_the_split_alone():
    """The design's definition: the scenario is "everything drawn from the task seed alone".  So the
    arm is not an argument, and N1 - scenario equality across a knob's arms - holds by
    construction rather than by check.  `test_n14_1`, `test_n14_2` and `test_g3_4` are
    the check anyway, because a generator could still draw *outside* `scenario_for`."""
    m = tasks()
    assert tuple(inspect.signature(m.scenario_for).parameters) == ("seed", "split", "spec")
    assert m.scenario_for(11, "eval") == m.scenario_for(11, "eval")
    assert m.scenario_for(11, "eval") != m.scenario_for(12, "eval")
    assert m.scenario_for(11, "eval") != m.scenario_for(11, "train")


def test_g3_4_a_generated_depth_contrast_satisfies_the_whole_ledger():
    """G3 says N1, N2 and N14 hold for every generated batch, and the ledger is how they
    are measured.  `check_pins` over the generated contrast refuses nothing and reports
    nothing - which is the knobs tests' CP5, run for the first time against real bundles."""
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
    """N14's D-control row, and the reason decision 1 had to be made here.

    The design lets the D control change the prompt `Messages` and `seq_start`, and nothing
    else.  `reference_observations` moves with them, because the control's reference
    episode starts at `seq_start = H - dL + 1` and an observation carries its `seq` -
    which is a field the definition names moving, not a second one appearing.
    `reference_calls` does **not** move: the control runs its own `dL` chain from stage
    0, on the same scenario, so it makes the same calls.

    `expected_final_state` does not move either (decision 1): the verdict's compared
    value carries no audit field, so it does not move with `seq_start`, so N14's list
    for the D control stays at the two fields the design names.  That is the whole of the
    decision, and the records-row width below is the assertion that would move if a later
    build took option 1 instead.
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
    rows = {len(row) for row in plain.expected_final_state}
    assert rows == {4}, "a records row is (class, record_id, stage, token) and nothing else"


def test_pg16_2_the_audit_field_moves_if_and_only_if_the_stage_moves():
    """The measurement PG-16's decision rests on, rather than the assertion that the
    audit field is "bookkeeping".

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
    stage `i` accepts only the stage `i+1` tool.

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
    """The records value decision 1 settles on, read off a live `DomainState`."""
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

    Every other fixture that reaches the goal also replies, so without this one a leaky
    check that also required a reply would pass the file.
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
    """G7, per task family.  `overshoot` and `collateral_mutation` are the pair the design
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
    """G8's first clause: each system label has a negative control that produces it.

    The arm is strict, so the verdict's `label` is its `strict_label` too, and never one
    of the three labels the adapter assigns (decision 3): `replay_mismatch` is E8's and
    the adapter runs the replay check before the verdict; `api_error` and `wall_timeout`
    name conditions `verify`'s five arguments cannot express (A4).  Naming the split is
    what stops a build assigning an instrument label from inside the verifier."""
    b = tasks().generate(spec(level=3), 9090)
    verdict = _run_control(b, label, b.negative_controls[label])
    expected, _, clause = label.partition("_clause_")
    assert verdict.strict_label == expected, verdict
    assert verdict.label == expected, verdict
    if clause:
        assert verdict.format_clause == int(clause), verdict


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
    """Clause 1, with a synthetic turn.  The generated control for it runs in each model's stack
    (`test_g8_1` pins that none is generated here); the clause itself is `verify`'s and is
    pinned here."""
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
    """The design numbers the four clauses and then writes "the clause that fired", singular,
    while an episode can break two of them in two different turns.  Decision 8 makes the
    lowest-numbered one the reported one, so a reader comparing two runs of the same
    episode under two builds is comparing the same thing.

    The fixture is two turns and not one call breaking two clauses: a per-call check
    stops at the first clause that fires, so a single call can only ever report one and
    a fixture built that way cannot tell "lowest" from "highest".
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
    """The knobs tests' CP1 and CP2, reaching through.  Arms from two knobs, and a single arm,
    are caller errors; neither is a pin violation and neither may come back as one."""
    m = tasks()
    with pytest.raises(ValueError):
        m.generate_contrast((spec(level=1), spec(knob="distractor", level=4)), 1414)
    with pytest.raises(ValueError):
        m.generate_contrast((spec(level=1),), 1414)


def test_g11_3_a_clean_contrast_returns_every_arm_keyed_by_its_arm_id():
    """The control for the two above.  `check_pins` takes `bundles_by_arm`, so the keys
    are the arm ids `knobs.py` renders and `generate_contrast`'s output is what the ledger
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
    of the two 256-word lists is the engine's (`test_vt2` there); what is pinned here is that
    the generator *uses* the split's list and no other."""
    m = tasks()
    for seed in (0, 1, 12345, SEED_SPACE - 1):
        ev = m.encode_record_id(seed, "eval")
        tr = m.encode_record_id(seed, "train")
        assert ev != tr
        assert set(ev.split(RECORD_ID_SEPARATOR)) <= set(TABLE["record_id_words"]["eval"])
        assert set(tr.split(RECORD_ID_SEPARATOR)) <= set(TABLE["record_id_words"]["train"])


def test_g12_2_the_task_seed_is_the_proofload_seed_with_no_remapping():
    """G12: "The task seed is the Proofload seed itself, with no
    remapping."  So the seed handed to `generate` is recoverable from the instance it
    produced, and a many-to-one split mapping, one cause of an earlier bug, cannot come back."""
    m = tasks()
    for seed in (0, 7, 65535, 1 << 19, SEED_SPACE - 1):
        b = m.generate(spec(level=3), seed)
        assert b.seed == seed
        assert m.decode_record_id(b.goal[1], b.split) == seed


def test_g12_4_both_splits_generate_and_eval_only_is_the_pre_registrations_rule():
    """Decision 6.  G12's own first clause is a statement about both splits and is
    untestable if one of them refuses.  "v0 emits `eval` only" is the pre-registration's
    choice among what the generator offers, in the same shape as `knobs.py`
    declining to check a level against `levels(knob)` because the design calls those the
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
    band the engine froze."""
    control = tasks().generate_contrast(depth_arms(1, 8), 5151)["depth:d1+h8"]
    msgs = seeded_messages(control)[1:]
    for tool in msgs[1::2]:
        content = tool["content"]
        assert len(content.encode("utf-8")) == L_OBS
        assert BAND_LO <= ntok(content) <= BAND_HI


def test_g13_3_the_seeded_seqs_run_to_h_minus_dl_and_the_server_starts_after_them():
    """Knob D's design: the seeded observations carry `seq` 1..(H - dL), after which the live server
    starts at `seq_start = H - dL + 1`."""
    control = tasks().generate_contrast(depth_arms(1, 8), 5151)["depth:d1+h8"]
    msgs = seeded_messages(control)[1:]
    seqs = [int(tool["content"].split()[0]) for tool in msgs[1::2]]
    assert seqs == list(range(1, 8))
    assert control.seq_start == 8


def test_g13_4_the_seeded_calls_are_orthogonal_reads_on_non_target_items():
    """Knob D's design: each seeded pair is "an orthogonal read tool called on a
    non-target catalogue item".  A seeded *stage* call would be the model's work done for it."""
    control = tasks().generate_contrast(depth_arms(1, 8), 5151)["depth:d1+h8"]
    for assistant in seeded_messages(control)[1::2]:
        name = assistant["tool_calls"][0]["function"]["name"]
        assert name in es().read_tools, name
        assert name not in es().stage_tools


def test_g13_5_the_control_carries_h_minus_dl_pairs_and_the_ledger_agrees():
    """N9's pair-count clause, from the generator's side: every control seeds exactly
    `H - dL` pairs.  `test_k20_2` is the other side: a control seeding the wrong number
    is refused."""
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


def test_g14_2_the_sweep_of_2_16_seeds_round_trips_and_gives_distinct_ids():
    """G14's *Test:* line, over the first 2^16 seeds (`G14_SWEEP` says why not 2^20).
    Run on `encode`/`decode` rather than on `generate`, because a sweep of bundles is not
    a test - which is the reason the two names are public at all.

    Every word reaches the bottom two digit positions here; the top two stay at the
    list's first word throughout.  `test_g14_1` draws seeds from the whole space, and
    `test_g14_3` and `test_g12_2` pin seeds that set the top digits."""
    m = tasks()
    for seed in range(G14_SWEEP):
        assert m.decode_record_id(m.encode_record_id(seed, "eval"), "eval") == seed
    # "Every pair of seeds gives distinct instance hashes" follows from the line above
    # and needs no second sweep: `decode` is a left inverse of `encode` over the swept
    # range, and a function with a left inverse is injective.  Holding a set of 2^16
    # strings to assert what the round trip already proves would be the expensive signal
    # standing in for the cheap one.
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
# 10^-40.  The reduction from G16's number is declared here rather than made
# silently, and the escape hatch is the constant.


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
    generator's arithmetic: over 6,000 draws with k = 48, the chance any structure is
    missed is below 10^-53 (k * (1 - 1/k)^6000), so the distinct fingerprints observed
    *are* the space.
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
    864,900 at N = 93.  This is the census as a test, for the arms the pilot
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

    `test_g16_2` is G16's uniformity clause and does not cover the clause's first half;
    this does.
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
# three knobs.py clauses whose discriminating inputs are generated bundles
# --------------------------------------------------------------------------
#
# N9's pair-count clause and N3's filler exemption are both in the design's own text and
# both fail closed.  N8's width is a UTF-8 byte length, which has no prose anywhere else
# in the tree and which the knobs tests cannot catch, since they only ever assert on
# ASCII.  All three are knobs.py behaviour reached through tasks.py bundles: they are
# here because tasks.py is the first module that produces the inputs that discriminate.


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
    dicts whenever two pairs tie on total and name, which raises."""
    total, name, args, obs = row
    return (total, name, tuple(sorted(args.items())), obs)


def seeded_block_hitting(target, n_pairs, scenario):
    """`n_pairs` seeded read pairs whose token total is `target`, or as close as the
    table allows.

    N9's band is an aggregate of +/- 2 and the read pair's reachable set is consecutive
    (measured when knobs.py was built), so a block of a *different* pair count can still
    land on a given total whenever the total is inside that count's range.  That is the
    whole content of the gap `test_k20_2` pins: without the pair-count clause, six pairs
    summing correctly would pass N9.
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


def test_k20_2_a_control_that_seeds_the_wrong_number_of_pairs_is_refused_even_in_band():
    """**N9's pair-count clause, pinned.**  Only a block of the wrong *number* of pairs
    that still lands on the right token total separates the count clause from the
    aggregate, and this builds one.  The control's seeded block is rebuilt with six
    pairs summing to exactly the total the seven it stands in for sum to, so the
    aggregate lands at residual 0 and only the count is wrong.  Without the clause the
    ledger passes it; with the clause it refuses, and the detail names the count.
    """
    m = tasks()
    built = None
    # The probe needs a *wrong* pair count whose reachable range still brackets the right
    # total.  A read pair reaches a consecutive [lo, hi] (measured for knobs.py), so `n` pairs
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


def test_k21_2_a_d_control_with_a_filler_suffix_is_refused():
    """**N3's filler exemption, pinned.**  The knobs tests' `n14_3` moves the D control's
    system prompt to a string that is not a suffix either way, so it cannot ask whether
    the suffix exemption is knob R's alone.

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


def test_k22_1_n8s_width_is_a_byte_length_and_not_a_character_count():
    """**N8's byte-length width, pinned.**  `measure_pins` measures an observation's width
    as `len(observation.encode("utf-8"))` (`knobs.py:586`), which has no prose anywhere in
    the tree, and the knobs tests assert only `len(obs.encode("ascii")) == L_OBS` - so
    every fixture it has is one on which a byte count and a character count agree.

    The vocabulary table's strings are ASCII **because `L_obs` is a byte count**, so the
    byte reading is intended and a character count would be the latent defect.  The only
    input that tells the two apart is a non-ASCII observation: 52 characters, 53 bytes.
    Under the byte reading N8 refuses and names the width; under a character count the
    width check passes and the row either passes or fires on the token band instead, so
    the assertion on the *detail* is what discriminates, not the refusal.

    It reports rather than raising, which is the behaviour decided for it and which is
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


# --------------------------------------------------------------------------
# the three N7 rules the build added, pinned directly
# --------------------------------------------------------------------------
#
# The build holds N7's overlap set still in three places it has freedom, and says so in
# its module docstring: the reads the instruction touches are replaced last, the
# distractors that add no instruction token the required tools lack are taken first, and
# the template's prose carries no token a read tool's name or a qualifier carries.  A
# build without any one of the rules passes every other test in this file.  Under
# vocabulary v1 the scripted file's `test_ct3[train]` caught all three, through the
# registered arm sets and the six record-id words a tool name carried; vocabulary v2
# removed those words, and that case with them.
#
# **On vocabulary v2 the two designation rules are latent.**  Measured exhaustively, over
# both splits, every qualifier, every drawable entry code and every record-id word in each
# position it can be rendered in: no instruction token is carried by a read tool's name,
# and none makes a distractor loud.  On the frozen table a build without either rule
# generates the same bytes, so no test over the frozen table can tell them apart.  They
# are pinned here on the frozen table with one key changed, `entry_codes` narrowed to one
# code joined from two of the table's own words, which the reference tokenizer splits at
# the join: `regionform` puts `region` in every instruction, and `lookup_region` is a read
# in every knob R block; `discountform` puts `discount` in every instruction, and
# `discount`'s stage tools are distractors for every other class.  Neither whole word is in
# a tool name, so both codes are drawable -- the entry-code filter reads whole words, and
# N7 reads tokens.  Only the entry codes change, because the engine's `apply` resolves
# every call against the frozen table, so a variant cannot rename anything the reference
# chain calls.  The prose is pinned on the frozen table itself, since the template is the
# frozen one.

N7G_SEEDS = tuple(7 + i * (SEED_SPACE // 24) for i in range(24))


def instruction_pieces(text):
    """N7's decomposition of an instruction: the reference tokenizer's tokens as the
    strings they stand for, stripped and lowered, the empty ones dropped."""
    enc = encoding()
    pieces = (enc.decode([token]).strip().lower() for token in enc.encode_ordinary(text))
    return tuple(piece for piece in pieces if piece)


@functools.lru_cache(maxsize=2)
def one_code_spec(code):
    """The frozen table with `entry_codes` narrowed to `code`, so every scenario draws it."""
    t = json.loads(json.dumps(TABLE))
    t["entry_codes"] = [code]
    return engine().EngineSpec.from_mapping(t)


def r_names(level, seed, split, table_spec):
    """A plain knob R arm's tool names, in slot order, and its instruction."""
    b = tasks().generate(spec(knob="distractor", level=level, split=split), seed, table_spec)
    return tuple(tool["name"] for tool in b.tools), b.prompt


def designation(names, pieces, table_spec):
    """The order the build designates the `r0` block's read slots in: the reads no
    instruction token touches first, then the rest, each group in slot order."""
    reads = [slot for slot, name in enumerate(names) if name in table_spec.read_tools]
    return sorted(reads, key=lambda slot: (any(p in names[slot].lower() for p in pieces), slot))


@pytest.mark.parametrize("split", SPLITS)
def test_n7g_1_a_read_the_instruction_touches_is_replaced_last(split):
    """Every level replaces a prefix of one designation, and the designation puts the
    read the instruction touches after every read it does not.  Replacing it earlier would
    take `region` out of N7's overlap set between `r0` and that level."""
    table_spec = one_code_spec("regionform")
    for seed in N7G_SEEDS:
        names, prompt = r_names(0, seed, split, table_spec)
        pieces = instruction_pieces(prompt)
        order = designation(names, pieces, table_spec)
        touched = [names[slot] for slot in order if any(p in names[slot].lower() for p in pieces)]
        assert touched == ["lookup_region"], (seed, touched)
        for level in DISTRACTOR_LEVELS[1:]:
            high, high_prompt = r_names(level, seed, split, table_spec)
            assert high_prompt == prompt
            moved = {slot for slot, name in enumerate(names) if high[slot] != name}
            assert moved == set(order[:level]), (seed, level)


@pytest.mark.parametrize("split", SPLITS)
def test_n7g_2_the_quiet_distractors_are_taken_first(split):
    """`r14` replaces every read, so its block shows the whole drawn distractor order, one
    per designated slot.  In it every quiet distractor comes before every loud one, and
    every lower level takes a prefix of it into a prefix of the designation.  A loud
    distractor taken while a quiet one waits would put `discount` into N7's overlap set."""
    table_spec = one_code_spec("discountform")
    drawn_loud = 0
    for seed in N7G_SEEDS:
        names, prompt = r_names(0, seed, split, table_spec)
        pieces = instruction_pieces(prompt)
        core = [name.lower() for name in names if name in table_spec.stage_tools]
        order = designation(names, pieces, table_spec)
        top, _prompt = r_names(DISTRACTOR_LEVELS[-1], seed, split, table_spec)
        ranked = [top[slot] for slot in order]
        loud = [
            any(p in name.lower() and not any(p in c for c in core) for p in pieces)
            for name in ranked
        ]
        assert loud == sorted(loud), (seed, ranked)
        drawn_loud += any(loud)
        for level in DISTRACTOR_LEVELS[1:-1]:
            high, _prompt = r_names(level, seed, split, table_spec)
            assert [high[slot] for slot in order[:level]] == ranked[:level], (seed, level)
            assert [high[slot] for slot in order[level:]] == [names[s] for s in order[level:]]
    # The rule only orders what it is given: a seed whose draw holds no loud distractor
    # pins nothing, so the sample must hold some.
    assert drawn_loud >= len(N7G_SEEDS) // 2, drawn_loud


@pytest.mark.parametrize("code", ["regionform", "discountform"])
@pytest.mark.parametrize("split", SPLITS)
def test_n7g_3_on_either_table_every_contrast_below_r14_holds_n7(split, code):
    """What the two orderings are for.  `r14` is left out on purpose: its block keeps no
    read and takes every distractor drawn, so there is no order left to choose and the
    rules have no freedom to use."""
    table_spec = one_code_spec(code)
    for seed in N7G_SEEDS:
        for level in DISTRACTOR_LEVELS[1:-1]:
            tasks().generate_contrast(distractor_arms(0, level, split=split), seed, table_spec)


def template_prose(bundle):
    """The instruction with its slot values cut out, in slot order: what the template
    itself says."""
    text, cut, prose = bundle.prompt, 0, []
    for _slot, value in bundle.prompt_slots:
        at = text.index(value, cut)
        prose.append(text[cut:at])
        cut = at + len(value)
    prose.append(text[cut:])
    return "\n".join(prose)


def test_n7g_4_the_templates_prose_carries_no_token_a_read_tool_or_qualifier_carries():
    """The first of the three rules, and the only one the frozen table exercises: knob R's
    block loses reads and gains other classes' stage tools as the level rises, so a prose
    token either carries enters or leaves N7's set with the level.  `in`, `is`, `up` and
    `to`, the four words the template started with, are each carried by some name here,
    which is what shows the check can see what it guards."""
    carriers = tuple(
        f"{verb}_{facet}" for verb, facet in zip(TABLE["read_verbs"], TABLE["facets"])
    ) + QUALIFIERS
    for word in ("in", "is", "up", "to"):
        assert any(word in name for name in carriers), word
    arms = [spec(level=level) for level in DEPTH_LEVELS]
    arms += [spec(knob="distractor", level=level) for level in DISTRACTOR_LEVELS]
    for split in SPLITS:
        for arm in arms:
            arm = dataclasses.replace(arm, split=split)
            for seed in N7G_SEEDS[:6]:
                pieces = instruction_pieces(template_prose(tasks().generate(arm, seed)))
                assert len(pieces) > 20
                carried = {p: [n for n in carriers if p in n] for p in pieces}
                assert not any(carried.values()), (split, arm, seed, carried)
