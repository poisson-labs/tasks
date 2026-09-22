"""TG-M3, task and verifier generation: `(arm, seed)` to a task bundle, with the
verifier, a reference solution and negative controls generated alongside the task.

The invariants this file is built against are G1-G16, the outcome vocabulary and the
format check in the spec's 2.3, as amended on 2026-09-11 by TG-ADR-35 and TG-ADR-36, on
2026-09-13 by TG-ADR-37 and TG-ADR-38, and on 2026-09-14 by TG-ADR-40 and TG-ADR-41.
The frozen test file is `tests/test_tg_m3_tasks.py`; where the spec's text could not be
used as written, that file's module docstring is authoritative and this file follows it.

Everything here is a pure function of its arguments and the frozen vocabulary table:
no clock, no RNG, no model, no network (G1, G2).  TG-M1's and TG-M2's literals are
reached by import and never re-minted, `d_R` included -- it is read back off TG-M2's own
`ArmSpec.reference_turns` rather than copied as a number (SF9, standing rule 8).

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
TG-ADR-42 recorded and the coverage item the spec's 2.1 owed any future table.  The
three rules below still earn their place -- they hold the overlap set still for the
prose, the slots and the entry code, none of which the table's disjointness reaches --
and the sentences above stand as they were written, because the freedom this build had
and did not have is what they describe.  `tests/test_record_id_fix.py` pins the new
property; the six words v1 carried are named there and in `_drawable_entry_codes`.

* **The block's read tools are the table's first `n` reads, in table order, and the
  block is then permuted by the scenario's one slot draw.**  2.2 says knob D's block is
  "8 orthogonal read tools" and never which eight.  Drawing the subset *and* the
  permutation would parameterise the same arrangement twice, so `structure_space` could
  no longer be the size of the image it claims to count (G16, `test_g16_1` brute-forces
  it).  One draw, one image.  *Escape hatch:* draw the subset instead of the order, and
  `structure_space` changes with it.

* **The slots knob R designates are chosen so that a level change never moves N7's
  overlap set, in both directions.**  2.2 says "the seed designates the slots"; it does
  not say which.  A read tool whose name carries an instruction token must not drop out
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
  the goal, and not otherwise.**  The tests' decision 7 states the top-stage case; the
  same sentence decides knob R, whose block holds stages 1 and 2 alone, so no call the
  model can make overshoots and no control could produce the label.  G7 is carried by
  `collateral_mutation` there, exactly as at stage 8.  *Escape hatch:* `test_g7_2` is
  written about stage 8 and would not move; a build that gives knob R the whole ladder
  would have to restate 2.2's block instead.

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

from poisson_tasks.engine import EngineSpec as _EngineSpec
from poisson_tasks.engine import Scenario as _Scenario
from poisson_tasks.engine import apply as _apply
from poisson_tasks.engine import engine_hash as _engine_hash
from poisson_tasks.engine import init_state as _init_state
from poisson_tasks.engine import mutations as _mutations
from poisson_tasks.engine import replay as _replay
from poisson_tasks.knobs import ArmSpec as _ArmSpec
from poisson_tasks.knobs import PinRecord as _PinRecord
from poisson_tasks.knobs import arm_id as _arm_id
from poisson_tasks.knobs import check_pins as _check_pins
from poisson_tasks.knobs import measure_pins as _measure_pins
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

# 2.2's knob names.  TG-M2's `ArmSpec.__post_init__` is what refuses anything else; these
# are the same two strings its arm ids render.
_DEPTH = "depth"
_DISTRACTOR = "distractor"

# TG-M2's `d_R`, cited and not re-minted: `reference_turns` is `d_R + 1` for every R arm
# (N16), so the number comes back off TG-M2's own constructor.
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

# Domain separators.  Each changes only if its construction changes, which would be a new
# generator version anyway -- the same shape as TG-M1's `engine_hash` separator.
# The spelling is deliberately not the package's: these bytes are hash input, so the
# 2026-09-22 rename to `poisson_tasks` left them alone.  Respelling one moves every id
# it keys.
_TASK_ID_DOMAIN = b"task-generator/task_id/1\n"
_SCENARIO_DOMAIN = b"task-generator/scenario_hash/1\n"
_FINGERPRINT_DOMAIN = b"task-generator/structural_fingerprint/1\n"
_GENERATOR_DOMAIN = b"task-generator/generator_hash/1\n"
_DRAW_KEY = b"task-generator/structure-draw/1"
_TOKEN_KEY_DOMAIN = b"task-generator/token-key/1"
_DECOY_DOMAIN = b"task-generator/decoy-record/1"
_STRUCTURE_DOMAIN = b"task-generator/structure/1"
_ENTRY_DOMAIN = b"task-generator/entry-code/1"

# 2.3's outcome vocabulary.  Closed, in the table's order: the first label that matches
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
# E8's and 2.5 runs the replay check before the verdict, and `api_error` and
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

# The prompt template.  One template for both knobs (2.2 gives knob D "one fixed
# template"), so N6's template-id clause is an equality a contrast can actually fail.
_TEMPLATE_ID = "ledger-chain/v1"

_SLOT_RECORD = "record_id"
_SLOT_ENTRY = "entry_code"
_SLOT_CLASS = "ledger_class"
_SLOT_LADDER = "stage_ladder"
_SLOT_GOAL = "goal_stage"

# The slots G15 masks: an id and an entry code are opaque strings the model copies, and
# neither is structure.  Masking by slot name is what keeps the mask off the prose.
_OPAQUE_SLOTS = (_SLOT_RECORD, _SLOT_ENTRY)
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
_USER_TEMPLATE = (
    "Advance record {" + _SLOT_RECORD + "} of the {" + _SLOT_CLASS + "} ledger.\n"
    "Stage ladder: {" + _SLOT_LADDER + "}.\n"
    "Raise that record through {" + _SLOT_GOAL + "}, and no further.\n"
    "Open with entry code {" + _SLOT_ENTRY + "}; each later stage needs what the stage "
    "before returned."
)

_LADDER_SEPARATOR = " then "

# 2.2's R control filler: a frozen neutral passage appended to the system prompt, whose
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
_RecordsRow = tuple[str, str, int, "str | None"]
_RecordsValue = tuple[_RecordsRow, ...]
_Option = tuple[int, str, dict[str, str], str]


# ---------------------------------------------------------------------------
# 2.3's five types
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
    """2.3's verifier spec.  One field: the target and the goal live on the bundle."""

    strictness: str


@_dataclass(frozen=True)
class Verdict:
    """2.3's verdict.  `format_clause` is the clause that fired, or `None`.

    `mutations` is TG-M1's diff, unchanged and unfiltered: it still reports
    `(class, id, "audit")` triples, because it is diagnostic output and not the predicate
    (TG-ADR-40).
    """

    strict_label: str
    leaky_pass: bool
    label: str
    mutations: tuple[tuple[str, str, str], ...]
    format_clause: int | None


@_dataclass(frozen=True)
class TaskBundle:
    """2.3's bundle, carrying 2.3's fields in 2.3's order and nothing else.

    `initial_state` and `expected_final_state` are **records** values -- a sorted tuple of
    `(class, record_id, stage, token)` rows, with no audit field (PG-16, TG-ADR-40) -- so
    neither moves with the arm's `seq_start` and neither repeats the scenario that
    `scenario_hash` already pins (TG-ADR-37).
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
    """`K_D` and `K_R` as the rule 2.2 states rather than as the literal it happens to
    come to: the target class's stage tools plus an equal number of orthogonal reads.

    Built as a count, the generator could not run on the reduced vocabulary G16's tests
    need; built as the rule, TG-M2's `K_D` is a consequence and not a second freeze.
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
    2.2 pins the *record id* to the task seed and says nothing about which entry code a
    scenario draws, so the generator draws one that cannot enter N7's overlap set.  It
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
    and `disc` (`train`) at 43 of 60, measured, not assumed (TG-ADR-44; the record was
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
    """2.2's functional distractors: the required stage tools of every *other* class.

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


def _prf(domain: bytes, seed: int, split: str) -> bytes:
    """A keyed pseudo-random function of the task seed and the split, and of nothing
    else -- the arm is not an argument, which is what makes N1 true by construction."""
    message = f"{seed}\x1f{split}".encode("ascii")
    return _hashlib.blake2b(domain + b"\x1f" + message, key=_DRAW_KEY, digest_size=32).digest()


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
    """Everything drawn from the task seed alone (2.2's Terms), and nothing from the arm.

    The scenario is a derivation and not a bundle field (TG-ADR-37, TG-ADR-38): `verify`
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
    without anyone remembering to add it -- which is the answer TG-ADR-38 asks TG-M3 to
    state.  The same construction TG-M1 pinned for `engine_hash`.
    """
    body = {name: value for name, value in _canon(bundle).items() if name != "task_id"}
    return _hashlib.sha256(_TASK_ID_DOMAIN + _canonical_bytes(body)).hexdigest()


def _generator_hash(generator_version: str) -> str:
    """N12's generator hash: this module's own source beside the arm's generator version,
    so it moves when either does."""
    source = _pathlib.Path(__file__).resolve().read_bytes()
    return _hashlib.sha256(
        _GENERATOR_DOMAIN + generator_version.encode("utf-8") + b"\x1f" + source
    ).hexdigest()


# ---------------------------------------------------------------------------
# records values - the shape PG-16 decided (TG-ADR-40)
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


def _render_tool(tool: _Any) -> dict[str, _Any]:
    """One tool's schema, as the block carries it.

    Keys are written in one order and every hash over the block is taken with
    `sort_keys`, so neither the rendering nor its digest moves with insertion order.
    """
    names = sorted(tool.parameters)
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": {
            "type": "object",
            "properties": {name: {"type": tool.parameters[name]} for name in names},
            "required": names,
            "additionalProperties": False,
        },
    }


def _instruction_pieces(text: str) -> tuple[str, ...]:
    """The instruction's reference-tokenizer tokens, as the strings they stand for.

    The same decomposition TG-M2's N7 measures; this module reads it to designate the
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
    distractors and the rest reads, with the required tools' slots untouched (N2).
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
    if arm.knob == _DEPTH or arm.level == 0:
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
    """The stage the task asks for: the level for knob D, `d_R` for every R level."""
    return arm.level if arm.knob == _DEPTH else _D_R


def _prompt_slots(
    spec: _EngineSpec, arm: _ArmSpec, record: str, code: str, qualifier: str
) -> tuple[tuple[str, str], ...]:
    """The template's filled slots, in template order.

    N6 pins the slots' token count and never their values.  Every slot but the goal stage
    is equal across a knob's arms by construction, and the goal stage name is one token
    for every stage the table names -- which is what makes N6 an equality a level change
    can pass.
    """
    stage = _goal_stage_index(spec, arm)
    return (
        (_SLOT_RECORD, record),
        (_SLOT_CLASS, qualifier),
        (_SLOT_LADDER, _LADDER_SEPARATOR.join(spec.stage_names)),
        (_SLOT_GOAL, spec.stage_names[stage - 1]),
        (_SLOT_ENTRY, code),
    )


def _render_instruction(slots: tuple[tuple[str, str], ...]) -> str:
    """The user instruction.

    It names the whole stage ladder at every level and designates the goal within it.
    That is forced, not chosen: knob D's block carries every stage tool of the target
    class at every level (N4), so a prompt naming only the goal would put a different
    stage word in N7's overlap set at every level and generation would refuse its own
    contrast.  The target class is named exactly once (2.2's lexical rule).
    """
    return _USER_TEMPLATE.format(**dict(slots))


def _filler(base: str, tokens: int) -> str:
    """2.2's R control filler, at exactly `tokens` reference-tokenizer tokens.

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


def _pair_tokens(name: str, args: _Args, observation: str) -> int:
    """N9's unit, rendered the way TG-M2 measures it: the name bare, the arguments as one
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

    N9 is an aggregate and never a per-pair equality: 2.2's own measurement is that
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
) -> dict[str, tuple[_Call, ...]]:
    """One control per system label a call sequence can produce.

    `passed` is `reference_calls` itself and `verifier_error` is fault-injected, so
    neither is generated.  Format-check clause 1 depends on a family's raw format and is
    exercised through each model's stack at stage 0b (A16), so this generates clauses 2,
    3 and 4 at the call level and not clause 1.
    """
    record_param = _param(spec, "record")
    entry_param = _param(spec, "entry")
    token_param = _param(spec, "token")
    code = scenario.records[(qualifier, record)]
    stage_tools = _stage_tools_of(spec, qualifier)
    goal = _goal_stage_index(spec, arm)

    controls: dict[str, tuple[_Call, ...]] = {}
    controls[_WRONG_STATE] = reference[:-1]
    controls[_TURN_LIMIT] = reference
    # The decoy id in the target class: knob D's block holds no other class's tools, so
    # this is the only mutation of another record any call inside the block can make.
    controls[_COLLATERAL] = reference + (
        (stage_tools[0], {record_param: decoy, entry_param: code}),
    )
    # `overshoot` needs a tool in the block that carries the target past the goal.  At the
    # top stage there is none, and knob R's block holds stages 1 and 2 alone, so there is
    # none there either; G7 is carried by `collateral_mutation` in both cases.
    if goal < len(stage_tools) and stage_tools[goal] in block and final_token is not None:
        controls[_OVERSHOOT] = reference + (
            (stage_tools[goal], {record_param: record, token_param: str(final_token)}),
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
    from the label order (decision 4).  On a table too small to leave a read outside the
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
# 2.3's format check
# ---------------------------------------------------------------------------


def _schema_ok(tool: dict[str, _Any], args: dict[str, _Any]) -> bool:
    """The tool's own JSON schema: exactly its parameters, each one a string."""
    properties = tool["parameters"]["properties"]
    if set(args) != set(properties):
        return False
    return all(isinstance(args[name], str) for name in sorted(properties))


def _format_clauses(
    turns: tuple[Turn, ...], fmt: FormatSpec, block: dict[str, dict[str, _Any]]
) -> set[int]:
    """Every clause that fired, over the whole episode.

    Every clause is collected rather than the first: an episode can break two of them in
    two turns, and one call can break two at once, and the *lowest-numbered* one is what
    `verify` reports (decision 8) -- so a reader comparing two runs of one episode under
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
# 2.3's verifier
# ---------------------------------------------------------------------------


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
    (G10): a bundle whose stored initial state disagrees with its own derivation is a
    defective bundle and not a failed episode, and an episode that neither replied nor hit
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

    calls = [call for turn in turns for call in turn.calls]
    state, _observations = _replay(scenario, calls, bundle.seq_start)
    final = _records_value(state)
    changed = tuple(_mutations(start, state))

    cls, record, goal = bundle.goal
    target = state.records[(cls, record)]
    expected = tuple(bundle.expected_final_state)
    leaky_pass = target.stage >= goal

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
        final, expected, cls, record, goal, target.stage, changed,
        ended_with_reply, turn_limit_hit, clause,
    )
    if strict_label in _ADAPTER_ONLY:  # pragma: no cover - the split is decision 3's
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


def _strict_label(
    final: _RecordsValue,
    expected: _RecordsValue,
    cls: str,
    record: str,
    goal: int,
    stage: int,
    changed: tuple[tuple[str, str, str], ...],
    ended_with_reply: bool,
    turn_limit_hit: bool,
    clause: int | None,
) -> str:
    """The table's labels, with the pass predicate decided first (decision 4).

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
    if stage > goal:
        return _OVERSHOOT
    if stage < goal or _row(final, cls, record) != _row(expected, cls, record):
        return _WRONG_STATE
    if any((row_cls, row_record) != (cls, record) for row_cls, row_record, _field in changed):
        return _COLLATERAL
    # Unreachable: the target matching expected with nothing else mutated *is* the
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
    opaque, never to the rendered string, so no pattern can reach the prose.
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
        "tools": _canon(bundle.tools),
        "target_class": bundle.goal[0],
        "goal_stage": bundle.goal[2],
        "seeded": seeded,
    }
    return _hashlib.sha256(_FINGERPRINT_DOMAIN + _canonical_bytes(body)).hexdigest()


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
    smaller `k` overstates the chance a run repeats a structure.
    """
    engine_spec = _resolve(spec)
    space = len(engine_spec.qualifiers) * _math.factorial(_block_size(engine_spec))
    if arm.knob == _DISTRACTOR and arm.level > 0:
        pool = len(_distractor_pool(engine_spec, engine_spec.qualifiers[0]))
        for position in range(arm.level):
            space *= pool - position
    return space


# ---------------------------------------------------------------------------
# 2.3's generator
# ---------------------------------------------------------------------------


def generate(arm: _ArmSpec, seed: int, spec: _EngineSpec | None = None) -> TaskBundle:
    """`(arm, seed)` to a task bundle, with the verifier, a reference solution and the
    negative controls generated alongside the task.

    Byte-identical across runs, processes and platforms, with no model call and no network
    call (G1, G2).  Both splits generate: "v0 emits `eval` only" is the pre-registration's
    choice among what the generator offers, and G12's own first clause is a statement
    about both splits that is untestable if one of them refuses.
    """
    engine_spec = _resolve(spec)
    scenario = scenario_for(seed, arm.split, engine_spec)
    qualifier, permutation, pool_order = _drawn_parts(seed, arm.split, engine_spec)

    record = encode_record_id(seed, arm.split)
    decoy = encode_record_id(_decoy_seed(seed, arm.split), arm.split)
    code = scenario.records[(qualifier, record)]
    slots = _prompt_slots(engine_spec, arm, record, code, qualifier)
    instruction = _render_instruction(slots)
    block = _block_names(engine_spec, arm, qualifier, permutation, pool_order, instruction)
    tools = tuple(_render_tool(_tool_defs(engine_spec)[name]) for name in block)

    goal = _goal_stage_index(engine_spec, arm)
    seq_start = 1
    system_prompt = _SYSTEM_PROMPT
    prompt: str | tuple[dict[str, _Any], ...] = instruction

    if arm.control is not None and arm.knob == _DEPTH:
        pairs = arm.control - arm.level
        seq_start = pairs + 1
        reads = tuple(name for name in block if name in engine_spec.read_tools)
        _high_calls, _high_observations = _chain_calls(
            engine_spec, scenario, qualifier, record, arm.control, 1
        )
        target = sum(
            _pair_tokens(name, args, observation)
            for (name, args), observation in zip(
                _high_calls[arm.level :], _high_observations[arm.level :], strict=True
            )
        )
        prompt = _seeded_messages(instruction, _seeded_block(engine_spec, reads, pairs, target))
    elif arm.control is not None:
        # 2.2's R control: the `r0` block, plus a frozen neutral filler whose token count
        # is the tool-block difference between `rH` and `r0`.  A length-only control, and
        # the content change it introduces is reported rather than denied.
        high = _replace(arm, level=arm.control, control=None)
        high_block = _block_names(
            engine_spec, high, qualifier, permutation, pool_order, instruction
        )
        high_tools = tuple(_render_tool(_tool_defs(engine_spec)[name]) for name in high_block)
        system_prompt = system_prompt + _filler(
            system_prompt, _rendered_tokens(high_tools) - _rendered_tokens(tools)
        )

    depth = goal
    reference_calls, reference_observations = _chain_calls(
        engine_spec, scenario, qualifier, record, depth, seq_start
    )
    start = _init_state(scenario, seq_start)
    final, _replayed = _replay(scenario, list(reference_calls), seq_start)
    final_token = _payload_of(reference_observations[-1]) if reference_observations else None

    controls = _negative_controls(
        engine_spec, scenario, arm, qualifier, record, decoy, arm.split, block,
        reference_calls, final_token,
    )

    rendered = _arm_id(arm)
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
        template_id=_TEMPLATE_ID,
        prompt_slots=slots,
        initial_state=_records_value(start),
        expected_final_state=_records_value(final),
        goal=(qualifier, record, goal),
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
            f"verifies as {verdict.strict_label!r}, not {_PASSED!r} (G4)"
        )

    # TG-M2 states the bundle it reads as a `Protocol` of mutable attributes, because
    # TG-M3 did not exist when it was written; a frozen dataclass satisfies it
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
    all of them vacuously and nothing in 2.3's Interface list can refuse on a row at all:
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
    """The template's prose carries no token that is a substring of a read tool's name or
    of a qualifier.

    N7 holds the prompt-to-tool-name overlap *set* equal across a knob's arms, and knob
    R's block loses reads and gains other classes' stage tools as the level rises.  A
    prose word that either of those carries therefore enters or leaves the overlap set
    with the level, and the contrast refuses.  The designation rules in `_block_names`
    are the second line; this is the first, and it is asserted at import because the
    failure it prevents surfaces three modules away as a refused ledger row.
    """
    prose = _USER_TEMPLATE
    for slot in (_SLOT_RECORD, _SLOT_CLASS, _SLOT_LADDER, _SLOT_GOAL, _SLOT_ENTRY):
        prose = prose.replace("{" + slot + "}", "\n")
    names = tuple(_SPEC.read_tools) + tuple(_SPEC.qualifiers)
    for piece in _instruction_pieces(prose):
        carried = [name for name in names if piece in name.lower()]
        if carried:
            raise ValueError(
                f"the prompt template's word {piece!r} is a substring of {carried}, so "
                "N7's overlap set would move with knob R's level"
            )


def _check_filler_words() -> None:
    """2.2 asks the R control's filler for no vocabulary-table token, no qualifier and
    nothing tool-shaped.  Asserted here, because a table version that added one of these
    words would otherwise turn a length-only control into a content change nobody
    declared."""
    table = _json.dumps(_SPEC.table).lower()
    for word in _FILLER_WORDS:
        if word in table or "_" in word:
            raise ValueError(f"the R control filler word {word!r} is not neutral against the table")


_check_template_words()
_check_filler_words()
