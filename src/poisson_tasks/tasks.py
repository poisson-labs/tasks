"""Task and verifier generation: `(arm, seed)` to a task bundle, with the verifier, a
reference solution and negative controls generated alongside the task.

The invariants this file is built against are G1-G16, the outcome vocabulary and the
format check, as amended on 2026-09-11, 2026-09-13 and 2026-09-14.
The frozen test file is `tests/test_tg_m3_tasks.py`; where the design's text could not be
used as written, that file's module docstring is authoritative and this file follows it.
`tests/test_k1_verify.py`, `tests/test_k1_surface.py` and `tests/test_k1_hash.py` pin what
the knobs added since need of it: targets read from a task's records, an argument check that
takes optional parameters, names translated through `surface.display_map`, and a generator
hash over the three modules that shape a task.  `tests/test_k2_*.py` pin the similarity knob:
B's block with twelve reads swapped for lookalikes shown under numbered names, the prompt
naming the ledger by number, the masked fingerprint and its census.  `tests/test_k5_*.py`
pin the block-size knob: B's task with its block grown from eight tools to sixty-four, the
right tools and six reads first in an order drawn from a domain of the knob's own, then the
table's other reads, then read copies under names of their own, each answering as the
engine read of its facet.  `tests/test_k6_*.py` pin the argument-difficulty knob: B's task
with each stage tool listing six more parameters, the request stating the level less two
of their values, which both stage calls must carry exactly, and the check that refuses
any other stage call in front of the engine, in `surface.py` so that the verifier, the
tool server and a run's replay apply one check.  `tests/test_k7_*.py` pin the task-shape
knob: four stage calls arranged by the width, one record through four stages, the target
and the decoy two stages each, or the target record one stage in four ledgers; the block
B's with exactly the stage tools the width needs; the request listing one line per goal;
the reference going stage by stage across the records; and the verdict over every target.
`tests/test_k8_*.py` pin the information-spread knob: B's task with the request naming four
reads in place of stating the entry code, the code split across the first P of their answers
and the rest answering `none`, each answer a head, a full stop and keyed hex, answered in front
of the engine by `surface.py` so that the generator, the verifier, the tool server and a run's
replay give one answer; the block, the system prompt and the six calls B's at every level.
`tests/test_f2_*.py` pin the 0.3.0 transport-fault knobs: `timeouts` and `ratelimits` are the
faults design with their own status word and their own sentence, planned, answered and
retried through the same seam, each a knob of its own and not a kind field on the arm;
`landed`, a write that goes through and answers the timeout line, is a knob the generator
refuses on the built-in tasks in one line that says why and names a user's own tools, where
it is built (decided 2026-10-29, Q2 option a of the faults design).

Everything here is a pure function of its arguments and the frozen vocabulary table:
no clock, no RNG, no model, no network (G1, G2).  The engine's and the knobs module's
literals are reached by import and never re-minted, `d_R` included -- it is read back off
the knobs module's own `ArmSpec.reference_turns` rather than copied as a number (SF9).

Shapes the spec names but does not define, decided by this build
---------------------------------------------------------------
That file's docstring settles twelve of them and this file implements those as
written.  Six more were open at the level of the build and are recorded here, each
with its escape hatch.  **Three of the six are one finding**: N7 holds the
prompt-to-tool-name overlap *set* equal across a knob's arms, and knob R's block both
loses read tools and gains other classes' stage tools as `r` rises, so every string the
prompt carries is a chance for a common word to enter or leave that set with the level
and refuse a clean contrast.  The prose, the slot designation and the entry-code draw
are the three places this build has the freedom to hold it still; the record id is the
one place it does not, and that residual is named under `_drawable_entry_codes`.

*Amended 2026-09-21.*  The residual is closed, and not by this module: vocabulary v2
draws both record-id word lists disjoint from every tool name, which is the escape hatch
recorded when the residual was found and the coverage item any future table owed.  The
three rules below still earn their place -- they hold the overlap set still for the
prose, the slots and the entry code, none of which the table's disjointness reaches --
and the sentences above stand as they were written, because the freedom this build had
and did not have is what they describe.  `tests/test_record_id_fix.py` pins the new
property; the six words v1 carried are named there and in `_drawable_entry_codes`.

* **The block's read tools are the table's first `n` reads, in table order, and the
  block is then permuted by the scenario's one slot draw.**  The design says knob D's block
  is "8 orthogonal read tools" and never which eight.  Drawing the subset *and* the
  permutation would parameterise the same arrangement twice, so `structure_space` could
  no longer be the size of the image it claims to count (G16, `test_g16_1` brute-forces
  it).  One draw, one image.  *Escape hatch:* draw the subset instead of the order, and
  `structure_space` changes with it.

* **The slots knob R designates are chosen so that a level change never moves N7's
  overlap set, in both directions.**  The design says "the seed designates the slots"; it
  does not say which.  A read tool whose name carries an instruction token must not drop out
  of the block, and a distractor whose name carries one the required tools do not must
  not drop in -- either moves the overlap set between `r0` and `r8` and refuses the
  contrast.  So the reads the instruction does not touch are replaced first and the
  quiet distractors are taken first, each stable within its group, so both stay a
  function of the one slot draw.  This is the generator satisfying the ledger rather
  than the ledger excusing the generator: the arm transform still only replaces
  designated slots, and re-ranking an ordered selection is a bijection on selections, so
  `structure_space` is untouched.  *Measured*, because the frozen tests catch neither
  half -- it builds a knob R contrast at three seeds, all `r0` against `r8`: over 3,600
  contrasts on the seed ranges whose first record-id word a tool name carries, dropping
  the read half refuses 350 and dropping the distractor half refuses 162, on disjoint
  words (`city`, `grad`, `port` for the reads; `disc` for the distractors), against 0
  with both.  *Escape hatch:* designate in slot order and let N7 refuse those scenarios.
  *(Those four words are vocabulary v1's and are not in v2's lists; the measurement is
  left as it was taken, against the table it was taken on.)*

* **The prompt template's prose carries no token that a read tool's name or a qualifier
  carries**, asserted at import by `_check_template_words`.  The same finding one level
  up: `in`, `is`, `up` and `to` were the four words this template started with, and each
  of them is a substring of some tool name that knob R's level can add or remove.  The
  designation rules are the second line of defence; this is the first, and it is checked
  at import because what it prevents surfaces two modules away as a refused ledger row.
  *Measured*, and it is the largest of the four: restoring one of those words refuses 248
  contrasts of 1,216 against 0, all at `r14`, the one level whose block keeps no read
  tool for the designation rule to work with.
  *Escape hatch:* the check names the word and the tools that carry it.

* **`overshoot` is generated when the block holds a tool that can carry the target past
  the goal, and not otherwise.**  The frozen tests' docstring states the top-stage case;
  the same sentence decides knob R, whose block holds stages 1 and 2 alone, so no call the
  model can make overshoots and no control could produce the label.  G7 is carried by
  `collateral_mutation` there, exactly as at stage 8.  *Escape hatch:* `test_g7_2` is
  written about stage 8 and would not move; a build that gives knob R the whole ladder
  would have to restate knob R's block instead.

* **`structure_space` counts the structures the *arm transform* exposes, which is a
  lower bound for a control arm.**  A D control's seeded block is a derivation of the
  scenario, so two scenarios sharing a class and a slot order can still seed different
  blocks and print different fingerprints.  The count does not claim them.  That is the
  conservative direction for G16's floor -- a smaller `k` overstates the chance of a
  repeat -- and it keeps `structure_space` equal to a brute-force count on the plain
  arms, which is the clause the tests measure.  *Escape hatch:* count the seeded
  block's own reach and report `k` per arm rather than per knob.

* **Opaque slot values are masked by slot name, not by pattern.**  G15's fingerprint
  masks "record ids, field values and chain tokens".  A record id and an entry code are
  ordinary words, so masking them out of a rendered string would need a pattern that
  also matches the prose.  The prompt is rendered from named slots, so the mask is
  applied to the slots the template declares opaque and the rendered string is never
  edited.  *Escape hatch:* the declared set is one constant.

`_check_pins` and the module-global `verify` are the two seams the tests fault-inject
(`test_g11_1`, `test_g4_4`).  Renaming either moves those two tests and nothing else.
"""

from __future__ import annotations

import hashlib as _hashlib
import json as _json
import math as _math
import pathlib as _pathlib
from dataclasses import dataclass as _dataclass
from dataclasses import fields as _dc_fields
from dataclasses import is_dataclass as _is_dataclass
from dataclasses import replace as _replace
from typing import Any as _Any
from typing import cast as _cast

from poisson_tasks import surface as _surface
from poisson_tasks.engine import EngineSpec as _EngineSpec
from poisson_tasks.engine import Scenario as _Scenario
from poisson_tasks.engine import apply as _apply
from poisson_tasks.engine import engine_hash as _engine_hash
from poisson_tasks.engine import init_state as _init_state
from poisson_tasks.engine import mutations as _mutations
from poisson_tasks.engine import replay as _replay
from poisson_tasks.knobs import (
    _ARGUMENT_CODES,
    _BLOCK_HEAD,
    _D_B,
    _ENGINE_ARGUMENTS,
    _LEDGER_NUMBER,
    _LOOKALIKE_LEDGERS,
    _LOOKALIKES,
    _NUMBER_WIDTH,
    _OWN_SLOT,
    _SHAPE_CALLS,
    _SHAPE_WIDTHS,
    _SPREAD_READS,
    _parse_arm_id,
    _split_evenly,
)
from poisson_tasks.knobs import ArmSpec as _ArmSpec
from poisson_tasks.knobs import PinRecord as _PinRecord
from poisson_tasks.knobs import arm_id as _arm_id
from poisson_tasks.knobs import check_pins as _check_pins
from poisson_tasks.knobs import measure_pins as _measure_pins
from poisson_tasks.surface import _prf
from poisson_tasks.tokenizer import count_tokens as _count_tokens
from poisson_tasks.tokenizer import reference_encoding as _reference_encoding

__all__ = [
    "TaskBundle",
    "VerifierSpec",
    "Verdict",
    "FormatSpec",
    "Turn",
    "OUTCOMES",
    "generate",
    "generate_contrast",
    "verify",
    "scenario_for",
    "structure_space",
    "structural_fingerprint",
    "encode_record_id",
    "decode_record_id",
]

# ---------------------------------------------------------------------------
# frozen literals, and the ones cited from the two modules below this one
# ---------------------------------------------------------------------------

_SPEC = _EngineSpec.load()

# The knobs this module generates.  `ArmSpec.__post_init__` in the knobs module is what
# refuses a name that is no knob; these are the same strings its arm ids render, and the
# knobs it names that are not here are refused by `_refuse_a_knob_not_generated`.
_DEPTH = "depth"
_DISTRACTOR = "distractor"
_SIMILARITY = "similarity"
_FAULTS = "faults"
_HISTORY = "history"
_BLOCK = "block"
_ARGUMENTS = "arguments"
_SHAPE = "shape"
_SPREAD = "spread"
_TIMEOUTS = "timeouts"
_RATELIMITS = "ratelimits"
_LANDED = "landed"
_GENERATED_KNOBS = (
    _DEPTH,
    _DISTRACTOR,
    _SIMILARITY,
    _FAULTS,
    _HISTORY,
    _BLOCK,
    _ARGUMENTS,
    _SHAPE,
    _SPREAD,
    _TIMEOUTS,
    _RATELIMITS,
)
# The knobs whose level is a plan of answers in front of the engine: each is the faults knob's
# design with its own status word and its own sentence (`surface.fault_kind`, below).  `landed`
# is a knob and not generated here: on the built-in ledger a repeated stage call is refused
# and moves nothing, so a landed write has no duplicate to catch; it is built on a user's own
# tools, whose store accepts a second write (decided 2026-10-29, the 0.3.0 faults design).
_PLANNED_KNOBS = (_FAULTS, _TIMEOUTS, _RATELIMITS)

# The knobs module's `d_R`, cited and not re-minted: `reference_turns` is `d_R + 1` for
# every R arm (N16), so the number comes back off that module's own constructor.
_D_R = (
    _ArmSpec(
        knob=_DISTRACTOR,
        level=0,
        control=None,
        strictness="strict",
        split="eval",
        generator_version="0",
    ).reference_turns
    - 1
)

# The shape knob's three widths, cited from the knobs module and named for what each
# arranges: one record through four stages, two records (the target and the decoy, in the
# target ledger) two stages each, and the target record one stage in four ledgers.  Four
# stage calls at every width (N33), so a target's goal is the calls shared out over the
# width.
_ONE_CHAIN, _TWO_RECORDS, _FOUR_LEDGERS = _SHAPE_WIDTHS

# Domain separators.  Each changes only if its construction changes, which would be a new
# generator version anyway -- the same shape as the engine's `engine_hash` separator.
# The spelling is deliberately not the package's: these bytes are hash input, so the
# 2026-09-22 rename to `poisson_tasks` left them alone.  Respelling one moves every id
# it keys.
_TASK_ID_DOMAIN = b"task-generator/task_id/1\n"
_SCENARIO_DOMAIN = b"task-generator/scenario_hash/1\n"
_FINGERPRINT_DOMAIN = b"task-generator/structural_fingerprint/1\n"
_GENERATOR_DOMAIN = b"task-generator/generator_hash/2\n"
_TOKEN_KEY_DOMAIN = b"task-generator/token-key/1"
_DECOY_DOMAIN = b"task-generator/decoy-record/1"
_STRUCTURE_DOMAIN = b"task-generator/structure/1"
_ENTRY_DOMAIN = b"task-generator/entry-code/1"
# The block knob's one order: the eight-tool head, the table's other reads, then the read
# copies.  A domain of its own, so no task of another knob moves with it, read as eight
# keyed blocks: a full order of the 240 copies needs about 1,600 bits, and one block is 256.
_BLOCK_DOMAIN = b"task-generator/block-order/1"
_BLOCK_DRAW_BLOCKS = 8
# The arguments knob's one draw: the six words a task's stage calls may have to carry.  A
# domain of its own, so no task of another knob moves with it.
_ARGUMENT_DOMAIN = b"task-generator/argument-values/1"
# The shape knob's one draw: the three other ledgers its widest task advances the target
# record in.  A domain of its own, so no task of another knob moves with it and the
# scenario's draw stays what it was.
_SHAPE_DOMAIN = b"task-generator/shape-ledgers/1"
# The spread knob's one draw: the four reads its request names, each with an item and a page.
# A domain of its own, so no task of another knob moves with it and the scenario's draw stays
# what it was.
_SPREAD_DOMAIN = b"task-generator/spread-reads/1"

# The outcome vocabulary.  Closed, in the table's order: the first label that matches
# wins, so this order is load-bearing and not decoration.
OUTCOMES = (
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

# The three the adapter assigns and this module must never return: `replay_mismatch` is
# E8's and the adapter runs the replay check before the verdict, and `api_error` and
# `wall_timeout` name conditions `verify`'s five arguments cannot express (A4).
_ADAPTER_ONLY = ("replay_mismatch", "api_error", "wall_timeout")

_STRICT = "strict"
_LEAKY = "leaky"
_VERIFIER_ERROR = "verifier_error"
_MALFORMED = "malformed_call"
_TURN_LIMIT = "turn_limit"
_OVERSHOOT = "overshoot"
_WRONG_STATE = "wrong_state"
_COLLATERAL = "collateral_mutation"
_PASSED = "passed"

_OK_STATUS = "ok"
_UNAVAILABLE_STATUS = "unavailable"

# The faults knob's one sentence, added to the system prompt at every faults level, the
# base level included: without it the knob would also test whether a model guesses that an
# `unavailable` answer is transient, a second factor, and the prompt would differ across the
# knob's arms where N3 holds it equal.  The timeouts and ratelimits knobs each add one sentence
# of their own the same way.  The timeouts sentence is deliberately silent on whether a retry
# is safe: that silence is the kind, since an `unavailable` says nothing changed and a timeout
# does not.  The ratelimits sentence says the hint is a wait, and nothing in an episode waits:
# the knob measures whether the model retries after a rate limit as it does after an outage.
_FAULTS_SENTENCE = (
    "A call can come back `unavailable`: nothing changed, and the same call can be made again."
)
_TIMEOUTS_SENTENCE = "A call can come back `timeout`: whether it went through is not known."
_RATELIMITS_SENTENCE = (
    "A call can come back `rate_limited` with a retry-after: nothing changed, and the same "
    "call can be made again after that long."
)
_FAULT_SENTENCES = {
    _FAULTS: _FAULTS_SENTENCE,
    _TIMEOUTS: _TIMEOUTS_SENTENCE,
    _RATELIMITS: _RATELIMITS_SENTENCE,
}

# The prompt templates.  One template for depth and distractor (the design gives knob D
# "one fixed template"), so N6's template-id clause is an equality a contrast can actually
# fail; similarity's names the ledger by number instead of by class, and is otherwise the
# same template sentence for sentence.
_TEMPLATE_ID = "ledger-chain/v1"
_NUMBER_TEMPLATE_ID = "ledger-number/v1"
_GOALS_TEMPLATE_ID = "ledger-goals/v1"
_SPREAD_TEMPLATE_ID = "ledger-spread/v1"

_SLOT_RECORD = "record_id"
_SLOT_ENTRY = "entry_code"
_SLOT_CLASS = "ledger_class"
_SLOT_NUMBER = "ledger_number"
_SLOT_LADDER = "stage_ladder"
_SLOT_GOAL = "goal_stage"
# The arguments knob's own slot, the one N6 leaves out: the values the request states, as
# the request states them.  The knobs module names it, so it is cited and not re-minted.
_SLOT_STATED = _OWN_SLOT[_ARGUMENTS]
# The shape knob's own slot, likewise: the goal lines, one per target.
_SLOT_GOALS = _OWN_SLOT[_SHAPE]
# The spread knob's own slot: the four read lines, one per named read.  Not N6's exception,
# because the lines are the same at every level; the knobs module names no slot for it.
_SLOT_READS = "named_reads"

# The slots G15 masks: an id, an entry code, a ledger number and the stated values are
# opaque strings the model copies, and none is structure.  Masking by slot name is what
# keeps the mask off the prose.  The goal lines are masked whole: the record ids in them
# are opaque, and the ledgers and stages they name are already read off the block, the goal
# and the target list the fingerprint carries for a shape arm.  The named reads are masked
# whole too: their pages are opaque keys, which facet and item each names is a draw of the
# task's and not its structure, and the parts are in answers no first request holds.
_OPAQUE_SLOTS = (
    _SLOT_RECORD,
    _SLOT_ENTRY,
    _SLOT_NUMBER,
    _SLOT_STATED,
    _SLOT_GOALS,
    _SLOT_READS,
)
_MASK = "<opaque>"

_SYSTEM_PROMPT = (
    "You operate a record ledger through the tools you are given.\n"
    "Each tool call returns one fixed-width line: a sequence number, a status word, "
    "and a payload.\n"
    "A ledger record moves one stage at a time, and each stage tool needs what the "
    "stage before it returned.\n"
    "Make one tool call per turn, and reply in plain text once the request is "
    "satisfied."
)

# The prose carries no token that is a substring of a read tool's name or of a qualifier
# other than the target's.  That is N7's real constraint and it is easy to miss: knob R's
# block *loses* read tools and *gains* other classes' stage tools as `r` grows, so a
# common short word -- `in`, `is`, `up`, `to` were the four this template started with --
# enters or leaves the overlap set with the level and refuses the contrast.  The words
# that remain are checked at import by `_check_template_words`.
#
# The record id and the entry code are in double quotes.  Both are ordinary English words
# (four hyphenated ones and one), and bare they read as part of the sentence: model A's
# first card had 72.5% of first replies ask for the values and call no tool.  Quoted, a
# probe got the exact reference call 16 times in 16.  The slots stay the bare values; the
# quotes are the template's.
_USER_TEMPLATE = (
    "Advance record \"{" + _SLOT_RECORD + "}\" of the {" + _SLOT_CLASS + "} ledger.\n"
    "Stage ladder: {" + _SLOT_LADDER + "}.\n"
    "Raise that record through {" + _SLOT_GOAL + "}, and no further.\n"
    "Open with entry code \"{" + _SLOT_ENTRY + "}\"; each later stage needs what the stage "
    "before returned."
)

# Similarity's template: the one above with the ledger named by its number, which is what
# the right tools carry in their names.  Every piece of the number the prompt carries is in
# the right tools' names at every level, so N7's overlap set cannot move with the lookalikes.
_NUMBER_TEMPLATE = _USER_TEMPLATE.replace(
    "of the {" + _SLOT_CLASS + "} ledger", "of ledger {" + _SLOT_NUMBER + "}"
)

# Shape's template: B's stage-ladder line, then one line per goal, then B's entry-code line,
# so the request differs from B's only where the knob needs it.  Each goal line is B's
# "and no further" line with the record and its ledger named, the id in double quotes as B
# quotes it.  A wider task names more ledgers, and those words are in the tool names: that
# is the knob, and why N7 is reported and not refused on a shape contrast.
_B_LINES = _USER_TEMPLATE.split("\n")
_GOAL_LINE = (
    'Raise record "{' + _SLOT_RECORD + '}" of the {' + _SLOT_CLASS + "} ledger through "
    "{" + _SLOT_GOAL + "}, and no further."
)
_GOALS_TEMPLATE = _B_LINES[1] + "\n{" + _SLOT_GOALS + "}\n" + _B_LINES[3]

# Spread's template: B's first three lines, the four named reads on a line each, the spec's
# two sentences, a line on the answers' shape, and B's last line without the entry code, so
# the request differs from B's only where the knob needs it, and states no code (N35).  Each
# read line names the read's facet as the engine's own read describes it, its item and its
# page, the item and the page in double quotes as B quotes the record id.  The prose carries
# `in`, `order`, `listed` and `reads`, pieces of read tools' and ledgers' names, so this
# template stays out of `_check_template_words`: N7 cannot move on a spread contrast, whose
# request and block are the same at every level.
_READ_LINE = '{index}. the {facet} field of catalogue item "{item}" on page "{page}"'
_SPREAD_TEMPLATE = (
    "\n".join(_B_LINES[:3]) + "\nThe four reads:\n{" + _SLOT_READS + "}\n"
    "The entry code is split across the answers of these four reads, in the order listed: join "
    "the parts. An answer that holds no part reads `none`.\n"
    "Each answer's payload is its part, a full stop, then filler.\n"
    "Open with the joined entry code; each later stage needs what the stage before returned."
)

_LADDER_SEPARATOR = " then "

# The R control's filler: a frozen neutral passage appended to the system prompt, whose
# token count equals the tool-block token difference between `rH` and `r0`.  No
# vocabulary-table token, no qualifier, nothing tool-shaped -- asserted at import below.
_FILLER_PREFIX = "\n\n"
_FILLER_WORDS = (
    "quiet",
    "plain",
    "steady",
    "gentle",
    "narrow",
    "hollow",
    "silver",
    "distant",
    "patient",
    "certain",
)

# The N9 search's step budget.  The read pair's reachable totals are consecutive, so a
# one-token walk closes any residual the table can bracket; the budget only bounds a
# scenario whose target lies outside the block's reach, where the ledger refuses anyway.
_SEARCH_STEPS = 4000

_Args = _Any
_Call = tuple[str, _Args]
# A target: a ledger, a record in it and the stage the record is to reach.
_Target = tuple[str, str, int]
_RecordsRow = tuple[str, str, int, "str | None"]
_RecordsValue = tuple[_RecordsRow, ...]
_Option = tuple[int, str, dict[str, str], str]


# ---------------------------------------------------------------------------
# the five types
# ---------------------------------------------------------------------------


@_dataclass(frozen=True)
class Turn:
    """One sampled model turn: its content, its parsed tool calls and its finish reason.

    `calls` is the engine's own call shape, `(name, arguments)`, with `arguments` left as
    parsed -- so format-check clause 2, arguments that are not a JSON object, is
    representable at all.
    """

    content: str
    calls: tuple[_Call, ...]
    finish_reason: str


@_dataclass(frozen=True)
class FormatSpec:
    """The pinned parser's format spec: the call markers that parser extracts.

    Part of the serving pin, which is why clause 1 reads its markers from here rather
    than from a constant of this module.
    """

    name: str
    markers: tuple[str, ...]


@_dataclass(frozen=True)
class VerifierSpec:
    """The verifier spec.  One field: the target and the goal live on the bundle."""

    strictness: str


@_dataclass(frozen=True)
class Verdict:
    """The verdict.  `format_clause` is the clause that fired, or `None`.

    `mutations` is the engine's diff, unchanged and unfiltered: it still reports
    `(class, id, "audit")` triples, because it is diagnostic output and not the predicate.
    """

    strict_label: str
    leaky_pass: bool
    label: str
    mutations: tuple[tuple[str, str, str], ...]
    format_clause: int | None


@_dataclass(frozen=True)
class TaskBundle:
    """The bundle, carrying the design's fields in the design's order and nothing else.

    `initial_state` and `expected_final_state` are **records** values -- a sorted tuple of
    `(class, record_id, stage, token)` rows, with no audit field (PG-16) -- so
    neither moves with the arm's `seq_start` and neither repeats the scenario that
    `scenario_hash` already pins.
    """

    task_id: str
    arm_id: str
    seed: int
    split: str
    scenario_hash: str
    system_prompt: str
    prompt: str | tuple[dict[str, _Any], ...]
    tools: tuple[dict[str, _Any], ...]
    seq_start: int
    template_id: str
    prompt_slots: tuple[tuple[str, str], ...]
    initial_state: _RecordsValue
    expected_final_state: _RecordsValue
    goal: tuple[str, str, int]
    reference_calls: tuple[_Call, ...]
    reference_observations: tuple[str, ...]
    negative_controls: dict[str, tuple[_Call, ...]]
    verifier: VerifierSpec
    pins: _PinRecord
    engine_hash: str
    generator_hash: str


# The gate's format spec.  G4 is a statement about the *state* predicate, and a reference
# solution carries no content, so the gate runs with no markers rather than assuming a
# family's.
_REFERENCE_FORMAT = FormatSpec(name="reference", markers=())


# ---------------------------------------------------------------------------
# the frozen table, read through whichever spec the caller passed
# ---------------------------------------------------------------------------


def _resolve(spec: _EngineSpec | None) -> _EngineSpec:
    return _SPEC if spec is None else spec


def _tool_defs(spec: _EngineSpec) -> dict[str, _Any]:
    return {tool.name: tool for tool in spec.tools}


def _stage_tools_of(spec: _EngineSpec, qualifier: str) -> tuple[str, ...]:
    """The class's stage tools in stage order.  `stage_tools` is insertion-ordered, so
    this is independent of `PYTHONHASHSEED` (G1)."""
    ordered = sorted(
        (index, name) for name, (index, q) in spec.stage_tools.items() if q == qualifier
    )
    return tuple(name for _index, name in ordered)


def _read_names(spec: _EngineSpec) -> tuple[str, ...]:
    """The read tools in table order: `read_tools` is built by zipping the table's verbs
    and facets, so its insertion order is the table's."""
    return tuple(spec.read_tools)


def _block_size(spec: _EngineSpec) -> int:
    """`K_D` and `K_R` as the rule the design states rather than as the literal it happens to
    come to: the target class's stage tools plus an equal number of orthogonal reads.

    Built as a count, the generator could not run on the reduced vocabulary G16's tests
    need; built as the rule, the knobs module's `K_D` is a consequence and not a second
    freeze.
    """
    return len(spec.stage_names) * 2


def _page_keys(spec: _EngineSpec) -> tuple[str, ...]:
    return tuple(sorted(spec.page_keys))


def _catalogue_items(spec: _EngineSpec) -> tuple[str, ...]:
    return tuple(spec.table["catalogue_items"])


def _entry_codes(spec: _EngineSpec) -> tuple[str, ...]:
    return tuple(spec.table["entry_codes"])


def _drawable_entry_codes(spec: _EngineSpec) -> tuple[str, ...]:
    """The entry codes no tool name carries as a substring.

    The third and last of this build's N7 rules, and the same freedom the other two use:
    the design pins the *record id* to the task seed and says nothing about which entry code
    a scenario draws, so the generator draws one that cannot enter N7's overlap set.  It
    costs one code of the table's thirty-two (`look`, which `lookup_region` carries), and
    the code is masked out of G15's fingerprint anyway, so the draw loses nothing
    structural.

    **The record id has no such freedom, and that was the residual**: G14 makes it an
    injective function of the seed, so a seed whose first word a tool name carries -- two
    of 256 in `eval`, four of 256 in `train` -- puts that word into the overlap set, and
    a knob R contrast at `r14`, the one level whose block keeps no read tool at all,
    refuses.  Measured at 9 seeds in 300 before this filter and 0 in 300 after it; over
    the wider sweep, dropping the filter refuses 10 contrasts of 1,216 against 0, all at
    `r14`.  The remainder was reachable only through those six words, and four of them
    did refuse at `r14` -- `city` (`eval`), `grad` and `port` (`train`) at 60 of 60 seeds
    and `disc` (`train`) at 43 of 60, measured, not assumed (the record of it was
    filed with three and `disc` is the one it did not name).

    **Closed 2026-09-21 by the escape hatch, in vocabulary v2**: the record-id word lists
    are now disjoint from every tool name, so the residual has nothing left to reach.  The
    six words v1 carried are gone -- `city` and `face` from `eval`, `disc`, `elect`, `grad`
    and `port` from `train` -- and `circle`, `email`, `disable`, `east`, `gray` and `point`
    stand in their places, each drawn by the rule this function applies to the entry codes:
    take only what no tool name carries.  `tests/test_record_id_fix.py` pins it.  This
    filter stays: it is the entry code's own rule and the table does not cover it, because
    `look` is still one of the thirty-two and `lookup_region` still carries it.
    """
    names = tuple(tool.name for tool in spec.tools)
    drawable = tuple(code for code in _entry_codes(spec) if not any(code in n for n in names))
    return drawable or _entry_codes(spec)


def _param(spec: _EngineSpec, role: str) -> str:
    return str(spec.parameter_names[role])


def _distractor_pool(spec: _EngineSpec, qualifier: str) -> tuple[str, ...]:
    """The functional distractors: the required stage tools of every *other* class.

    Same verb, same parameter names, types and order, a description from the same
    template; only the class qualifier differs.
    """
    pool: list[str] = []
    for other in spec.qualifiers:
        if other == qualifier:
            continue
        pool.extend(_stage_tools_of(spec, other)[:_D_R])
    return tuple(pool)


# ---------------------------------------------------------------------------
# G14 - the record id is a bijection on the 32-bit task seed
# ---------------------------------------------------------------------------


def _record_id_words(split: str) -> tuple[str, ...]:
    lists = _SPEC.table["record_id_words"]
    if split not in lists:
        raise ValueError(f"unknown split {split!r}: the splits are {sorted(lists)}")
    return tuple(lists[split])


def _record_id_shape() -> tuple[int, str]:
    return int(_SPEC.table["record_id_word_count"]), str(_SPEC.table["record_id_separator"])


def encode_record_id(seed: int, split: str) -> str:
    """The split's four words encoding `seed` bijectively, as base-256 digits (G14).

    Every word is one token under the reference tokenizer and the two splits draw from
    disjoint lists, so no eval instance can equal a train instance (G12) and N6 survives
    an injective id.
    """
    words = _record_id_words(split)
    count, separator = _record_id_shape()
    size = len(words)
    space = size**count
    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < space:
        raise ValueError(f"a task seed is an integer in [0, {space}); got {seed!r}")
    digits: list[int] = []
    rest = seed
    for _ in range(count):
        digits.append(rest % size)
        rest //= size
    digits.reverse()
    return separator.join(words[digit] for digit in digits)


def decode_record_id(record_id: str, split: str) -> int:
    """`encode_record_id`'s left inverse, which is what makes the encoding injective."""
    words = _record_id_words(split)
    count, separator = _record_id_shape()
    index = {word: position for position, word in enumerate(words)}
    parts = record_id.split(separator)
    if len(parts) != count:
        raise ValueError(f"{record_id!r} is not {count} words joined by {separator!r}")
    seed = 0
    for part in parts:
        if part not in index:
            raise ValueError(f"{part!r} is not a {split} record-id word")
        seed = seed * len(words) + index[part]
    return seed


# ---------------------------------------------------------------------------
# the keyed draw, and the mixed-radix decoding G16 names
# ---------------------------------------------------------------------------


# The keyed draw itself, `_prf`, lives in `surface.py` and is imported above: what a block
# shows is drawn there from the same seed and split, and that module cannot import this one.


def _mixed_radix(material: bytes, radices: tuple[int, ...]) -> tuple[int, ...]:
    """G16's decoding: the PRF output read as one integer, digit by digit.

    The digest carries far more bits than the radices consume -- the whole product is
    under 2^110 against 256 bits -- so the modulo bias is below 2^-140 and the draw is
    uniform to well past anything a chi-square over 6,000 samples could see.
    """
    value = int.from_bytes(material, "big")
    digits: list[int] = []
    for radix in radices:
        digits.append(value % radix)
        value //= radix
    return tuple(digits)


def _permutation(digits: tuple[int, ...], size: int) -> tuple[int, ...]:
    """A permutation of `size` slots from `size - 1` factorial-base digits."""
    remaining = list(range(size))
    out: list[int] = []
    for digit in digits:
        out.append(remaining.pop(digit))
    out.extend(remaining)
    return tuple(out)


def _selection(digits: tuple[int, ...], size: int) -> tuple[int, ...]:
    """An ordered selection of `len(digits)` items from `size`, by the same decoding."""
    remaining = list(range(size))
    out: list[int] = []
    for digit in digits:
        out.append(remaining.pop(digit))
    return tuple(out)


def _slot_radices(spec: _EngineSpec) -> tuple[int, ...]:
    block = _block_size(spec)
    return tuple(range(block, 1, -1))


def _pool_radices(spec: _EngineSpec) -> tuple[int, ...]:
    """The radices of the distractor ordering: an ordered selection of the most
    distractors any R level can ask for, out of the pool."""
    pool = len(_distractor_pool(spec, spec.qualifiers[0]))
    wanted = _block_size(spec) - _D_R
    if pool <= 0 or wanted <= 0:
        return ()
    wanted = min(wanted, pool)
    return tuple(range(pool, pool - wanted, -1))


def _scenario_radices(spec: _EngineSpec) -> tuple[int, ...]:
    """The one draw a scenario makes, in one radix list: the target class, the slot
    permutation, and the distractor ordering the knob may designate."""
    return (len(spec.qualifiers),) + _slot_radices(spec) + _pool_radices(spec)


def _draw(seed: int, split: str, spec: _EngineSpec) -> tuple[int, ...]:
    return _mixed_radix(_prf(_STRUCTURE_DOMAIN, seed, split), _scenario_radices(spec))


def _drawn_parts(
    seed: int, split: str, spec: _EngineSpec
) -> tuple[str, tuple[int, ...], tuple[int, ...]]:
    """The class, the slot permutation and the distractor ordering, from one draw."""
    digits = _draw(seed, split, spec)
    slots = _slot_radices(spec)
    pool = _pool_radices(spec)
    qualifier = spec.qualifiers[digits[0]]
    slot_digits = digits[1 : 1 + len(slots)]
    pool_digits = digits[1 + len(slots) : 1 + len(slots) + len(pool)]
    return (
        qualifier,
        _permutation(slot_digits, _block_size(spec)),
        _selection(pool_digits, len(_distractor_pool(spec, qualifier))),
    )


# ---------------------------------------------------------------------------
# G3 - the scenario, a derivation of the seed and the split alone
# ---------------------------------------------------------------------------


def _decoy_seed(seed: int, split: str) -> int:
    words = _record_id_words(split)
    count, _separator = _record_id_shape()
    space = int(len(words) ** count)
    value = int.from_bytes(_prf(_DECOY_DOMAIN, seed, split), "big") % space
    if value == seed:
        value = (value + 1) % space
    return value


def _absent_record_id(scenario: _Scenario, split: str) -> str:
    """A well-formed id the scenario does not hold.  Used by the clause-3 control on a
    table too small to leave a read tool outside the block, so the control still names a
    real tool and still mutates nothing."""
    words = _record_id_words(split)
    count, separator = _record_id_shape()
    held = {record for _cls, record in scenario.records}
    tail = next(iter(sorted(held))).split(separator)[1:]
    for word in words:
        candidate = separator.join([word] + tail)
        if candidate not in held:
            return candidate
    raise ValueError("every record id the table can render is already in the scenario")


def scenario_for(seed: int, split: str, spec: _EngineSpec | None = None) -> _Scenario:
    """Everything drawn from the task seed alone, and nothing from the arm.

    The scenario is a derivation and not a bundle field: `verify`
    re-derives it from `bundle.seed` and `bundle.split`, and so does A8's replay check.
    Because the arm is not an argument, N1 -- scenario equality across a knob's arms --
    holds by construction rather than by check.

    Every ledger class carries the same two record ids, the target and one decoy, under
    one entry code.  Both halves are forced: a functional distractor is a required tool's
    twin in another class and E7 rejects rather than redirects, so an id in the target
    class alone would make every distractor call `no_such_rec`; and knob D's block holds
    no other class's tools at all, so with one id per class no call inside that block
    could mutate another record and `collateral_mutation` would be unreachable.
    """
    engine_spec = _resolve(spec)
    target = encode_record_id(seed, split)
    decoy = encode_record_id(_decoy_seed(seed, split), split)
    codes = _drawable_entry_codes(engine_spec)
    code = codes[int.from_bytes(_prf(_ENTRY_DOMAIN, seed, split), "big") % len(codes)]
    records: dict[tuple[str, str], str] = {}
    for qualifier in engine_spec.qualifiers:
        for record in (target, decoy):
            records[(qualifier, record)] = code
    return _Scenario(
        records=records,
        token_key=_hashlib.blake2b(
            _TOKEN_KEY_DOMAIN + f"\x1f{seed}\x1f{split}".encode("ascii"), digest_size=32
        ).digest(),
        visible_items=_catalogue_items(engine_spec),
    )


def _scenario_hash(scenario: _Scenario) -> str:
    body = {
        "records": [
            [cls, record, scenario.records[(cls, record)]]
            for cls, record in sorted(scenario.records)
        ],
        "token_key": scenario.token_key.hex(),
        "visible_items": list(scenario.visible_items),
    }
    return _hashlib.sha256(_SCENARIO_DOMAIN + _canonical_bytes(body)).hexdigest()


# ---------------------------------------------------------------------------
# canonical forms - the one rendering every hash in this module is taken over
# ---------------------------------------------------------------------------


def _canon(value: _Any) -> _Any:
    """Every field as JSON-able data, deterministically and independently of
    `PYTHONHASHSEED`: dataclasses by field, mappings by sorted key, sequences in order."""
    if _is_dataclass(value) and not isinstance(value, type):
        return {field.name: _canon(getattr(value, field.name)) for field in _dc_fields(value)}
    if isinstance(value, dict):
        return {str(k): _canon(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_canon(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _canonical_bytes(value: _Any) -> bytes:
    return _json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _task_id(bundle: TaskBundle) -> str:
    """A content hash over a domain separator and every field but the id itself.

    It covers all twenty, rather than a listed subset, so a field added later is covered
    without anyone remembering to add it.  The same construction the engine pinned for
    `engine_hash`.
    """
    body = {name: value for name, value in _canon(bundle).items() if name != "task_id"}
    return _hashlib.sha256(_TASK_ID_DOMAIN + _canonical_bytes(body)).hexdigest()


# The modules whose bytes shape a task, in the order the generator hash reads them: this one,
# what a block shows and what answers in front of the engine, and the knobs' levels and
# literals.
_GENERATOR_MODULES = ("tasks.py", "surface.py", "knobs.py")


def _generator_hash(generator_version: str) -> str:
    """N12's generator hash: the arm's generator version beside the source of every module
    that shapes a task, so it moves when any of them does and for nothing else -- not the
    folder the package sits in, the process or the hash seed."""
    package = _pathlib.Path(__file__).resolve().parent
    parts = [generator_version.encode("utf-8")]
    parts += [(package / name).read_bytes() for name in _GENERATOR_MODULES]
    return _hashlib.sha256(_GENERATOR_DOMAIN + b"\x1f".join(parts)).hexdigest()


# ---------------------------------------------------------------------------
# records values - the shape PG-16 decided
# ---------------------------------------------------------------------------


def _records_value(state: _Any) -> _RecordsValue:
    """A sorted tuple of `(class, record_id, stage, token)` rows, and no audit field."""
    return tuple(
        sorted(
            (cls, record, entry.stage, entry.token)
            for (cls, record), entry in state.records.items()
        )
    )


def _row(value: _RecordsValue, cls: str, record: str) -> tuple[int, str | None]:
    for row_cls, row_record, stage, token in value:
        if (row_cls, row_record) == (cls, record):
            return (stage, token)
    raise KeyError(f"({cls!r}, {record!r}) is not in the records value")


# ---------------------------------------------------------------------------
# the tool block
# ---------------------------------------------------------------------------


def _render_tool(
    tool: _Any,
    name: str | None = None,
    description: str | None = None,
    extra: tuple[str, ...] = (),
) -> dict[str, _Any]:
    """One tool's schema, as the block carries it: under the name and the description the
    block shows it with, which are the engine's own unless given, and with `extra`
    parameters listed beside the tool's own, each a string and none required (an arguments
    arm's six more on each stage tool; the engine's own stay the required ones, N30).

    Keys are written in one order and every hash over the block is taken with
    `sort_keys`, so neither the rendering nor its digest moves with insertion order.
    """
    names = sorted(tool.parameters)
    return {
        "name": tool.name if name is None else name,
        "description": tool.description if description is None else description,
        "parameters": {
            "type": "object",
            "properties": {
                name: {"type": tool.parameters.get(name, "string")}
                for name in sorted((*names, *extra))
            },
            "required": names,
            "additionalProperties": False,
        },
    }


def _render_block(
    spec: _EngineSpec,
    seed: int,
    split: str,
    rendered_arm: str,
    goal: tuple[str, str, int],
    block: tuple[str, ...],
) -> tuple[dict[str, _Any], ...]:
    """The block's schemas in slot order, each as `surface.display_map` shows it: the shown
    name, the engine tool it stands for, and the description the block gives it.  `block` is
    the names the block shows (`surface.shown_names`), the engine's own for every knob but
    similarity, and on a block arm the read copies' as well, which the generator builds the
    block in.  On an arguments arm each stage tool lists the six argument parameters beside
    its own, at every level and on the control alike, so the block is one block across the
    knob's arms (N4, N30)."""
    defs = _tool_defs(spec)
    shown = _surface.display_map(seed, split, rendered_arm, goal, block)
    wide = _parse_arm_id(rendered_arm).knob == _ARGUMENTS
    return tuple(
        _render_tool(
            defs[entry.engine],
            name,
            entry.description,
            _ARGUMENT_CODES if wide and entry.engine in spec.stage_tools else (),
        )
        for name, entry in shown.items()
    )


def _instruction_pieces(text: str) -> tuple[str, ...]:
    """The instruction's reference-tokenizer tokens, as the strings they stand for.

    The same decomposition the ledger's N7 measures; this module reads it to designate the
    distractor slots, so the generator and the ledger agree on what "lexical overlap"
    means without either re-implementing the other.
    """
    encoding = _reference_encoding()
    pieces: list[str] = []
    for token in encoding.encode_ordinary(text):
        piece = encoding.decode([token]).strip().lower()
        if piece:
            pieces.append(piece)
    return tuple(pieces)


def _touched_by(name: str, pieces: tuple[str, ...]) -> bool:
    lowered = name.lower()
    return any(piece in lowered for piece in pieces)


def _block_names(
    spec: _EngineSpec,
    arm: _ArmSpec,
    qualifier: str,
    permutation: tuple[int, ...],
    pool_order: tuple[int, ...],
    instruction: str,
) -> tuple[str, ...]:
    """The arm's tool block, in slot order.

    Knob D: the target class's stage tools plus an equal number of orthogonal reads,
    identical at every level (N4).  Knob R: the `d_R` required tools, `r` functional
    distractors and the rest reads, with the required tools' slots untouched (N2).  Faults,
    timeouts and ratelimits: knob R's base block at every level (N4), because each level is
    a plan over the calls and not a change to the block.  History: the same base block at
    every level (N4), because its level is earlier tool work before the first move and not a
    change to the block.
    Arguments: the same base block too (N4), its level being how many values the stage calls
    carry, which widens the stage tools' schemas and designates no slot.  Spread: the same
    base block too (N4), its level being how many of the four named reads answer with a
    part, which changes the answers and designates no slot.
    """
    size = _block_size(spec)
    stage_tools = _stage_tools_of(spec, qualifier)
    reads = _read_names(spec)
    if arm.knob == _DEPTH:
        base = list(stage_tools) + list(reads[: size - len(stage_tools)])
    else:
        base = list(stage_tools[:_D_R]) + list(reads[: size - _D_R])
    if len(base) != size:
        raise ValueError(
            f"the vocabulary table cannot fill a {size}-slot block for {arm.knob}: "
            f"{len(base)} tools available"
        )
    names = [base[index] for index in permutation]
    if arm.knob in (_DEPTH, *_PLANNED_KNOBS, _HISTORY, _ARGUMENTS, _SPREAD) or arm.level == 0:
        return tuple(names)

    pool = _distractor_pool(spec, qualifier)
    if arm.level > len(pool) or arm.level > size - _D_R:
        raise ValueError(
            f"level r{arm.level} needs {arm.level} functional distractors; this table "
            f"offers {min(len(pool), size - _D_R)}"
        )
    pieces = _instruction_pieces(instruction)
    core = _stage_tools_of(spec, qualifier)[:_D_R]
    # The designation, both halves, and both for N7.  A level change may neither drop a
    # name the instruction touches nor add one it touches, or the overlap set moves and
    # generation refuses its own contrast.  So the reads the instruction does not touch
    # are replaced first, and the distractors that introduce nothing the required tools
    # already carry are taken first.  Each is stable within its group, so both stay a
    # function of the one slot draw -- and re-ranking an ordered selection is a bijection
    # on selections, so `structure_space` is untouched.
    read_slots = [slot for slot, name in enumerate(names) if name in spec.read_tools]
    designated = sorted(read_slots, key=lambda slot: (_touched_by(names[slot], pieces), slot))
    ranked = sorted(
        enumerate(pool_order),
        key=lambda pair: (not _quiet_against(pool[pair[1]], core, pieces), pair[0]),
    )
    for position in range(arm.level):
        names[designated[position]] = pool[ranked[position][1]]
    return tuple(names)


def _similarity_block(
    spec: _EngineSpec, seed: int, split: str, qualifier: str, permutation: tuple[int, ...]
) -> tuple[str, ...]:
    """B's block with twelve of its reads swapped for lookalikes, in engine names.

    B is `distractor:r0@k16`'s block, as `_block_names` builds it: the right tools and
    fourteen reads in the scenario's slot order.  The right tools keep their slots; the reads
    in B's first two read slots stay; every later read slot takes the next lookalike, each
    lookalike ledger's first stage then its second, the ledgers in their drawn order.  No draw
    of its own: which reads stay follows B's slot order, and the census counts what the masked
    block can still tell apart (`structure_space`).
    """
    size = _block_size(spec)
    base = list(_stage_tools_of(spec, qualifier)[:_D_R]) + list(_read_names(spec)[: size - _D_R])
    names = [base[index] for index in permutation]
    lookalikes = [
        tool
        for other in _surface.lookalike_ledgers(seed, split, qualifier)
        for tool in _stage_tools_of(spec, other)[:_D_B]
    ]
    read_slots = [slot for slot, name in enumerate(names) if name in spec.read_tools]
    if len(lookalikes) > len(read_slots):
        raise ValueError(
            f"the block holds {len(read_slots)} reads and {len(lookalikes)} lookalikes would "
            "replace them"
        )
    kept = len(read_slots) - len(lookalikes)
    for slot, tool in zip(read_slots[kept:], lookalikes, strict=True):
        names[slot] = tool
    return tuple(names)


def _aliased_reads(spec: _EngineSpec) -> tuple[str, ...]:
    """The read copies: every `{verb}_{facet}` of the table's read verbs and facets that
    the engine does not read under, in table order.  Each is shown by `surface.display_map`
    as the engine read of its facet, under words of its own."""
    verbs = spec.table["read_verbs"]
    facets = spec.table["facets"]
    return tuple(
        f"{verb}_{facet}"
        for verb in verbs
        for facet in facets
        if f"{verb}_{facet}" not in spec.read_tools
    )


def _sized_block(
    spec: _EngineSpec, seed: int, split: str, qualifier: str, level: int
) -> tuple[str, ...]:
    """The block knob's block at `level`: the first `level` names of one drawn order.

    The order is the target ledger's two stage tools and the table's first six reads, then
    the table's other reads, then the read copies, each part in a drawn order of its own
    digits; so the first eight slots are the same at every level (N28), every level's
    block is the start of the next one's, and a level adds tools and changes none it
    already offered.  The digits come from the block knob's own domain, never the
    scenario's draw, so no task of another knob moves (K1.1), and the draw does not read
    the level.  The census (`structure_space`) counts exactly the orders this can make.
    """
    reads = _read_names(spec)
    head_reads = _BLOCK_HEAD - _D_B
    head = list(_stage_tools_of(spec, qualifier)[:_D_B]) + list(reads[:head_reads])
    others = list(reads[head_reads:])
    aliases = list(_aliased_reads(spec))
    radices = (
        tuple(range(len(head), 1, -1))
        + tuple(range(len(others), 1, -1))
        + tuple(range(len(aliases), 1, -1))
    )
    material = b"".join(
        _prf(_BLOCK_DOMAIN + b"/" + str(index).encode("ascii"), seed, split)
        for index in range(_BLOCK_DRAW_BLOCKS)
    )
    digits = _mixed_radix(material, radices)
    first = len(head) - 1
    second = first + len(others) - 1
    order = (
        [head[i] for i in _permutation(digits[:first], len(head))]
        + [others[i] for i in _permutation(digits[first:second], len(others))]
        + [aliases[i] for i in _permutation(digits[second:], len(aliases))]
    )
    if level > len(order):
        raise ValueError(
            f"a block offers at most {len(order)} tools, the two the task needs and every "
            f"read name the table can make, not {level}"
        )
    return tuple(order[:level])


def _shape_block(
    spec: _EngineSpec, qualifier: str, permutation: tuple[int, ...], targets: tuple[_Target, ...]
) -> tuple[str, ...]:
    """A shape task's block, in engine names: B's block holding exactly the stage tools the
    width needs, every target's ledger's stage tools up to its goal, and B's reads to sixteen.

    B's base list is the target ledger's two stage tools and then fourteen reads, permuted by
    the scenario's slot draw.  Here the first two places hold the first two stage tools the
    width needs, the last two places, B's last two reads', hold any others, and the twelve
    reads between keep their places.  So the width that needs exactly B's stage tools has
    B's block, the stage tools take the same four slots at every other width, and no read
    moves between widths.  Nothing above a target's goal is listed, so no tool in the block
    can carry any target past it, and the block is sixteen at every width (N33).
    """
    size = _block_size(spec)
    needed = tuple(
        dict.fromkeys(
            tool
            for ledger, _record, goal in targets
            for tool in _stage_tools_of(spec, ledger)[:goal]
        )
    )
    reads = _read_names(spec)[: size - len(needed)]
    base = list(needed[:_D_B]) + list(reads) + list(needed[_D_B:])
    if len(base) != size or len(needed) < _D_B:
        raise ValueError(
            f"the vocabulary table cannot fill a {size}-slot block for shape: {len(needed)} "
            f"stage tools needed and {len(reads)} reads available"
        )
    return tuple(base[index] for index in permutation)


def _quiet_against(name: str, core: tuple[str, ...], pieces: tuple[str, ...]) -> bool:
    """True when `name` adds no instruction token the always-present tools already carry.

    A distractor that did would put a piece into N7's overlap set at one level and not at
    another, which is the same failure as a read dropping out, from the other side.
    """
    lowered = name.lower()
    for piece in pieces:
        if piece in lowered and not any(piece in other.lower() for other in core):
            return False
    return True


# ---------------------------------------------------------------------------
# the prompts
# ---------------------------------------------------------------------------


def _goal_stage_index(spec: _EngineSpec, arm: _ArmSpec) -> int:
    """The stage the task asks for: the level for knob D, `d_R` for every R level, and for
    a shape arm the four stage calls shared out over the width, each target's chain."""
    if arm.knob == _DEPTH:
        return arm.level
    if arm.knob == _SHAPE:
        return _SHAPE_CALLS // arm.level
    return _D_R


def _shape_other_ledgers(width: int) -> int:
    """How many ledgers besides the target's a shape task at `width` advances the target
    record in: three at the widest width, none at the others."""
    return width - 1 if width == _FOUR_LEDGERS else 0


def _shape_ledgers(
    spec: _EngineSpec, seed: int, split: str, qualifier: str, count: int
) -> tuple[str, ...]:
    """The `count` other ledgers a shape task advances the target record in, in drawn order:
    an ordered selection of the ledgers that are not the target's, from the knob's own domain,
    so no task of another knob moves with it.  The draw reads the seed and the split and never
    the target ledger, which it only leaves out."""
    others = tuple(other for other in spec.qualifiers if other != qualifier)
    if count > len(others):
        raise ValueError(
            f"a shape task advances the target record in {count + 1} ledgers and the table "
            f"has {len(spec.qualifiers)}"
        )
    radices = tuple(range(len(others), len(others) - count, -1))
    digits = _mixed_radix(_prf(_SHAPE_DOMAIN, seed, split), radices)
    return tuple(others[index] for index in _selection(digits, len(others)))


def _shape_targets(
    spec: _EngineSpec,
    seed: int,
    split: str,
    qualifier: str,
    record: str,
    decoy: str,
    width: int,
    goal: int,
) -> tuple[_Target, ...]:
    """A shape task's targets at `width`, each to reach `goal`, the goal record first: at
    width one the target record alone, through four stages; at width two that record and the
    decoy, which the scenario holds in the same ledger, two stages each; at width four the
    target record in the target ledger and in three others drawn for the task, one stage
    each.  The request lists them in this order and the reference advances them in it."""
    first = (qualifier, record, goal)
    if width == _ONE_CHAIN:
        return (first,)
    if width == _TWO_RECORDS:
        return (first, (qualifier, decoy, goal))
    if width == _FOUR_LEDGERS:
        others = _shape_ledgers(spec, seed, split, qualifier, _shape_other_ledgers(width))
        return (first,) + tuple((other, record, goal) for other in others)
    raise ValueError(f"no shape task advances {width} records side by side")


def _shape_slots(
    spec: _EngineSpec, targets: tuple[_Target, ...], code: str
) -> tuple[tuple[str, str], ...]:
    """A shape task's slots, in template order: the stage ladder, one goal line per target in
    the knob's own slot, and the entry code.  The goal lines are the knob, so N6 leaves that
    slot out; every other slot is the same at every width."""
    lines = "\n".join(
        _GOAL_LINE.format(
            **{
                _SLOT_RECORD: record,
                _SLOT_CLASS: ledger,
                _SLOT_GOAL: spec.stage_names[goal - 1],
            }
        )
        for ledger, record, goal in targets
    )
    return (
        (_SLOT_LADDER, _LADDER_SEPARATOR.join(spec.stage_names)),
        (_SLOT_GOALS, lines),
        (_SLOT_ENTRY, code),
    )


def _spread_reads(spec: _EngineSpec, seed: int, split: str) -> tuple[_Call, ...]:
    """A spread task's four named reads, in the order the request lists them: four different
    read tools of B's fourteen, each with a catalogue item and a page key, drawn from the knob's
    own domain, so no task of another knob moves with it.

    The draw reads the seed and the split and never the level, so the four are the same at
    every level (N35); its order is the listed order, which decides which read holds which part.
    One draw, one image: an ordered selection of the tools, then an item and a page for each.
    """
    reads = _read_names(spec)[: _block_size(spec) - _D_R]
    items = _catalogue_items(spec)
    pages = _page_keys(spec)
    item_param = _param(spec, "item")
    page_param = _param(spec, "page")
    radices = (
        tuple(range(len(reads), len(reads) - _SPREAD_READS, -1))
        + (len(items),) * _SPREAD_READS
        + (len(pages),) * _SPREAD_READS
    )
    digits = _mixed_radix(_prf(_SPREAD_DOMAIN, seed, split), radices)
    tools = [reads[index] for index in _selection(digits[:_SPREAD_READS], len(reads))]
    return tuple(
        (
            tool,
            {
                item_param: items[digits[_SPREAD_READS + position]],
                page_param: pages[digits[2 * _SPREAD_READS + position]],
            },
        )
        for position, tool in enumerate(tools)
    )


def _spread_lines(spec: _EngineSpec, reads: tuple[_Call, ...]) -> str:
    """The named reads as the request lists them, one numbered line each, in the knob's own
    slot: the read's facet as the engine's read describes it, its item and its page."""
    item_param = _param(spec, "item")
    page_param = _param(spec, "page")
    return "\n".join(
        _READ_LINE.format(
            index=position + 1,
            facet=spec.read_tools[tool],
            item=args[item_param],
            page=args[page_param],
        )
        for position, (tool, args) in enumerate(reads)
    )


def _spread_parts(code: str, level: int) -> tuple[str, ...]:
    """What each of the four named reads answers at `level`, in the listed order: the entry
    code in `level` parts as evenly as it goes, the earlier parts longer, in the first `level`
    reads, and nothing in the rest (N35).  Entry codes are four to eight letters, so four parts
    always exist."""
    parts: list[str] = []
    start = 0
    for size in _split_evenly(len(code), level):
        parts.append(code[start : start + size])
        start += size
    return tuple(parts) + ("",) * (_SPREAD_READS - level)


def _prompt_slots(
    spec: _EngineSpec,
    arm: _ArmSpec,
    record: str,
    code: str,
    qualifier: str,
    number: str | None,
) -> tuple[tuple[str, str], ...]:
    """The template's filled slots, in template order.

    N6 pins the slots' token count and never their values.  Every slot but the goal stage
    is equal across a knob's arms by construction, and the goal stage name is one token
    for every stage the table names -- which is what makes N6 an equality a level change
    can pass.  A similarity task names its ledger by `number` in the class slot's place.
    """
    stage = _goal_stage_index(spec, arm)
    return (
        (_SLOT_RECORD, record),
        (_SLOT_CLASS, qualifier) if number is None else (_SLOT_NUMBER, number),
        (_SLOT_LADDER, _LADDER_SEPARATOR.join(spec.stage_names)),
        (_SLOT_GOAL, spec.stage_names[stage - 1]),
        (_SLOT_ENTRY, code),
    )


def _template_of(slots: tuple[tuple[str, str], ...]) -> tuple[str, str]:
    """The template id and the template the slots fill: the one that names the ledger by
    number when the slots carry a number, the one that lists goal lines when the slots carry
    them, the one that names four reads when the slots carry them, else the one that names the
    ledger by class."""
    if any(name == _SLOT_NUMBER for name, _value in slots):
        return _NUMBER_TEMPLATE_ID, _NUMBER_TEMPLATE
    if any(name == _SLOT_GOALS for name, _value in slots):
        return _GOALS_TEMPLATE_ID, _GOALS_TEMPLATE
    if any(name == _SLOT_READS for name, _value in slots):
        return _SPREAD_TEMPLATE_ID, _SPREAD_TEMPLATE
    return _TEMPLATE_ID, _USER_TEMPLATE


def _render_instruction(slots: tuple[tuple[str, str], ...]) -> str:
    """The user instruction.

    It names the whole stage ladder at every level and designates the goal within it.
    That is forced, not chosen: knob D's block carries every stage tool of the target
    class at every level (N4), so a prompt naming only the goal would put a different
    stage word in N7's overlap set at every level and generation would refuse its own
    contrast.  The target class is named exactly once (the design's lexical rule).
    """
    _template_id, template = _template_of(slots)
    return template.format(**dict(slots))


def _filler(base: str, tokens: int) -> str:
    """The R control's filler, at exactly `tokens` reference-tokenizer tokens.

    Measured as what the suffix adds to the system prompt, so the passage is grown a word
    at a time until the whole prompt lands on its target rather than counted on its own
    and assumed additive.
    """
    if tokens <= 0:
        return ""
    want = _count_tokens(base) + tokens
    words: list[str] = []
    for step in range(tokens * 2 + 2):
        candidate = words + [_FILLER_WORDS[step % len(_FILLER_WORDS)]]
        if _count_tokens(base + _FILLER_PREFIX + " ".join(candidate)) > want:
            break
        words = candidate
        if _count_tokens(base + _FILLER_PREFIX + " ".join(words)) == want:
            break
    if not words:
        return ""
    return _FILLER_PREFIX + " ".join(words)


def _argument_values(seed: int, split: str, record: str) -> tuple[str, ...]:
    """The six words an arguments task's stage calls may have to carry, one per argument
    parameter in `_ARGUMENT_CODES`' order: an ordered selection of the split's record-id
    words that are not words of the task's own record id, drawn from the knob's own domain.

    Record-id words because vocabulary v2 keeps both lists out of every tool name (N7, N31),
    each is one reference token, and the splits' lists are disjoint, so the values move with
    the split as the record id does.  The level is no input: a level states the first
    `level - 2` of the six, so each level states what the level below states, and more.  Six
    different words, none of the record's: a value in the wrong parameter, or the record's
    own words in one, is wrong in a way the check can see.
    """
    _count, separator = _record_id_shape()
    taken = set(record.split(separator))
    words = tuple(word for word in _record_id_words(split) if word not in taken)
    radices = tuple(range(len(words), len(words) - len(_ARGUMENT_CODES), -1))
    digits = _mixed_radix(_prf(_ARGUMENT_DOMAIN, seed, split), radices)
    return tuple(words[index] for index in _selection(digits, len(words)))


def _stated_values(seed: int, split: str, record: str, level: int) -> dict[str, str]:
    """The values an arguments arm at `level` states, each under its parameter: the first
    `level - 2` of the task's six words.  None at the knob's base level."""
    values = _argument_values(seed, split, record)
    return dict(zip(_ARGUMENT_CODES[: level - _ENGINE_ARGUMENTS], values, strict=False))


def _stated_text(stated: dict[str, str]) -> str:
    """The stated values as the request states them and the knob's own slot holds them:
    each parameter's name in words, then its value in double quotes, as the record id and the
    entry code are quoted, so a model reads which parameter takes which value as it reads
    which record takes which code.  Empty when nothing is stated."""
    return ", ".join(f'{name.replace("_", " ")} "{value}"' for name, value in stated.items())


def _with_stated(instruction: str, stated_text: str) -> str:
    """B's request, then one sentence stating the values when there are any.  The sentence's
    own words, like the template's, carry no token a tool name carries (N7)."""
    return instruction + (f"\nCarry {stated_text}." if stated_text else "")


# ---------------------------------------------------------------------------
# the reference solution, and the pairs N9 compares
# ---------------------------------------------------------------------------


def _status_of(observation: str) -> str:
    return observation.split()[1]


def _payload_of(observation: str) -> str:
    return observation.split()[2]


def _chain_calls(
    spec: _EngineSpec, scenario: _Scenario, qualifier: str, record: str, depth: int, seq_start: int
) -> tuple[tuple[_Call, ...], tuple[str, ...]]:
    """`depth` dependent stage transitions on one record, and their observations.

    Each call waits on the token the call before it returned, which is E3's precondition
    and what makes the minimal path exactly `depth` (G5).
    """
    stage_tools = _stage_tools_of(spec, qualifier)
    if depth > len(stage_tools):
        raise ValueError(f"stage {depth} is past the {len(stage_tools)}-stage ladder")
    record_param = _param(spec, "record")
    entry_param = _param(spec, "entry")
    token_param = _param(spec, "token")
    state = _init_state(scenario, seq_start)
    calls: list[_Call] = []
    observations: list[str] = []
    token: str | None = None
    for index in range(depth):
        if index == 0:
            args = {record_param: record, entry_param: scenario.records[(qualifier, record)]}
        else:
            args = {record_param: record, token_param: str(token)}
        call: _Call = (stage_tools[index], args)
        state, observation = _apply(state, call)
        if _status_of(observation) != _OK_STATUS:
            raise ValueError(f"the reference chain was refused at stage {index + 1}: {observation}")
        token = _payload_of(observation)
        calls.append(call)
        observations.append(observation)
    return tuple(calls), tuple(observations)


def _shape_calls(
    spec: _EngineSpec, scenario: _Scenario, targets: tuple[_Target, ...], seq_start: int
) -> tuple[tuple[_Call, ...], tuple[str, ...]]:
    """A shape task's reference: four stage calls over the targets, stage by stage, every
    target's first stage in the targets' order, then every second, and so on, with their
    observations numbered from `seq_start`.

    Each record's calls are its ledger's stage tools from the first up to its goal, the first
    with the entry code and each later one with the token the call before it on that record
    returned (E3's precondition, as a chain's).  So the reference is the batched episode made
    one call per turn, and a model that batches a stage's calls into one turn meets the same
    answers in the same order.
    """
    record_param = _param(spec, "record")
    entry_param = _param(spec, "entry")
    token_param = _param(spec, "token")
    state = _init_state(scenario, seq_start)
    tokens: dict[tuple[str, str], str] = {}
    calls: list[_Call] = []
    observations: list[str] = []
    for stage in range(1, max(goal for _ledger, _record, goal in targets) + 1):
        for ledger, record, goal in targets:
            if goal < stage:
                continue
            stage_tools = _stage_tools_of(spec, ledger)
            if stage > len(stage_tools):
                raise ValueError(f"stage {stage} is past the {len(stage_tools)}-stage ladder")
            if stage == 1:
                args = {record_param: record, entry_param: scenario.records[(ledger, record)]}
            else:
                args = {record_param: record, token_param: tokens[(ledger, record)]}
            call: _Call = (stage_tools[stage - 1], args)
            state, observation = _apply(state, call)
            if _status_of(observation) != _OK_STATUS:
                raise ValueError(
                    f"the reference was refused at stage {stage} of record {record!r} in the "
                    f"{ledger} ledger: {observation}"
                )
            tokens[(ledger, record)] = _payload_of(observation)
            calls.append(call)
            observations.append(observation)
    return tuple(calls), tuple(observations)


def _planned_chain(
    scenario: _Scenario,
    chain: tuple[_Call, ...],
    seq_start: int,
    plan: dict[str, int],
    kind: str = _UNAVAILABLE_STATUS,
) -> tuple[tuple[_Call, ...], tuple[str, ...]]:
    """The chain with the plan applied, numbered from `seq_start`: each planned answer's call
    answered the kind's line, and the same call, arguments and all, made again until it is
    answered.  Through the one function the tool server and `verify` apply the plan with, so
    the reference meets exactly the answers a model would."""
    state = _init_state(scenario, seq_start)
    counts: dict[str, int] = {}
    calls: list[_Call] = []
    observations: list[str] = []
    for call in chain:
        while True:
            state, counts, observation = _surface.apply_planned(
                state, counts, call, plan, kind=kind
            )
            calls.append(call)
            observations.append(observation)
            if _status_of(observation) != kind:
                break
    return tuple(calls), tuple(observations)


def _fault_pair_tokens(
    spec: _EngineSpec,
    scenario: _Scenario,
    arm: _ArmSpec,
    qualifier: str,
    record: str,
    depth: int,
) -> int:
    """N26's target for a faults, timeouts or ratelimits control: the reference tokens of the
    fault pairs it stands in for, the high level's less its own level's.  A fault pair is a
    planned call and its answer in the knob's word, measured as N9's unit and numbered as the
    plain arm numbers them."""
    chain, _observations = _chain_calls(spec, scenario, qualifier, record, depth, 1)
    path = tuple(name for name, _args in chain)
    kind = _surface.fault_kind(_arm_id(arm)) or _UNAVAILABLE_STATUS

    def tokens(level: int) -> int:
        plan = _surface.fault_plan(_arm_id(_replace(arm, level=level, control=None)), path)
        calls, observations = _planned_chain(scenario, chain, 1, plan, kind)
        return sum(
            _pair_tokens(name, args, observation)
            for (name, args), observation in zip(calls, observations, strict=True)
            if _status_of(observation) == kind
        )

    return tokens(arm.control or 0) - tokens(arm.level)


def _history_pairs(spec: _EngineSpec, reads: tuple[str, ...], target: int) -> int:
    """N23's starting count for a history arm: `round(target / m)`, with `m` the median
    reachable read-pair total in the block at the first seeded position.  An observation
    carries its `seq`, so each position has its own totals; the first is the one every count
    has.  The search then moves single pairs until the total is the target."""
    totals = [option[0] for option in _read_options(spec, reads, 1)]
    if not totals:
        raise ValueError("this vocabulary table offers no orthogonal read pair to seed with")
    # `_read_options` is sorted by total first, so the middle of its totals is their median.
    half = len(totals) // 2
    median = totals[half] if len(totals) % 2 else (totals[half - 1] + totals[half]) / 2
    return round(target / median)


def _fewest_pairs_reaching(spec: _EngineSpec, reads: tuple[str, ...], target: int) -> int:
    """The fewest seeded read pairs whose reachable totals bracket `target`: the first count
    whose largest total reaches it, which is also the first whose smallest total can still be
    at or below it.  Where no count brackets the target this is the nearest count above it,
    the search then gets as near as the table allows, and the ledger's N26 refuses the
    contrast rather than this refusing the arm."""
    pairs, highest = 0, 0
    while highest < target:
        pairs += 1
        highest += _read_options(spec, reads, pairs)[-1][0]
    return pairs


def _pair_tokens(name: str, args: _Args, observation: str) -> int:
    """N9's unit, rendered the way the ledger measures it: the name bare, the arguments as one
    compact JSON object, the observation as it stands."""
    rendered = args if isinstance(args, str) else _json.dumps(args, separators=(",", ":"))
    return _count_tokens(name) + _count_tokens(rendered) + _count_tokens(observation)


_READ_OPTIONS: dict[tuple[str, str, int], tuple[_Option, ...]] = {}


def _read_options(spec: _EngineSpec, reads: tuple[str, ...], seq: int) -> tuple[_Option, ...]:
    """Every seeded read pair available at one sequence number, by token total.

    A read call's observation is the catalogue's own value for that item and facet, so
    the whole table is a property of the vocabulary and not of a scenario -- which is why
    it is built once per `(table, reads, seq)` and shared by every control arm.
    """
    key = (spec.canonical, "\x1f".join(reads), seq)
    cached = _READ_OPTIONS.get(key)
    if cached is not None:
        return cached
    item_param = _param(spec, "item")
    page_param = _param(spec, "page")
    scenario = _Scenario(
        records={}, token_key=b"read-options", visible_items=_catalogue_items(spec)
    )
    state = _init_state(scenario, seq)
    rows: list[_Option] = []
    for name in reads:
        for item in _catalogue_items(spec):
            for page in _page_keys(spec):
                args = {item_param: item, page_param: page}
                _after, observation = _apply(state, (name, args))
                if _status_of(observation) != _OK_STATUS:
                    continue
                rows.append((_pair_tokens(name, args, observation), name, args, observation))
    rows.sort(key=lambda row: (row[0], row[1], tuple(sorted(row[2].items())), row[3]))
    options = tuple(rows)
    _READ_OPTIONS[key] = options
    return options


def _seeded_block(
    spec: _EngineSpec, reads: tuple[str, ...], pairs: int, target: int
) -> tuple[_Option, ...]:
    """`pairs` seeded read pairs whose token total is `target`, or as near as the table
    allows.

    N9 is an aggregate and never a per-pair equality: the design's own measurement is that
    roughly half the emitted chain calls are cheaper on arguments than any read call, so
    the seeded floor sits above the per-call total and only the sum can be matched.  The
    read pair's reachable totals are consecutive, so a one-token walk closes the residual;
    it takes a search and not a formula, because the observation carries its own `seq` and
    so each position has its own reachable set.
    """
    rows = [_read_options(spec, reads, position + 1) for position in range(pairs)]
    if any(not row for row in rows):
        raise ValueError("this vocabulary table offers no orthogonal read pair to seed with")
    by_total = [{option[0]: option for option in reversed(row)} for row in rows]
    chosen = [row[len(row) // 2] for row in rows]
    for _step in range(_SEARCH_STEPS):
        residual = sum(option[0] for option in chosen) - target
        if residual == 0:
            break
        moved = False
        for position, table in enumerate(by_total):
            wanted = chosen[position][0] - (1 if residual > 0 else -1)
            candidate = table.get(wanted)
            if candidate is not None:
                chosen[position] = candidate
                moved = True
                break
        if not moved:
            break
    return tuple(chosen)


def _seeded_messages(instruction: str, block: tuple[_Option, ...]) -> tuple[dict[str, _Any], ...]:
    """G13's shape: a user message, then assistant messages carrying one `tool_calls`
    entry each, every one matched by a tool message whose `tool_call_id` is that call's
    id.  The OpenAI chat shape, because N18 pins the endpoint type to that."""
    messages: list[dict[str, _Any]] = [{"role": "user", "content": instruction}]
    for index, (_total, name, args, observation) in enumerate(block):
        call_id = f"call_{index}"
        messages.append(
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": _json.dumps(args, separators=(",", ":")),
                        },
                    }
                ],
            }
        )
        messages.append({"role": "tool", "tool_call_id": call_id, "content": observation})
    return tuple(messages)


# ---------------------------------------------------------------------------
# G8 - the generated negative controls
# ---------------------------------------------------------------------------


def _negative_controls(
    spec: _EngineSpec,
    scenario: _Scenario,
    arm: _ArmSpec,
    qualifier: str,
    record: str,
    decoy: str,
    split: str,
    block: tuple[str, ...],
    reference: tuple[_Call, ...],
    final_token: str | None,
    stated: dict[str, str] | None = None,
    targets: tuple[_Target, ...] | None = None,
) -> dict[str, tuple[_Call, ...]]:
    """One control per system label a call sequence can produce.

    `stated` is an arguments arm's stated values: a stage call this adds to the reference
    carries them too, or the check would refuse it and the control would pass instead of
    giving its label.  `targets` is the records the task advances, the goal record first;
    every task but a shape task's has the one, the goal record at the goal stage.

    `passed` is `reference_calls` itself and `verifier_error` is fault-injected, so
    neither is generated.  Format-check clause 1 depends on a family's raw format and is
    exercised through each model's own serving stack, so this generates clauses 2,
    3 and 4 at the call level and not clause 1.
    """
    record_param = _param(spec, "record")
    entry_param = _param(spec, "entry")
    token_param = _param(spec, "token")
    code = scenario.records[(qualifier, record)]
    stage_tools = _stage_tools_of(spec, qualifier)
    if targets is None:
        targets = ((qualifier, record, _goal_stage_index(spec, arm)),)
    goal = targets[0][2]

    controls: dict[str, tuple[_Call, ...]] = {}
    controls[_WRONG_STATE] = reference[:-1]
    controls[_TURN_LIMIT] = reference
    # The decoy id in the target class: knob D's block holds no other class's tools, so
    # this is the only mutation of another record any call inside the block can make.  A
    # task that advances the decoy too, shape's two-record width, has no such control: every
    # stage tool in its block is the target ledger's, both of whose records are targets, so
    # no call in the block can change a record that is not one.
    if (qualifier, decoy) not in {(ledger, moved) for ledger, moved, _goal in targets}:
        controls[_COLLATERAL] = reference + (
            (stage_tools[0], {record_param: decoy, entry_param: code, **(stated or {})}),
        )
    # `overshoot` needs a tool in the block that carries the target past the goal.  At the
    # top stage there is none, and knob R's block holds stages 1 and 2 alone, so there is
    # none there either; G7 is carried by `collateral_mutation` in both cases.
    if goal < len(stage_tools) and stage_tools[goal] in block and final_token is not None:
        controls[_OVERSHOOT] = reference + (
            (stage_tools[goal], {record_param: record, token_param: str(final_token)}),
        )

    if arm.knob == _SIMILARITY:
        # A lookalike is another ledger's real first stage tool, and the scenario holds the
        # target record in every ledger under the one entry code, so the reference's first
        # call aimed at the first-stage lookalike in the lowest slot succeeds on the wrong
        # ledger: a side effect strict fails and leaky passes.
        lookalike = next(
            name
            for name in block
            if name in spec.stage_tools
            and spec.stage_tools[name][0] == 0
            and name != stage_tools[0]
        )
        controls[f"{_COLLATERAL}_lookalike"] = reference + (
            (lookalike, {record_param: record, entry_param: code}),
        )

    in_block = reference[0][0] if reference else block[0]
    controls[f"{_MALFORMED}_clause_2"] = ((in_block, ("not", "an", "object")),)
    controls[f"{_MALFORMED}_clause_3"] = (_outside_call(spec, scenario, split, block),)
    controls[f"{_MALFORMED}_clause_4"] = ((in_block, {record_param: record}),)
    return controls


def _outside_call(
    spec: _EngineSpec, scenario: _Scenario, split: str, block: tuple[str, ...]
) -> _Call:
    """A call naming a real tool outside the block that mutates nothing.

    A read is preferred, because a control that disturbed the chain could not be prefixed
    to a passing episode -- which is how the tests separate "fell short of `passed`"
    from the label order.  On a table too small to leave a read outside the
    block, a stage tool of another class aimed at a record the scenario does not hold is
    `no_such_rec` and mutates nothing either.
    """
    item_param = _param(spec, "item")
    page_param = _param(spec, "page")
    record_param = _param(spec, "record")
    entry_param = _param(spec, "entry")
    for name in _read_names(spec):
        if name not in block:
            return (
                name,
                {item_param: _catalogue_items(spec)[0], page_param: _page_keys(spec)[0]},
            )
    for name in sorted(spec.stage_tools):
        if name not in block:
            return (
                name,
                {
                    record_param: _absent_record_id(scenario, split),
                    entry_param: _entry_codes(spec)[0],
                },
            )
    raise ValueError("every tool the table defines is already in this block")


# ---------------------------------------------------------------------------
# the format check
# ---------------------------------------------------------------------------


def _schema_ok(tool: dict[str, _Any], args: dict[str, _Any]) -> bool:
    """The tool's own JSON schema: every required parameter present, none the tool does not
    list, and every value a string.

    A schema that names no required parameters requires them all.  Every schema generated
    so far requires all of its parameters, so for those this is "exactly its parameters".
    """
    properties = tool["parameters"]["properties"]
    required = tool["parameters"].get("required", tuple(properties))
    if not set(required) <= set(args) <= set(properties):
        return False
    return all(isinstance(value, str) for value in args.values())


def _format_clauses(
    turns: tuple[Turn, ...], fmt: FormatSpec, block: dict[str, dict[str, _Any]]
) -> set[int]:
    """Every clause that fired, over the whole episode.

    Every clause is collected rather than the first: an episode can break two of them in
    two turns, and one call can break two at once, and the *lowest-numbered* one is what
    `verify` reports -- so a reader comparing two runs of one episode under
    two builds is comparing the same thing.
    """
    fired: set[int] = set()
    for turn in turns:
        content = str(turn.content)
        if not turn.calls and any(marker in content for marker in fmt.markers):
            fired.add(1)
        for name, args in turn.calls:
            if not isinstance(args, dict):
                fired.add(2)
            tool = block.get(name)
            if tool is None:
                fired.add(3)
            elif isinstance(args, dict) and not _schema_ok(tool, args):
                fired.add(4)
    return fired


# ---------------------------------------------------------------------------
# the verifier
# ---------------------------------------------------------------------------


def _reaches_the_server(name: _Any, args: _Any, block: dict[str, dict[str, _Any]]) -> bool:
    """Whether the harness forwards a call to the tool server, applied per call as the
    verifier sees it: the arguments a JSON object and the name one the block shows.  Any other
    call the harness answers itself, with a line that carries no sequence number, and the
    server never receives it, so it takes no planned failure."""
    return isinstance(args, dict) and isinstance(name, str) and name in block


def verify(
    bundle: TaskBundle,
    turns: tuple[Turn, ...],
    ended_with_reply: bool,
    turn_limit_hit: bool,
    fmt: FormatSpec,
    spec: _EngineSpec | None = None,
) -> Verdict:
    """The verdict on one episode: a pure function of the bundle, the turns and the two
    flags (G9).

    Every raise inside becomes `verifier_error`, and there is no default-to-pass path
    (G10): a bundle whose stored initial state disagrees with its own derivation, or whose
    goal is not one of the records its expected state moves, is a defective bundle and not a
    failed episode, and an episode that neither replied nor hit
    the turn limit ended for a reason these five arguments cannot see -- both of which are
    instrument conditions, and an instrument condition may never wear a system label.
    """
    try:
        return _verdict(bundle, tuple(turns), ended_with_reply, turn_limit_hit, fmt, spec)
    except Exception:
        return Verdict(
            strict_label=_VERIFIER_ERROR,
            leaky_pass=False,
            label=_VERIFIER_ERROR,
            mutations=(),
            format_clause=None,
        )


def _verdict(
    bundle: TaskBundle,
    turns: tuple[Turn, ...],
    ended_with_reply: bool,
    turn_limit_hit: bool,
    fmt: FormatSpec,
    spec: _EngineSpec | None,
) -> Verdict:
    engine_spec = _resolve(spec)
    scenario = scenario_for(bundle.seed, bundle.split, engine_spec)
    start = _init_state(scenario, bundle.seq_start)
    if _records_value(start) != tuple(bundle.initial_state):
        raise ValueError(
            "the bundle's initial state disagrees with "
            "init_state(scenario_for(seed, split), seq_start)"
        )

    block = {str(tool["name"]): tool for tool in bundle.tools}
    fired = _format_clauses(turns, fmt, block)
    clause = min(fired) if fired else None

    # The block's names are what the model was shown; the engine is called by its own.  The
    # map is read through the module, so the verifier, the generator and the tool server
    # cannot disagree about it, and a name the block does not show reaches the engine as no
    # tool: the harness refuses such a call, so the replay must not let it move a record.
    shown = _surface.display_map(
        bundle.seed, bundle.split, bundle.arm_id, bundle.goal, tuple(block)
    )
    # The arm's planned failures, derived as the tool server derives them and applied through
    # the same function, counted over the calls the server received: a call the harness
    # answered itself takes none, and reaches the engine here as it always has, as no tool or
    # as arguments the engine refuses, changing nothing.
    plan = _surface.reference_plan(bundle.arm_id, shown, bundle.reference_calls)
    kind = _surface.fault_kind(bundle.arm_id) or _UNAVAILABLE_STATUS
    # An arguments arm's stated values, read off the reference as the tool server and the
    # record reader read them, applied by the same function: a stage call that does not carry
    # exactly them is refused there and moves no record here either.
    stated = _surface.stated_values(bundle.arm_id, shown, bundle.reference_calls)
    # A spread arm's named reads and their answers, read off the reference as the tool server
    # and the record reader read them, answered by the same function: a read moves no record,
    # so the verdict cannot see them, but the replay is then the one the server made.
    spread = _surface.spread_answers(
        bundle.arm_id, shown, bundle.reference_calls, bundle.reference_observations
    )
    state = start
    counts: dict[str, int] = {}
    for turn in turns:
        for name, args in turn.calls:
            call: _Call = (_surface.engine_name(shown, name), args)
            if _reaches_the_server(name, args, block):
                state, counts, _observation = _surface.apply_planned(
                    state, counts, call, plan, stated=stated, spread=spread, kind=kind
                )
            else:
                state, _observation = _apply(state, call)
    final = _records_value(state)
    changed = tuple(_mutations(start, state))

    expected = tuple(bundle.expected_final_state)
    targets = _targets(bundle)
    cls, record, goal = bundle.goal
    if targets.get((cls, record)) != goal:
        raise ValueError(
            "the bundle's goal is not one of the records its expected final state moves, at "
            "the stage it moves it to"
        )
    stages = {key: state.records[key].stage for key in targets}
    leaky_pass = all(stages[key] >= wanted for key, wanted in targets.items())

    if not ended_with_reply and not turn_limit_hit:
        # No system label covers it, and giving it one is A4's failure inverted: the
        # adapter's `api_error` or `wall_timeout` is the label that wins downstream.
        return Verdict(
            strict_label=_VERIFIER_ERROR,
            leaky_pass=False,
            label=_VERIFIER_ERROR,
            mutations=changed,
            format_clause=clause,
        )

    strict_label = _strict_label(
        final, expected, targets, stages, changed, ended_with_reply, turn_limit_hit, clause
    )
    if strict_label in _ADAPTER_ONLY:  # pragma: no cover - the adapter's three
        raise ValueError(f"{strict_label} is the adapter's to assign, never the verifier's")

    if strict_label == _VERIFIER_ERROR:
        label = strict_label
    elif bundle.verifier.strictness == _LEAKY and leaky_pass:
        label = _PASSED
    else:
        label = strict_label
    return Verdict(
        strict_label=strict_label,
        leaky_pass=leaky_pass,
        label=label,
        mutations=changed,
        format_clause=clause,
    )


def _targets(bundle: TaskBundle) -> dict[tuple[str, str], int]:
    """A task's targets: the records whose stage differs between its initial and its
    expected records, each with the stage it is to reach.

    Read from the records and not from `goal`, which names the first target and keeps its
    shape, so a task that moves more than one record needs no new bundle field.  For a task
    with one target this is the `goal` record at the `goal` stage.
    """
    before = {(cls, record): stage for cls, record, stage, _token in bundle.initial_state}
    return {
        (cls, record): stage
        for cls, record, stage, _token in bundle.expected_final_state
        if before.get((cls, record)) != stage
    }


def _strict_label(
    final: _RecordsValue,
    expected: _RecordsValue,
    targets: dict[tuple[str, str], int],
    stages: dict[tuple[str, str], int],
    changed: tuple[tuple[str, str, str], ...],
    ended_with_reply: bool,
    turn_limit_hit: bool,
    clause: int | None,
) -> str:
    """The table's labels, with the pass predicate decided first.

    `malformed_call`'s own definition opens "the episode fell short of `passed`" while the
    table lists it above `passed`; both hold only if the strict predicate is computed
    first and the label order applied to what is left.  So a turn that fails the format
    check in an episode that otherwise passes is `passed`, and the clause is still
    reported.
    """
    if final == expected and ended_with_reply:
        return _PASSED
    if clause is not None:
        return _MALFORMED
    if turn_limit_hit and not ended_with_reply:
        return _TURN_LIMIT
    if any(stages[key] > wanted for key, wanted in targets.items()):
        return _OVERSHOOT
    if any(
        stages[key] < wanted or _row(final, *key) != _row(expected, *key)
        for key, wanted in targets.items()
    ):
        return _WRONG_STATE
    if any((row_cls, row_record) not in targets for row_cls, row_record, _field in changed):
        return _COLLATERAL
    # Unreachable: every target matching expected with nothing else mutated *is* the
    # expected records value, and a reply was made, so the pass predicate fired above.
    return _WRONG_STATE


# ---------------------------------------------------------------------------
# G15, G16 - the masked structure, and the space it is drawn from
# ---------------------------------------------------------------------------


def structural_fingerprint(bundle: TaskBundle) -> str:
    """G15's fingerprint: the first request with the opaque strings masked out.

    What remains is the tool order, the target class, the goal and the catalogue content,
    including the control arm's seeded history -- so a control and its plain arm are
    different structures, and a census that ignored the seeded block would report a space
    the control does not have.  The mask is applied to the slots the template declares
    opaque, never to the rendered string, so no pattern can reach the prose.  A shape arm's
    fingerprint also carries its target list, the ledgers and goal stages of every record
    the task advances, with the record ids masked (`_masked_targets`).
    """
    seeded: list[_Any] = []
    if not isinstance(bundle.prompt, str):
        for message in bundle.prompt:
            if message.get("role") == "assistant":
                for call in message.get("tool_calls") or ():
                    function = call.get("function", {})
                    arguments = _json.loads(function.get("arguments", "{}"))
                    seeded.append([function.get("name"), _mask_arguments(arguments)])
            elif message.get("role") == "tool":
                seeded.append(["observation", _mask_observation(str(message.get("content", "")))])
    body = {
        "system_prompt": bundle.system_prompt,
        "template_id": bundle.template_id,
        "slots": [
            [name, _MASK if name in _OPAQUE_SLOTS else value] for name, value in bundle.prompt_slots
        ],
        "tools": _masked_tools(bundle),
        "target_class": bundle.goal[0],
        "goal_stage": bundle.goal[2],
        "seeded": seeded,
    }
    targets = _masked_targets(bundle)
    if targets is not None:
        body["targets"] = targets
    return _hashlib.sha256(_FINGERPRINT_DOMAIN + _canonical_bytes(body)).hexdigest()


def _masked_targets(bundle: TaskBundle) -> list[list[_Any]] | None:
    """The target list the fingerprint adds for a shape arm, and for no other: each target's
    ledger and goal stage, sorted, the record ids left out as every record id is masked.
    Every other knob's one target is already the target class at the goal stage, and a bundle
    whose arm id names no arm has no knob to add a list for."""
    try:
        knob = _parse_arm_id(bundle.arm_id).knob
    except ValueError:
        return None
    if knob != _SHAPE:
        return None
    return sorted([ledger, stage] for (ledger, _record), stage in _targets(bundle).items())


def _masked_tools(bundle: TaskBundle) -> _Any:
    """The tools as the fingerprint reads them: canonical, in slot order, and for a similarity
    arm with every ledger number masked.

    A number's digits are opaque, as the record id's letters are, but which places a
    lookalike's number shares with the target's is structure (the census counts the kept
    places), so each number in a name or a description is replaced by its pattern against the
    target's: `<==##>` for one sharing the first two places, `<====>` for the target's own.
    Every other knob's tools are read as they are; a bundle whose arm id names no arm has no
    knob to mask for.
    """
    tools = _canon(bundle.tools)
    try:
        knob = _parse_arm_id(bundle.arm_id).knob
    except ValueError:
        return tools
    if knob != _SIMILARITY:
        return tools
    slots = dict(bundle.prompt_slots)
    if _SLOT_NUMBER not in slots:
        raise ValueError("a similarity bundle names its target ledger in the ledger_number slot")
    target = slots[_SLOT_NUMBER]

    def pattern(match: _Any) -> str:
        number = match.group(0)
        places = zip(number, target, strict=True)
        return "<" + "".join("=" if a == b else "#" for a, b in places) + ">"

    return [
        {
            key: _LEDGER_NUMBER.sub(pattern, value) if key in ("name", "description") else value
            for key, value in tool.items()
        }
        for tool in tools
    ]


def _mask_arguments(arguments: dict[str, _Any]) -> dict[str, _Any]:
    """A seeded read's arguments: the catalogue item is content and stays, the page key is
    an opaque string and goes."""
    page = _param(_SPEC, "page")
    return {
        name: (_MASK if name == page else value) for name, value in sorted(arguments.items())
    }


def _mask_observation(observation: str) -> str:
    """The observation with its payload masked: the sequence number and the status word
    are structure, the value the catalogue returned is not."""
    parts = observation.split()
    if len(parts) < 3:
        return observation
    return " ".join(parts[:2] + [_MASK])


def structure_space(arm: _ArmSpec, spec: _EngineSpec | None = None) -> int:
    """The number of distinct masked structures the arm can generate, before any run.

    A property of the arm and never of a draw, which is the whole point: a seed argument
    would make it a property of a sample of the thing it exists to bound.  For knob D that
    is the target class times the slot permutation; knob R's designated slots multiply it
    by the distractor identities its level exposes.

    For a control arm the count is a **lower bound**: the seeded block is a derivation of
    the scenario, so two scenarios sharing a class and a slot order can still seed
    different blocks.  That is the conservative direction for G16's floor, because a
    smaller `k` overstates the chance a run repeats a structure.  A faults arm's first
    request is knob R's base block, prompt and system prompt at every level, so its count is
    that base arm's.  So is a history arm's: its block, system prompt and instruction are the
    base arm's at every level, and its seeded pairs are a derivation of the scenario, as a
    depth control's are, so the count is a lower bound for the levels that seed any.  A block
    arm's count is every tool and its slot, since nothing in its block is masked: the target
    ledger, the order of the first eight slots, the order of the table's other reads in the
    slots they take, and the order of the copies after them; the control counts k8's, a lower
    bound as for every control, its filler being a derivation of k64's block.  An arguments
    arm's count is B's at every level and on the control: its block is B's, its stage tools'
    schemas the same at every level, and the stated values are masked with the record id.  A
    spread arm's count is B's at every level: its block, system prompt and the request's prose
    are B's but for the words every spread request carries, and the named reads are masked
    with the record id.  A shape arm's count is B's too at the widths whose block holds one
    ledger's tools and on the control, the goal lines masked whole; at the width that advances
    the target record in four ledgers it is B's times the choice of the three other ledgers
    among the eleven, each set of four first-stage tools taking every order of the sixteen
    slots, as B's two take every order; the order the three are drawn in is not counted, since
    the slot draw already ranges over it.
    """
    _refuse_a_knob_not_generated(arm)
    engine_spec = _resolve(spec)
    if arm.knob == _SIMILARITY:
        # What the masked block can tell apart: the target class; the right tools' two slots
        # and, among the rest, which two reads stay (they take the first two remaining slots
        # in B's order, so only their identities vary); and the places each lookalike ledger's
        # number shares with the target's.  The lookalike ledgers' identities and the order of
        # the twelve reads they replaced are masked away with the numbers, so they are not
        # counted: counting them would overstate the space, the direction G16's floor must
        # never err in.
        size = _block_size(engine_spec)
        reads = size - _D_R
        placed = _math.perm(size, _D_R) * _math.perm(reads, reads - _LOOKALIKES)
        shared: int = _math.comb(_NUMBER_WIDTH, arm.level) ** _LOOKALIKE_LEDGERS
        return len(engine_spec.qualifiers) * placed * shared
    if arm.knob == _BLOCK:
        reads = len(_read_names(engine_spec))
        others = reads - (_BLOCK_HEAD - _D_B)
        aliases = len(_aliased_reads(engine_spec))
        extra = arm.level - _BLOCK_HEAD
        return (
            len(engine_spec.qualifiers)
            * _math.factorial(_BLOCK_HEAD)
            * _math.perm(others, min(extra, others))
            * _math.perm(aliases, max(extra - others, 0))
        )
    space = len(engine_spec.qualifiers) * _math.factorial(_block_size(engine_spec))
    if arm.knob == _SHAPE:
        others = len(engine_spec.qualifiers) - 1
        return space * _math.comb(others, _shape_other_ledgers(arm.level))
    if arm.knob == _DISTRACTOR and arm.level > 0:
        pool = len(_distractor_pool(engine_spec, engine_spec.qualifiers[0]))
        for position in range(arm.level):
            space *= pool - position
    return space


# ---------------------------------------------------------------------------
# the generator
# ---------------------------------------------------------------------------


def _refuse_a_knob_not_generated(arm: _ArmSpec) -> None:
    """The knobs module names every knob, with its levels, its arm ids and its ledger rows;
    this module makes tasks for `_GENERATED_KNOBS`.  Without the refusal an arm of any other
    knob would be built as a distractor arm under another knob's id."""
    if arm.knob == _LANDED:
        raise ValueError(
            "no landed task is generated on the built-in tasks: the ledger refuses a repeated "
            "stage call and moves nothing, so a write that landed and answered a timeout has "
            "no duplicate for the end-state check to catch; landed is offered on your own "
            "tools, whose store accepts a second write as yours would"
        )
    if arm.knob not in _GENERATED_KNOBS:
        raise ValueError(
            f"no {arm.knob} task can be generated yet: the {arm.knob} knob has its levels, its "
            f"arm ids and its pin-ledger rows, and the generator makes "
            + ", ".join(_GENERATED_KNOBS[:-1])
            + f" and {_GENERATED_KNOBS[-1]} tasks"
        )


def generate(arm: _ArmSpec, seed: int, spec: _EngineSpec | None = None) -> TaskBundle:
    """`(arm, seed)` to a task bundle, with the verifier, a reference solution and the
    negative controls generated alongside the task.

    Byte-identical across runs, processes and platforms, with no model call and no network
    call (G1, G2).  Both splits generate: "v0 emits `eval` only" is the pre-registration's
    choice among what the generator offers, and G12's own first clause is a statement
    about both splits that is untestable if one of them refuses.
    """
    _refuse_a_knob_not_generated(arm)
    engine_spec = _resolve(spec)
    scenario = scenario_for(seed, arm.split, engine_spec)
    qualifier, permutation, pool_order = _drawn_parts(seed, arm.split, engine_spec)

    record = encode_record_id(seed, arm.split)
    decoy = encode_record_id(_decoy_seed(seed, arm.split), arm.split)
    code = scenario.records[(qualifier, record)]
    rendered = _arm_id(arm)
    number = _surface.target_number(seed, arm.split) if arm.knob == _SIMILARITY else None
    goal = _goal_stage_index(engine_spec, arm)
    target = (qualifier, record, goal)
    targets: tuple[_Target, ...] = (target,)
    if arm.knob == _SHAPE:
        # Shape: the width's targets, the goal record first, and a request listing one line
        # per goal in the knob's own slot (N34), the rest of it B's at every width.
        targets = _shape_targets(
            engine_spec, seed, arm.split, qualifier, record, decoy, arm.level, goal
        )
        slots = _shape_slots(engine_spec, targets, code)
    elif arm.knob == _SPREAD:
        # Spread: B's slots but the entry code, then the four named reads in the knob's own
        # slot, which the fingerprint masks (N35); the request states no code.
        spread_reads = _spread_reads(engine_spec, seed, arm.split)
        slots = tuple(
            slot
            for slot in _prompt_slots(engine_spec, arm, record, code, qualifier, number)
            if slot[0] != _SLOT_ENTRY
        ) + ((_SLOT_READS, _spread_lines(engine_spec, spread_reads)),)
    else:
        slots = _prompt_slots(engine_spec, arm, record, code, qualifier, number)
    instruction = _render_instruction(slots)
    stated: dict[str, str] = {}
    if arm.knob == _ARGUMENTS:
        # Arguments: B's request, then the level less two of the task's six values, each
        # stated after its parameter's name (N31), in the knob's own slot too, which the
        # fingerprint masks; both stage calls carry them (below) and the check requires them.
        stated = _stated_values(seed, arm.split, record, arm.level)
        slots = slots + ((_SLOT_STATED, _stated_text(stated)),)
        instruction = _with_stated(instruction, _stated_text(stated))
    if arm.knob == _SIMILARITY:
        block = _similarity_block(engine_spec, seed, arm.split, qualifier, permutation)
    elif arm.knob == _BLOCK:
        block = _sized_block(engine_spec, seed, arm.split, qualifier, arm.level)
    elif arm.knob == _SHAPE:
        block = _shape_block(engine_spec, qualifier, permutation, targets)
    else:
        block = _block_names(engine_spec, arm, qualifier, permutation, pool_order, instruction)
    # The block is built in engine names and shown under the names the surface gives them;
    # the two are one list for every knob but similarity.
    shown_block = _surface.shown_names(seed, arm.split, rendered, target, block)
    tools = _render_block(engine_spec, seed, arm.split, rendered, target, shown_block)

    seq_start = 1
    system_prompt = _SYSTEM_PROMPT
    if arm.knob in _PLANNED_KNOBS:
        system_prompt = system_prompt + "\n" + _FAULT_SENTENCES[arm.knob]
    prompt: str | tuple[dict[str, _Any], ...] = instruction

    if arm.knob == _HISTORY:
        # History: the base task with read pairs seeded before the first move, as a depth
        # control's are (N24), `round(T / m)` of them, searched until their tokens total the
        # level (N23).  A level whose count rounds to none, level 0 among them, seeds nothing
        # and leaves the prompt a string, as the base task's is.
        reads = tuple(name for name in block if name in engine_spec.read_tools)
        pairs = _history_pairs(engine_spec, reads, arm.level)
        if pairs:
            seq_start = pairs + 1
            prompt = _seeded_messages(
                instruction, _seeded_block(engine_spec, reads, pairs, arm.level)
            )
    elif arm.control is not None and arm.knob == _DEPTH:
        pairs = arm.control - arm.level
        seq_start = pairs + 1
        reads = tuple(name for name in block if name in engine_spec.read_tools)
        _high_calls, _high_observations = _chain_calls(
            engine_spec, scenario, qualifier, record, arm.control, 1
        )
        wanted = sum(
            _pair_tokens(name, args, observation)
            for (name, args), observation in zip(
                _high_calls[arm.level :], _high_observations[arm.level :], strict=True
            )
        )
        prompt = _seeded_messages(instruction, _seeded_block(engine_spec, reads, pairs, wanted))
    elif arm.control is not None and arm.knob in _PLANNED_KNOBS:
        # The faults, timeouts or ratelimits control: the base level's task with read pairs
        # seeded before the first move, as long as the fault pairs the high level adds, so a
        # drop can be read against the same length added as earlier tool work.  The fewest
        # pairs whose reachable totals bracket that length (N26), seeded as a depth control's
        # are (N24).
        reads = tuple(name for name in block if name in engine_spec.read_tools)
        wanted = _fault_pair_tokens(engine_spec, scenario, arm, qualifier, record, goal)
        pairs = _fewest_pairs_reaching(engine_spec, reads, wanted)
        seq_start = pairs + 1
        prompt = _seeded_messages(instruction, _seeded_block(engine_spec, reads, pairs, wanted))
    elif arm.control is not None and arm.knob == _BLOCK:
        # The block control: k8's block, plus the neutral filler at the end of the system
        # prompt, as long as what k64's block adds (N29), the R control's mechanism with N3's
        # rule extended to it.  A length-only control; the block's growth is reported.
        high = _replace(arm, level=arm.control, control=None)
        high_block = _sized_block(engine_spec, seed, arm.split, qualifier, arm.control)
        high_tools = _render_block(
            engine_spec, seed, arm.split, _arm_id(high), target, high_block
        )
        system_prompt = system_prompt + _filler(
            system_prompt, _rendered_tokens(high_tools) - _rendered_tokens(tools)
        )
    elif arm.control is not None and arm.knob == _ARGUMENTS:
        # The arguments control: a2's request, plus the neutral filler at its end, as long as
        # what a8's stated values add to the request (N32), where N3 does not look and the
        # filler words keep it neutral.  A length-only control; the schema is the same.
        high_stated = _stated_values(seed, arm.split, record, arm.control)
        wanted = _count_tokens(_with_stated(_render_instruction(slots), _stated_text(high_stated)))
        instruction = instruction + _filler(instruction, wanted - _count_tokens(instruction))
        prompt = instruction
    elif arm.control is not None and arm.knob == _SHAPE:
        # The shape control: w1's request, plus the neutral filler at its end, as long as what
        # w4's goal lines add to the request (N34), where N3 does not look and the filler words
        # keep it neutral.  A length-only control; the block, the targets and the reference
        # are w1's.
        high = _replace(arm, level=arm.control, control=None)
        high_targets = _shape_targets(
            engine_spec,
            seed,
            arm.split,
            qualifier,
            record,
            decoy,
            high.level,
            _goal_stage_index(engine_spec, high),
        )
        high_slots = _shape_slots(engine_spec, high_targets, code)
        wanted = _count_tokens(_render_instruction(high_slots))
        instruction = instruction + _filler(instruction, wanted - _count_tokens(instruction))
        prompt = instruction
    elif arm.control is not None:
        # The R control: the `r0` block, plus a frozen neutral filler whose token count
        # is the tool-block difference between `rH` and `r0`.  A length-only control, and
        # the content change it introduces is reported rather than denied.
        high = _replace(arm, level=arm.control, control=None)
        high_block = _block_names(
            engine_spec, high, qualifier, permutation, pool_order, instruction
        )
        high_tools = _render_block(
            engine_spec, seed, arm.split, _arm_id(high), target, high_block
        )
        system_prompt = system_prompt + _filler(
            system_prompt, _rendered_tokens(high_tools) - _rendered_tokens(tools)
        )

    if arm.knob == _SHAPE:
        # Shape: the targets advanced side by side, stage by stage, four calls at every width.
        reference_calls, reference_observations = _shape_calls(
            engine_spec, scenario, targets, seq_start
        )
    elif arm.knob == _SPREAD:
        # Spread: the four named reads in the listed order, each answered in front of the
        # engine with its part or `none` through the one function the tool server and `verify`
        # answer them with, then B's two stage calls numbered after them (N35).
        answers = tuple(
            (tool, args, _surface.spread_payload(seed, arm.split, position, part))
            for position, ((tool, args), part) in enumerate(
                zip(spread_reads, _spread_parts(code, arm.level), strict=True)
            )
        )
        state = _init_state(scenario, seq_start)
        counts: dict[str, int] = {}
        read_observations: list[str] = []
        for tool, args, _payload in answers:
            state, counts, observation = _surface.apply_planned(
                state, counts, (tool, args), {}, spread=answers
            )
            read_observations.append(observation)
        chain_calls, chain_observations = _chain_calls(
            engine_spec, scenario, qualifier, record, goal, seq_start + len(answers)
        )
        reference_calls = spread_reads + chain_calls
        reference_observations = tuple(read_observations) + chain_observations
    else:
        reference_calls, reference_observations = _chain_calls(
            engine_spec, scenario, qualifier, record, goal, seq_start
        )
    start = _init_state(scenario, seq_start)
    final, _replayed = _replay(scenario, list(reference_calls), seq_start)
    if stated:
        # Both stage calls carry the stated values, after the engine replay that sets the
        # expected records: the engine never sees them, and the observations are B's.
        reference_calls = tuple(
            (name, {**arguments, **stated}) for name, arguments in reference_calls
        )
    if arm.knob in _PLANNED_KNOBS:
        # The reference carries the retries: each planned answer's call, answered the knob's
        # line, and the same call again (N25).  The plan and the word are read off the arm id
        # and the reference's own tools, as `verify` and the tool server read them, so the
        # controls built from this reference meet the same answers.
        plan = _surface.fault_plan(rendered, tuple(name for name, _args in reference_calls))
        reference_calls, reference_observations = _planned_chain(
            scenario, reference_calls, seq_start, plan,
            _surface.fault_kind(rendered) or _UNAVAILABLE_STATUS,
        )
    final_token = _payload_of(reference_observations[-1]) if reference_observations else None

    controls = _negative_controls(
        engine_spec, scenario, arm, qualifier, record, decoy, arm.split, block,
        reference_calls, final_token, stated, targets,
    )
    # The reference and the controls call the tools as the block shows them, which `verify`
    # and the tool server map back to the engine; a control's call to a tool outside the
    # block keeps the engine's name, which the block shows nothing under.
    to_shown = dict(zip(block, shown_block, strict=True))
    reference_calls = tuple((to_shown[name], args) for name, args in reference_calls)
    controls = {
        key: tuple((to_shown.get(name, name), args) for name, args in calls)
        for key, calls in controls.items()
    }

    template_id, _template = _template_of(slots)
    bundle = TaskBundle(
        task_id="",
        arm_id=rendered,
        seed=seed,
        split=arm.split,
        scenario_hash=_scenario_hash(scenario),
        system_prompt=system_prompt,
        prompt=prompt,
        tools=tools,
        seq_start=seq_start,
        template_id=template_id,
        prompt_slots=slots,
        initial_state=_records_value(start),
        expected_final_state=_records_value(final),
        goal=target,
        reference_calls=reference_calls,
        reference_observations=reference_observations,
        negative_controls=controls,
        verifier=VerifierSpec(strictness=arm.strictness),
        pins=_PinRecord(arm_id=rendered, values={}, unmeasured={}),
        engine_hash=_engine_hash(engine_spec),
        generator_hash=_generator_hash(arm.generator_version),
    )

    # G4's gate, through the module-global `verify` so a test can fault-inject it.
    # Without the gate, G4 is a property of a correct generator and not a gate.
    reference_turns = tuple(
        Turn(content="", calls=(call,), finish_reason="tool_calls") for call in reference_calls
    )
    verdict = verify(
        bundle,
        reference_turns,
        ended_with_reply=True,
        turn_limit_hit=False,
        fmt=_REFERENCE_FORMAT,
        spec=engine_spec,
    )
    if verdict.strict_label != _PASSED or not verdict.leaky_pass:
        raise ValueError(
            f"generation refuses {rendered} at seed {seed}: its reference solution "
            f"verifies as {verdict.strict_label!r}, not {_PASSED!r}"
        )

    # The knobs module states the bundle it reads as a `Protocol` of mutable attributes,
    # because this module did not exist when it was written; a frozen dataclass satisfies it
    # structurally and not nominally, so the two calls into the ledger are cast.
    bundle = _replace(bundle, pins=_measure_pins(_cast(_Any, bundle)))
    return _replace(bundle, task_id=_task_id(bundle))


def _rendered_tokens(tools: tuple[dict[str, _Any], ...]) -> int:
    """N5's measurement: the tool block's schemas in slot order, canonically rendered."""
    return _count_tokens(_json.dumps(list(tools), sort_keys=True, separators=(",", ":")))


def generate_contrast(
    arms: tuple[_ArmSpec, ...], seed: int, spec: _EngineSpec | None = None
) -> dict[str, TaskBundle]:
    """One seed under every arm of one knob, refused as a batch (G11).

    Every ledger row is an equality *across* the arms of one knob, so one arm satisfies
    all of them vacuously and no single-arm entry point can refuse on a row at all:
    the contrast is the unit the ledger is defined over, so it is the unit generation
    refuses on.  A batch that violates any row emits nothing -- there is no partial
    output.
    """
    made = {_arm_id(arm): generate(arm, seed, spec) for arm in arms}
    report = _check_pins(_cast(_Any, made))
    if report.refused:
        rows = ", ".join(row for row, _detail in report.violations)
        raise ValueError(
            f"generation refuses the contrast at seed {seed}: the ledger violates {rows} "
            f"-- {report.violations}"
        )
    return made


# ---------------------------------------------------------------------------
# import-time checks on the frozen filler, which no test can reach
# ---------------------------------------------------------------------------


def _check_template_words() -> None:
    """The templates' prose carries no token that is a substring of a read tool's name or
    of a qualifier.

    N7 holds the prompt-to-tool-name overlap *set* equal across a knob's arms, and knob
    R's block loses reads and gains other classes' stage tools as the level rises.  A
    prose word that either of those carries therefore enters or leaves the overlap set
    with the level, and the contrast refuses.  The designation rules in `_block_names`
    are the second line; this is the first, and it is asserted at import because the
    failure it prevents surfaces three modules away as a refused ledger row.

    Spread's template is not checked: the spec's sentence carries pieces of read tools' and
    ledgers' names (`in` is a piece of `invoice`), and N7 cannot move on a spread contrast,
    whose request and block are the same at every level.
    """
    prose = "\n".join((_USER_TEMPLATE, _NUMBER_TEMPLATE, _GOALS_TEMPLATE, _GOAL_LINE))
    for slot in (
        _SLOT_RECORD,
        _SLOT_CLASS,
        _SLOT_NUMBER,
        _SLOT_LADDER,
        _SLOT_GOAL,
        _SLOT_ENTRY,
        _SLOT_GOALS,
    ):
        prose = prose.replace("{" + slot + "}", "\n")
    names = tuple(_SPEC.read_tools) + tuple(_SPEC.qualifiers)
    for piece in _instruction_pieces(prose):
        carried = [name for name in names if piece in name.lower()]
        if carried:
            raise ValueError(
                f"the prompt template's word {piece!r} is a substring of {carried}, so "
                "the prompt's overlap with the tool names would move with knob R's level"
            )


def _check_filler_words() -> None:
    """The design asks the R control's filler for no vocabulary-table token, no qualifier and
    nothing tool-shaped.  Asserted here, because a table version that added one of these
    words would otherwise turn a length-only control into a content change nobody
    declared."""
    table = _json.dumps(_SPEC.table).lower()
    for word in _FILLER_WORDS:
        if word in table or "_" in word:
            raise ValueError(f"the R control filler word {word!r} is not neutral against the table")


_check_template_words()
_check_filler_words()
