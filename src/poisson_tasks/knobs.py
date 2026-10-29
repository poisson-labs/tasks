"""The knobs, control arms and the pin ledger: a declared ledger, and the two measurements
a bundle supports.

The invariants this file is built against are N1-N18, tested in `tests/test_tg_m2_knobs.py`;
where a requirement could not be used as written, that file's module docstring is
authoritative.  The seven knobs added beside depth and the distractor dial -- similarity,
faults, history, block, arguments, shape and spread -- and their ledger rows N19-N35 are
tested in `tests/test_k1_knobs.py` and `tests/test_k1_ledger.py`.  Every knob's name, levels,
arm id formats, turn budget and rows are declared here at once, and so are the literals each
knob's design rests on, because this file's bytes are part of the generator hash.

The public surface is the interface's names plus the three type names its signatures use,
and nothing else.  "Both knobs' transforms" are reached through `ArmSpec`'s derived values
and through `check_pins`, never as symbols of their own.

Shapes the requirements name but do not define, decided here:

* **`ArmSpec.control` is the reference level, not a flag.**  It holds the level the
  control stands in for -- `8` in `depth:d1+h8` and in `distractor:r0+len(r8)@k16` -- and
  `None` on a plain arm.  The arm id formats forced it: each control id renders exactly
  that one extra number.
* **Validation lives in `ArmSpec.__post_init__`.**  N15's own words are that `d3+h3` and
  `d8+h1` are "construction errors rather than arms that generate and then fail a pin", so
  an arm spec that cannot be rendered cannot be built.  The knob and the control relation
  are checked; **the level is not checked against `levels(knob)`**, because those are the
  *candidate* levels, and the choice among them belongs to a study's pre-registration, not
  here.  The escape hatch, if a later module wants an arm spec it
  validates itself, is to move both checks into `arm_id` -- which every test that exercises
  them already calls.
* **A refusal is a `PinReport` that says so.**  The interface is
  `check_pins(...) -> PinReport | refusal`; the ledger's job is to report and the *On
  violation* column says **generation** refuses, so `refused` is a field and not an
  exception.  `check_pins` raises `ValueError` only for a caller error -- arms from two
  knobs, or fewer than two arms -- because a caller error is not a pin violation and must
  not come back as one.
* **`PinRow` carries `stage` and `applies_to`.**  The ledger's *On violation* column states
  where a row is enforced in prose, and a caller cannot act on prose.  `applies_to` names
  the knobs a row constrains: N4 is the knobs' whose block does not move with the level, N5
  is knob R's, N9 is knob D's because only knob D's control seeds history in `(H - dL)`
  pairs, and each of N19 to N35 is its own knob's.
* **A row can report and refuse at once.**  N29 and N33 carry the action `refuse`, which is
  what a caller acting on the row needs to know, and the block's growth they also measure
  goes in the report's `reported` list beside any refusal.  N7 is reported, and never
  refused, on a shape contrast, where the request and the block name more ledgers as the
  width grows.
* **The new rows are measured on every bundle, from the fields the ledger already read.**
  The right tools are the tools the reference solution calls, in the order it first calls
  them; the target ledger's number is the four-digit number in the first one's name; a
  planned failure is an `unavailable` answer among the reference observations.  A row that
  compares a control with the level it stands in for does so only when that arm is in the
  contrast, as N9 does.
* **The arm id is parsed back in `check_pins`.**  A bundle carries an `arm_id` string and
  no arm spec, so the knob CP1 refuses on and the `(dL, H)` pair N9 compares are read off
  the key.  `_render_arm_id` is the one renderer, used by `arm_id` and by N9's lookup of
  the high arm, so the two can never disagree.

* **The three transport-fault knobs of 0.3.0** (`timeouts`, `ratelimits`, `landed`) are
  knobs beside the nine, not levels of `faults` and not a kind field on the arm: a level is a
  count and cannot say which kind, and a seventh field would reach every reader of
  `(knob, level)`.  Their letters are `o` (`t` is history's), `r` (the knob's name is always in
  the id, so `ratelimits:r2` and `distractor:r2@k16` cannot be confused) and `l`.  `landed`
  joins the knobs with no control arm, for a reason of its own: one fault pair is 33 reference
  tokens and the shortest seeded read pair 51, so no control reaches its length within the
  ledger's two tokens.  The status word each kind's planned answers carry is `_FAULT_WORDS`',
  which N25 and N26 read (`surface.fault_kind` gives it per arm), and N24 to N26 apply to the
  new knobs as the 0.3.0 faults design says: N24 and N25 to all three, N26 to the two with a
  control.  Tested in `tests/test_f2_arms.py` and `tests/test_f2_lines_and_plan.py`.

`measure_pins` is a read: it never writes to the bundle it is handed (P3).  Every entry
point is pure -- no clock, no RNG, no IO beyond the frozen vocabulary table the engine
already loads, and no network (SF5).  `L_obs` and the token band are the engine's
literals, cited here and never re-minted (SF6).
"""

from __future__ import annotations

import hashlib as _hashlib
import json as _json
import re as _re
from collections.abc import Mapping as _Mapping
from dataclasses import dataclass as _dataclass
from typing import Any as _Any
from typing import Protocol as _Protocol

from poisson_tasks.engine import EngineSpec as _EngineSpec
from poisson_tasks.tokenizer import count_tokens as _count_tokens
from poisson_tasks.tokenizer import reference_encoding as _reference_encoding

__all__ = [
    "ArmSpec",
    "PinRow",
    "PinRecord",
    "PinReport",
    "arm_id",
    "levels",
    "pin_ledger",
    "measure_pins",
    "check_pins",
]

# The engine's frozen literals, cited and not re-minted (SF6).  `L_obs` and the token band are
# properties of the vocabulary table; a second copy here would be a number read back and
# compared with itself.
_SPEC = _EngineSpec.load()
_L_OBS = _SPEC.L_obs
_BAND_LO, _BAND_HI = _SPEC.table["token_band"]

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
_KNOBS = (
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
    _LANDED,
)

# Candidate levels, not the pilot defaults: the pilot picks {1, 3, 8} for depth, and that
# choice lives in its pre-registration.  The seven newer knobs' candidates are the levels a
# calibration card measures.
_DEPTH_LEVELS = (1, 2, 3, 5, 8)
_DISTRACTOR_LEVELS = (0, 2, 4, 8, 14)
_LEVELS = {
    _DEPTH: _DEPTH_LEVELS,
    _DISTRACTOR: _DISTRACTOR_LEVELS,
    _SIMILARITY: (0, 1, 2, 3),
    _FAULTS: (0, 1, 2, 4),
    _HISTORY: (0, 300, 600, 1200, 2400),
    _BLOCK: (8, 16, 32, 64),
    _ARGUMENTS: (2, 4, 6, 8),
    _SHAPE: (1, 2, 4),
    _SPREAD: (1, 2, 4),
    _TIMEOUTS: (0, 1, 2, 4),
    _RATELIMITS: (0, 1, 2, 4),
    _LANDED: (0, 1),
}

# The fixed block sizes, and knob R's fixed chain depth.
_K_D = 16
_K_R = 16
_D_R = 2

# The base task the newer knobs measure departures from: two chained stage calls in a
# sixteen-tool block that holds no stage above the goal.
_D_B = 2
_K_B = 16

# The letter each newer knob's arm id writes its level with, and the knobs with no control
# arm: similarity and spread hold the prompt's length equal across their levels, and length
# is history's own factor.
_LETTERS = {
    _SIMILARITY: "s",
    _FAULTS: "f",
    _HISTORY: "t",
    _BLOCK: "k",
    _ARGUMENTS: "a",
    _SHAPE: "w",
    _SPREAD: "p",
    _TIMEOUTS: "o",
    _RATELIMITS: "r",
    _LANDED: "l",
}
_NO_CONTROL = (_SIMILARITY, _HISTORY, _SPREAD, _LANDED)
# Why `landed` has no control: the lengths were measured on the faults design (one fault pair
# against the shortest seeded read pair), and the landed line adds no call to make up for it.
_FAULT_PAIR_TOKENS = 33
_SHORTEST_READ_PAIR_TOKENS = 51

# Similarity: a ledger's number is four digits, and a block holds the two stage tools of six
# other ledgers.  The level is how many digits each of those shares in place with the
# target's, so the highest is one digit apart.
_NUMBER_WIDTH = 4
_LOOKALIKE_LEDGERS = 6
_LOOKALIKES = _LOOKALIKE_LEDGERS * _D_B
_MAX_SIMILARITY = _NUMBER_WIDTH - 1

# Block: the right tools and six reads fill the first eight slots at every level, and the
# most a block can offer is those two tools and every read name the table can make, its
# own reads among them: 258 on the table that ships.
_BLOCK_HEAD = 8
_MAX_BLOCK = _D_B + len(_SPEC.table["read_verbs"]) * len(_SPEC.table["facets"])

# Arguments: a stage tool lists eight parameters, two of them the engine's own.
_ENGINE_ARGUMENTS = 2
_MAX_ARGUMENTS = 8
# The six parameters each stage tool lists beside the engine's two on an arguments arm, in
# the order the levels state them: a4 states the first two, a6 the first four, a8 all six.
# Opaque `*_code` names whose words no tool name carries (N7).
_ARGUMENT_CODES = ("lot_code", "batch_code", "bin_code", "crate_code", "dock_code", "bay_code")

# Shape: four stage calls at every width, side by side in equal rows.
_SHAPE_CALLS = 4
_SHAPE_WIDTHS = (1, 2, 4)

# Spread: four reads are named at every level, and the level is how many carry a part.
_SPREAD_READS = 4

# The slot of the user prompt that is the knob itself, where a knob has one: N6 leaves it
# out on that knob's arms, as the goal stage is depth's.
_OWN_SLOT = {_ARGUMENTS: "stated_values", _SHAPE: "goal_lines"}

# What the knobs' designs answer in front of the engine, and the engine's own word for a
# call that worked.
_OK = "ok"
_UNAVAILABLE = "unavailable"
# The status words the two newer kinds of planned answer carry, and the rate-limited line's
# hint, which the table's fill follows to the payload's width.  Each kind is one word: a
# timeout says only that whether the call went through is not known, and a rate limit that
# nothing changed and when to make the call again.
_TIMEOUT = "timeout"
_RATE_LIMITED = "rate_limited"
_RETRY_AFTER = "retry-after=1s"
# The word each planned-fault knob's answers carry: `landed` answers the timeout line, since
# the call went through and the model cannot tell it from one that went nowhere.
_FAULT_WORDS = {
    _FAULTS: _UNAVAILABLE,
    _TIMEOUTS: _TIMEOUT,
    _RATELIMITS: _RATE_LIMITED,
    _LANDED: _TIMEOUT,
}
_FAULT_KNOBS = tuple(_FAULT_WORDS)
_NO_PART = "none"
_PART_END = "."

# N9's declared band, in reference-tokenizer tokens, over the aggregate.  Minted with
# the tests, at a measured residual of 0 over 256 blocks of seven pairs across two disjoint
# scenarios; the same two-token margin, and the same empirical footing, as the engine's
# observation band.  It is an aggregate and explicitly not a per-pair equality: 51.4% of
# chain calls are cheaper on arguments than any read call and 3.0% of chain pairs fall
# below the read pair floor, so a per-pair equality could never pass.
_N9_BAND = 2

_REFUSE = "refuse"
_REPORT = "report"
_ENGINE_TEST = "engine_test"
_STOP_RUN = "stop_run"
_REFUSE_START = "refuse_start"
_VOID_CONTRAST = "void_contrast"

_GENERATION = "generation"
_ENGINE = "engine"
_ADAPTER = "adapter"
_ANALYSIS = "analysis"

_EVERY = _KNOBS

_DEPTH_ID = _re.compile(r"^depth:d(\d+)(?:\+h(\d+))?$")
_DISTRACTOR_ID = _re.compile(r"^distractor:r(\d+)(?:\+len\(r(\d+)\))?@k(\d+)$")
_LETTER_IDS = {
    knob: _re.compile(rf"^{knob}:{letter}(\d+)(?:\+len\({letter}(\d+)\))?$")
    for knob, letter in _LETTERS.items()
}
_LEDGER_NUMBER = _re.compile(rf"(?<!\d)\d{{{_NUMBER_WIDTH}}}(?!\d)")


class _Verifier(_Protocol):
    """`tasks.VerifierSpec`, reduced to the one field N11 reads."""

    strictness: str


class _Bundle(_Protocol):
    """The bundle fields the ledger reads.

    `tasks.py` owns `TaskBundle` and imports this module, so this states the shape rather
    than naming the type.  Without `template_id`, `prompt_slots` and
    `reference_observations`, N6 and N9 have no measurement.
    """

    arm_id: str
    scenario_hash: str
    system_prompt: str
    prompt: object
    tools: tuple[_Any, ...]
    reference_calls: tuple[_Any, ...]
    reference_observations: tuple[_Any, ...]
    verifier: _Verifier
    engine_hash: str
    generator_hash: str
    template_id: str
    prompt_slots: tuple[_Any, ...]


@_dataclass(frozen=True)
class ArmSpec:
    """An arm: `(knob, level, control, strictness, split, generator version)`.

    Six fields and no seventh: `S` is a run's configuration axis and `seq_start` is an
    argument to `init_state`, so neither belongs here.
    """

    knob: str
    level: int
    control: int | None
    strictness: str
    split: str
    generator_version: str

    def __post_init__(self) -> None:
        if self.knob not in _KNOBS:
            raise ValueError(f"unknown knob {self.knob!r}: the knobs are {', '.join(_KNOBS)}")
        refusal = _unbuildable(self.knob, self.level)
        if refusal is not None:
            raise ValueError(refusal)
        if self.control is None:
            return
        if self.knob == _LANDED:
            raise ValueError(
                f"landed has no control arm: one fault pair is {_FAULT_PAIR_TOKENS} reference "
                f"tokens and the shortest seeded read pair {_SHORTEST_READ_PAIR_TOKENS}, so no "
                f"seeded history reaches the length of its one planned answer within the "
                f"ledger's {_N9_BAND} tokens, and landed level {self.level} cannot stand in "
                f"for level {self.control}"
            )
        if self.knob in _NO_CONTROL:
            raise ValueError(
                f"{self.knob} has no control arm: its levels differ in nothing a control "
                f"could hold equal, so {self.knob} level {self.level} cannot stand in for "
                f"level {self.control}"
            )
        if self.control <= self.level:
            raise ValueError(
                f"a control stands in for a higher level: {self.knob} level {self.level} "
                f"cannot stand in for level {self.control}"
            )
        refusal = _unbuildable(self.knob, self.control)
        if refusal is not None:
            raise ValueError(f"a control stands in for a level that can be built: {refusal}")

    @property
    def reference_turns(self) -> int:
        """N16's minimum: one call per turn, plus the reply turn.

        Depth level `d` needs `d + 1`; every R level needs `d_R + 1`.  The depth control
        follows its own `dL` and never the level it stands in for, because seeded history
        uses no turns.  Similarity, history, block and arguments need the base task's two
        stage calls; faults, timeouts and ratelimits one more call per planned answer; shape
        four stage calls at every width; spread its four reads and the two stage calls;
        landed the one call that lands and the reply.  A control follows its own level here
        too.
        """
        if self.knob == _DEPTH:
            return self.level + 1
        if self.knob == _DISTRACTOR:
            return _D_R + 1
        if self.knob in (_FAULTS, _TIMEOUTS, _RATELIMITS):
            return _D_B + self.level + 1
        if self.knob == _SHAPE:
            return _SHAPE_CALLS + 1
        if self.knob == _SPREAD:
            return _SPREAD_READS + _D_B + 1
        return _D_B + 1

    def max_turns(self, slack: int) -> int:
        """N16's budget: the needed turns plus one slack constant `S`.

        `S` is a run's configuration axis and not one of the six fields, so it is an argument here;
        A5 writes `max_turns(arm)` as though it were nullary.
        """
        return self.reference_turns + slack


@_dataclass(frozen=True)
class PinRow:
    """One ledger row.

    `stage` is where the row is enforced and `on_violation` is what happens when it
    fails; the ledger's table states both in one prose column, and a caller cannot act on
    prose.  `applies_to` is the knobs the row constrains.
    """

    row_id: str
    held: str
    measured: str
    tolerance: str
    on_violation: str
    stage: str
    applies_to: tuple[str, ...]


@_dataclass(frozen=True)
class PinRecord:
    """One bundle's measurements.

    `values` maps a row id to its measured value; `unmeasured` maps a row id to the reason
    it cannot be measured from a bundle at generation time.  Every ledger row appears in
    exactly one of the two, so a row nobody checks is impossible to write.
    """

    arm_id: str
    values: dict[str, _Any]
    unmeasured: dict[str, str]


@_dataclass(frozen=True)
class PinReport:
    """The artefact a pre-registration files.

    `violations` and `reported` are `(row_id, detail)` pairs in ledger order.  `refused`
    is true when any row was violated.  A reported row is not a violation: N5 only ever
    reports, N7 reports on a shape contrast, and N29 and N33 report the block's growth
    beside whatever they refuse.  Collapsing the actions to a boolean is exactly where
    that distinction gets lost, which is why the rows keep their own.
    """

    knob: str
    refused: bool
    violations: tuple[tuple[str, str], ...]
    reported: tuple[tuple[str, str], ...]
    records: dict[str, PinRecord]


@_dataclass(frozen=True)
class _ParsedArm:
    """What an arm id renders, read back: the knob, the level and the reference level."""

    knob: str
    level: int
    control: int | None


def _unbuildable(knob: str, level: int) -> str | None:
    """Why the generator cannot build `level` of a newer knob, in one line, or `None`.

    Not a check against `levels(knob)`: `history:t12800` is a level no card measures and
    the generator can still make.  These are the levels each design has no task for.  Depth
    and the distractor dial keep the bounds their callers always applied.
    """
    if knob == _SIMILARITY and not 0 <= level <= _MAX_SIMILARITY:
        return (
            f"similarity level {level} cannot be built: the level is how many of a ledger "
            f"number's {_NUMBER_WIDTH} digits a lookalike shares with the target's, from 0 "
            f"to {_MAX_SIMILARITY}"
        )
    if knob in (_FAULTS, _HISTORY, _TIMEOUTS, _RATELIMITS, _LANDED) and level < 0:
        counted = {
            _FAULTS: "failed calls",
            _HISTORY: "tokens of earlier tool work",
            _TIMEOUTS: "calls that time out",
            _RATELIMITS: "calls that are rate limited",
            _LANDED: "writes that land and answer a timeout",
        }[knob]
        return f"{knob} level {level} cannot be built: the level counts {counted}, from 0 up"
    if knob == _LANDED and level > 1:
        return (
            f"landed level {level} cannot be built: the level is whether the write lands and "
            "answers a timeout, 0 or 1"
        )
    if knob == _BLOCK and level > _MAX_BLOCK:
        return (
            f"block level {level} cannot be built: a block offers at most {_MAX_BLOCK} tools, "
            "the two the task needs and every read name the table can make"
        )
    if knob == _BLOCK and level < _BLOCK_HEAD:
        return (
            f"block level {level} cannot be built: the level is how many tools are offered, "
            f"and the right tools and six reads fill the first {_BLOCK_HEAD}"
        )
    if knob == _ARGUMENTS and not _ENGINE_ARGUMENTS <= level <= _MAX_ARGUMENTS:
        return (
            f"arguments level {level} cannot be built: the level is how many values a stage "
            f"call carries, from {_ENGINE_ARGUMENTS} to {_MAX_ARGUMENTS}"
        )
    if knob == _SHAPE and level not in _SHAPE_WIDTHS:
        widths = ", ".join(str(width) for width in _SHAPE_WIDTHS[:-1])
        return (
            f"shape level {level} cannot be built: the level is how many records "
            f"{_SHAPE_CALLS} stage calls advance side by side, {widths} or {_SHAPE_WIDTHS[-1]}"
        )
    if knob == _SPREAD and not 1 <= level <= _SPREAD_READS:
        return (
            f"spread level {level} cannot be built: the level is how many of "
            f"{_SPREAD_READS} named reads answer with a part, from 1 to {_SPREAD_READS}"
        )
    return None


def _split_evenly(total: int, shares: int) -> tuple[int, ...]:
    """`total` over `shares` as evenly as it goes, the earlier shares taking the extra.

    The faults knob's plan: the level's failures over the tools on the reference path, so
    with two tools the first stage takes the odd one.
    """
    if shares <= 0:
        return ()
    each, extra = divmod(total, shares)
    return tuple(each + (1 if index < extra else 0) for index in range(shares))


def _render_arm_id(knob: str, level: int, control: int | None) -> str:
    """Every arm id format, and the only place any of them is written."""
    if knob == _DEPTH:
        return f"depth:d{level}" if control is None else f"depth:d{level}+h{control}"
    if knob == _DISTRACTOR:
        if control is None:
            return f"distractor:r{level}@k{_K_R}"
        return f"distractor:r{level}+len(r{control})@k{_K_R}"
    letter = _LETTERS[knob]
    if control is None:
        return f"{knob}:{letter}{level}"
    return f"{knob}:{letter}{level}+len({letter}{control})"


def _parse_arm_id(rendered: str) -> _ParsedArm:
    """The inverse of `_render_arm_id`.

    A bundle carries an arm id and no arm spec, so `check_pins` reads the knob and the
    `(dL, H)` pair off the key.  The `@k` field is parsed and not enforced: the block is
    fixed at 16 and the renderer is the only thing that writes it.
    """
    depth = _DEPTH_ID.match(rendered)
    if depth is not None:
        high = depth.group(2)
        return _ParsedArm(_DEPTH, int(depth.group(1)), None if high is None else int(high))
    distractor = _DISTRACTOR_ID.match(rendered)
    if distractor is not None:
        high = distractor.group(2)
        return _ParsedArm(
            _DISTRACTOR, int(distractor.group(1)), None if high is None else int(high)
        )
    for knob, pattern in _LETTER_IDS.items():
        lettered = pattern.match(rendered)
        if lettered is not None:
            high = lettered.group(2)
            return _ParsedArm(knob, int(lettered.group(1)), None if high is None else int(high))
    raise ValueError(
        f"{rendered!r} is not an arm id: an arm id is a knob, a colon and a level, such as "
        "depth:d3, distractor:r8@k16, similarity:s3, faults:f2, history:t600, block:k32, "
        "arguments:a6, shape:w2 or spread:p4; a control arm adds the level it stands in for, "
        "as in depth:d1+h8 or faults:f0+len(f4)"
    )


def arm_id(spec: ArmSpec) -> str:
    """The canonical id of an arm.

    Canonical means one id per `(knob, level, control)`.  Strictness, split and generator
    version are pinned by N11, G12 and N12 and do not enter the id: an id that rendered
    all six fields would silently break `diff`'s cell matching.
    """
    return _render_arm_id(spec.knob, spec.level, spec.control)


def levels(knob: str) -> tuple[int, ...]:
    """The knob's candidate levels, never the pilot's chosen subset."""
    if knob not in _LEVELS:
        raise ValueError(f"unknown knob {knob!r}: the knobs are {', '.join(_KNOBS)}")
    return _LEVELS[knob]


def pin_ledger(knob: str) -> list[PinRow]:
    """The thirty rows, in the ledger's order: N1 to N13, then N19 to N35.

    The same ledger is used for every knob, so the row set does not vary with the knob;
    what varies is `applies_to`, which `check_pins` reads to decide whether a row is
    evaluated for this contrast.
    """
    if knob not in _LEVELS:
        raise ValueError(f"unknown knob {knob!r}: the knobs are {', '.join(_KNOBS)}")
    return [
        PinRow(
            row_id="N1",
            held="Scenario (every seed-drawn field)",
            measured="`scenario_hash` of the same seed generated under every arm of the knob",
            tolerance="equal",
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=_EVERY,
        ),
        PinRow(
            row_id="N2",
            held="Required-tool slot positions",
            measured=(
                "slot indices per seed, across arms: the name and the index of every tool "
                "the reference solution calls, compared on the tools two arms share"
            ),
            tolerance="equal",
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=_EVERY,
        ),
        PinRow(
            row_id="N3",
            held="System prompt",
            measured=(
                "sha256 across arms.  The only permitted difference is the filler of a "
                "distractor or block control, which is appended at the end, so it is a "
                "suffix of a plain arm's"
            ),
            tolerance="equal",
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=_EVERY,
        ),
        PinRow(
            row_id="N4",
            held="Tool block (knob D)",
            measured="sha256 of the rendered schemas in slot order, across levels",
            tolerance=f"equal; the block is K_D = {_K_D} tools, identical at every level",
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=(_DEPTH, _FAULTS, _HISTORY, _ARGUMENTS, _SPREAD),
        ),
        PinRow(
            row_id="N5",
            held="Tool-block token count (knob R)",
            measured="reference tokenizer, per arm",
            tolerance=(
                "declared band, fixed in the pre-registration; the difference is reported "
                "and never refused, because knob R's block must change by definition"
            ),
            on_violation=_REPORT,
            stage=_GENERATION,
            applies_to=(_DISTRACTOR,),
        ),
        PinRow(
            row_id="N6",
            held="User prompt",
            measured=(
                "template id equal; token count of the variable slots under the reference "
                "tokenizer, both read from the bundle's `template_id` and `prompt_slots`"
            ),
            tolerance="equal; the slot values are free and the goal stage name is the knob",
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=_EVERY,
        ),
        PinRow(
            row_id="N7",
            held="Prompt-to-tool-name lexical overlap",
            measured=(
                "the set of user-instruction tokens that occur in any tool name, across "
                "arms.  The user instruction only: a D control's seeded history names "
                "tools it did not choose"
            ),
            tolerance=(
                "equal; on the shape knob the difference is reported and not refused, "
                "because a wider request and its block name more ledgers"
            ),
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=_EVERY,
        ),
        PinRow(
            row_id="N8",
            held="Observation size",
            measured=(
                "the engine's observation size, in bytes and reference-tokenizer tokens, "
                "over the bundle's `reference_observations`"
            ),
            tolerance=(
                f"L_obs == {_L_OBS} bytes exact; tokens in [{_BAND_LO}, {_BAND_HI}].  A "
                "per-arm property: d1 and d8 carry different numbers of observations, so "
                "a cross-arm equality would refuse a clean contrast"
            ),
            on_violation=_ENGINE_TEST,
            stage=_ENGINE,
            applies_to=_EVERY,
        ),
        PinRow(
            row_id="N9",
            held="Seeded history (control arms)",
            measured=(
                "reference-tokenizer tokens of the seeded pairs vs the expected (H - dL) "
                "stage pairs, which are the bundle's `reference_calls` paired with its "
                "`reference_observations`"
            ),
            tolerance=(
                f"declared band of +/- {_N9_BAND} tokens on the **aggregate** over the "
                "(H - dL) pairs, at a measured residual of 0.  Never a per-pair equality: "
                "that is unsatisfiable against this table"
            ),
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=(_DEPTH,),
        ),
        PinRow(
            row_id="N10",
            held=(
                "The serving pin: model id and revision (N18, the exact commit); vLLM version and "
                "serve flags (parser, reasoning parser, quantization, --max-model-len, "
                "--language-model-only); thinking mode; decoding settings; GPU type.  Also "
                "the harness id and version, endpoint type, slack S, horizon H, token "
                "limits and runtime type"
            ),
            measured=(
                "cfg (single-valued axes, one sweep file per model), the arm spec, and the "
                "serving-pin hash in every episode's `meta`"
            ),
            tolerance="equal across all of a model's runs",
            on_violation=_STOP_RUN,
            stage=_ADAPTER,
            applies_to=_EVERY,
        ),
        PinRow(
            row_id="N11",
            held="Verifier strictness",
            measured="arm spec, carried on the bundle's verifier",
            tolerance="equal",
            on_violation=_REFUSE_START,
            stage=_ADAPTER,
            applies_to=_EVERY,
        ),
        PinRow(
            row_id="N12",
            held="Engine, vocabulary and generator hashes",
            measured=(
                "recorded per task.  The vocabulary is part of `engine_hash`, so two bundle "
                "fields carry three hashes"
            ),
            tolerance="equal",
            on_violation=_REFUSE_START,
            stage=_ADAPTER,
            applies_to=_EVERY,
        ),
        PinRow(
            row_id="N13",
            held="Realised first-request input tokens, per model",
            measured="server-reported usage from the trace, per episode",
            tolerance="pre-registered band",
            on_violation=_VOID_CONTRAST,
            stage=_ANALYSIS,
            applies_to=_EVERY,
        ),
        PinRow(
            row_id="N19",
            held="Lookalike count",
            measured="lookalike tools in the block",
            tolerance=f"exactly {_LOOKALIKES} at every level",
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=(_SIMILARITY,),
        ),
        PinRow(
            row_id="N20",
            held="Block token count (similarity)",
            measured="reference tokens of the rendered block",
            tolerance="equal across levels",
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=(_SIMILARITY,),
        ),
        PinRow(
            row_id="N21",
            held="Lookalike distance",
            measured=(
                "digits each lookalike ledger's number shares in place with the target ledger's"
            ),
            tolerance=(
                f"exactly the level; the {_LOOKALIKE_LEDGERS + 1} numbers distinct, none "
                "starting with 0"
            ),
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=(_SIMILARITY,),
        ),
        PinRow(
            row_id="N22",
            held="The right tools",
            measured=(
                "the two target tools' rendered schemas: display name, description, parameters"
            ),
            tolerance="equal across levels",
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=(_SIMILARITY,),
        ),
        PinRow(
            row_id="N23",
            held="Seeded history size",
            measured=(
                "reference tokens of the seeded pairs: tool name, compact arguments, observation"
            ),
            tolerance=f"the level +/- {_N9_BAND} tokens, summed over the pairs",
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=(_HISTORY,),
        ),
        PinRow(
            row_id="N24",
            held="Seeded history kind",
            measured=(
                "every seeded call is a read tool in the block, answered `ok`, mutating nothing"
            ),
            tolerance="every pair; an arm that seeds nothing holds it trivially",
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=(_FAULTS, _HISTORY, _TIMEOUTS, _RATELIMITS, _LANDED),
        ),
        PinRow(
            row_id="N25",
            held="Fault plan",
            measured=(
                "planned answers on the reference path, each carrying the knob's own status "
                "word (`unavailable`, `timeout` or `rate_limited`)"
            ),
            tolerance=(
                "exactly the level, the first stage taking the odd one; on landed, one on the "
                "last tool of the path at level 1 and none at level 0"
            ),
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=(_FAULTS, _TIMEOUTS, _RATELIMITS, _LANDED),
        ),
        PinRow(
            row_id="N26",
            held="Fault control length",
            measured="the control's seeded tokens against the high arm's fault pairs",
            tolerance=f"+/- {_N9_BAND} tokens, summed over the pairs",
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=(_FAULTS, _TIMEOUTS, _RATELIMITS),
        ),
        PinRow(
            row_id="N27",
            held="Block count",
            measured="tools in the block",
            tolerance="exactly the level",
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=(_BLOCK,),
        ),
        PinRow(
            row_id="N28",
            held="The right tools' place (block)",
            measured="the right tools' slots",
            tolerance=f"the same slots, inside the first {_BLOCK_HEAD}, at every level",
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=(_BLOCK,),
        ),
        PinRow(
            row_id="N29",
            held="Block token count (block)",
            measured=(
                "reference tokens of the rendered block; the control's filler against the "
                "high arm's extra"
            ),
            tolerance=(
                f"the block's growth is reported; the filler +/- {_N9_BAND} tokens, which "
                "is what refuses"
            ),
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=(_BLOCK,),
        ),
        PinRow(
            row_id="N30",
            held="Argument schema",
            measured="the stage tools' rendered schemas",
            tolerance="equal across levels",
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=(_ARGUMENTS,),
        ),
        PinRow(
            row_id="N31",
            held="Stated values",
            measured="the extra values the request states",
            tolerance=(
                f"exactly the level less {_ENGINE_ARGUMENTS}, the same on every stage call, "
                "each an opaque word no tool name carries"
            ),
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=(_ARGUMENTS,),
        ),
        PinRow(
            row_id="N32",
            held="Argument control length",
            measured="the control's filler against the high arm's stated values",
            tolerance=f"+/- {_N9_BAND} tokens",
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=(_ARGUMENTS,),
        ),
        PinRow(
            row_id="N33",
            held="Shape's calls and block",
            measured="stage calls in the reference; the block's size and tokens",
            tolerance=(
                f"{_SHAPE_CALLS} calls and {_K_B} tools at every width, which is what "
                "refuses; the tokens are reported"
            ),
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=(_SHAPE,),
        ),
        PinRow(
            row_id="N34",
            held="Shape control length",
            measured="the control's filler against the widest request's extra lines",
            tolerance=f"+/- {_N9_BAND} tokens",
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=(_SHAPE,),
        ),
        PinRow(
            row_id="N35",
            held="Spread's reads",
            measured=f"the {_SPREAD_READS} named reads; the parts they answer",
            tolerance=(
                f"the same {_SPREAD_READS} reads at every level; exactly the level's number "
                "of non-empty parts, in order, joining to the code"
            ),
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=(_SPREAD,),
        ),
    ]


def _compact(arguments: _Any) -> str:
    """A call's arguments as the wire carries them: one compact JSON object.

    A seeded history already holds the serialised form, because that is what an
    OpenAI-compatible chat completion sends; a reference call holds the mapping.
    """
    if isinstance(arguments, str):
        return arguments
    return _json.dumps(arguments, separators=(",", ":"))


def _pair_tokens(name: str, arguments: _Any, observation: str) -> int:
    """One `(assistant tool call, tool observation)` pair, in reference-tokenizer tokens.

    The tool name counted bare, the arguments as one compact JSON object, the observation
    as it stands.  This is N9's unit and the only place it is defined.
    """
    return _count_tokens(name) + _count_tokens(_compact(arguments)) + _count_tokens(observation)


def _messages(prompt: object) -> tuple[_Any, ...]:
    """The prompt as `Messages`, or empty when it is a plain string (`str | Messages`)."""
    if isinstance(prompt, (list, tuple)):
        return tuple(prompt)
    return ()


def _user_instruction(prompt: object) -> str:
    """The user instruction, and never the seeded history.

    N7 is measured over this alone.  A D control's seeded pairs name the read tools it was
    given, so an overlap set read from the whole prompt would refuse every control arm on
    history the model did not write.
    """
    if isinstance(prompt, str):
        return prompt
    parts = [
        str(message.get("content", ""))
        for message in _messages(prompt)
        if isinstance(message, _Mapping) and message.get("role") == "user"
    ]
    return "\n".join(parts)


def _seeded_pairs(prompt: object) -> tuple[tuple[str, _Any, str], ...]:
    """The seeded `(assistant tool call, tool observation)` pairs of a `Messages` prompt.

    The shape is the OpenAI chat shape, because N18 pins the endpoint type to
    OpenAI-compatible chat completions: an assistant message carrying `tool_calls`,
    then the `tool` message holding that call's observation.
    """
    pending: list[tuple[str, _Any]] = []
    pairs: list[tuple[str, _Any, str]] = []
    for message in _messages(prompt):
        if not isinstance(message, _Mapping):
            continue
        role = message.get("role")
        if role == "assistant":
            for call in message.get("tool_calls") or ():
                function = call.get("function", {}) if isinstance(call, _Mapping) else {}
                pending.append((str(function.get("name", "")), function.get("arguments", "")))
        elif role == "tool" and pending:
            name, arguments = pending.pop(0)
            pairs.append((name, arguments, str(message.get("content", ""))))
    return tuple(pairs)


def _instruction_tokens(text: str) -> tuple[str, ...]:
    """The user instruction's reference-tokenizer tokens, as the strings they stand for."""
    encoding = _reference_encoding()
    pieces: list[str] = []
    for token in encoding.encode_ordinary(text):
        piece = encoding.decode([token]).strip().lower()
        if piece:
            pieces.append(piece)
    return tuple(pieces)


def _tool_names(tools: tuple[_Any, ...]) -> tuple[str, ...]:
    return tuple(str(tool["name"]) for tool in tools)


def _lexical_overlap(instruction: str, tools: tuple[_Any, ...]) -> tuple[str, ...]:
    """N7's set: the instruction tokens that occur in any tool name, sorted."""
    names = tuple(name.lower() for name in _tool_names(tools))
    overlap = {
        piece for piece in _instruction_tokens(instruction) if any(piece in name for name in names)
    }
    return tuple(sorted(overlap))


def _rendered_block(tools: tuple[_Any, ...]) -> str:
    """The tool block as N4 and N5 read it: the schemas in slot order, canonically.

    Keys are sorted at every depth, so two blocks built by different insertion orders
    render the same string and neither hash nor token count moves with `PYTHONHASHSEED`.
    """
    return _json.dumps(list(tools), sort_keys=True, separators=(",", ":"))


def _status(observation: str) -> str:
    """An observation's status word, or nothing when the line has none."""
    fields = observation.split()
    return fields[1] if len(fields) > 1 else ""


def _right_tools(calls: tuple[_Any, ...]) -> tuple[str, ...]:
    """The tools the reference solution calls, in the order it first calls them."""
    return tuple(dict.fromkeys(str(call[0]) for call in calls))


def _ledger_number(name: str) -> str | None:
    """The four-digit ledger number a tool's name carries, if it carries one."""
    found = _LEDGER_NUMBER.search(name)
    return None if found is None else found.group(0)


def _lookalikes(
    names: tuple[str, ...], right: tuple[str, ...]
) -> tuple[str | None, tuple[str, ...]]:
    """The target ledger's number, and the number of every lookalike tool in slot order.

    The target's number is the one in the first right tool's name; a lookalike is a tool
    whose name carries any other.
    """
    target = _ledger_number(right[0]) if right else None
    numbers = tuple(
        number
        for number in (_ledger_number(name) for name in names)
        if number is not None and number != target
    )
    return target, numbers


def _block_digest(tools: tuple[_Any, ...]) -> str:
    return _hashlib.sha256(_rendered_block(tools).encode("utf-8")).hexdigest()


def _extra_values(tool: _Any, arguments: _Any) -> tuple[tuple[str, str], ...]:
    """The values a call carries in parameters its tool lists and does not require.

    A schema that names no required parameters requires them all, which is every schema
    but the arguments knob's stage tools.
    """
    if tool is None or not isinstance(arguments, _Mapping):
        return ()
    parameters = tool.get("parameters", {})
    properties = parameters.get("properties", {})
    required = parameters.get("required", tuple(properties))
    return tuple(
        sorted(
            (str(name), str(value))
            for name, value in arguments.items()
            if name in properties and name not in required
        )
    )


def _part(observation: str) -> str:
    """The part of a split code a read's answer carries, or nothing.

    A part answer's payload is the part, a full stop and filling; an answer that holds no
    part says so in the part's place.
    """
    fields = observation.split()
    if len(fields) < 3 or _PART_END not in fields[2]:
        return ""
    head = fields[2].split(_PART_END, 1)[0]
    return "" if head == _NO_PART else head


def measure_pins(bundle: _Bundle) -> PinRecord:
    """Measure every ledger row a bundle can answer, and name the reason for the rest.

    Twenty-eight rows are measurable from a bundle.  Only N10 and N13 need something no
    bundle carries -- a run's configuration and an episode's record for the serving pin,
    and the trace for realised tokens -- and each of those gets a reason rather than a
    silent absence.  Every row is measured on every bundle, whatever its knob: which rows
    a contrast is held to is `check_pins`'s question, read off `applies_to`.

    This is a read.  Nothing on the bundle is written, so a caller may measure one bundle
    under two ledgers (P3).
    """
    tools = tuple(bundle.tools)
    names = _tool_names(tools)
    by_name = {str(tool["name"]): tool for tool in tools}
    calls = tuple(bundle.reference_calls)
    observations = tuple(str(observation) for observation in bundle.reference_observations)
    rendered = _rendered_block(tools)
    block_tokens = _count_tokens(rendered)
    instruction = _user_instruction(bundle.prompt)

    right = _right_tools(calls)
    required = set(right)
    try:
        knob: str | None = _parse_arm_id(str(bundle.arm_id)).knob
    except ValueError:
        knob = None
    own_slot = _OWN_SLOT.get(knob) if knob is not None else None
    # The status word this knob's planned answers carry, which N25 and N26 count; an arm of a
    # knob that plans none counts no line, whatever its observations say.
    fault_word = _FAULT_WORDS.get(knob) if knob is not None else None
    slots = tuple(slot for slot in bundle.prompt_slots if slot[0] != own_slot)
    widths = tuple(sorted({len(observation.encode("utf-8")) for observation in observations}))
    counts = tuple(_count_tokens(observation) for observation in observations)
    required_slots = tuple(
        sorted(
            (str(tool["name"]), index)
            for index, tool in enumerate(tools)
            if str(tool["name"]) in required
        )
    )

    seeded = _seeded_pairs(bundle.prompt)
    paired = tuple(zip(calls, observations, strict=False))
    if seeded:
        # A control arm: N9's unit is the seeded pair, one total per pair, so `check_pins`
        # sums and nothing else has to.
        pairs = tuple(_pair_tokens(name, arguments, obs) for name, arguments, obs in seeded)
    else:
        pairs = tuple(
            _pair_tokens(str(call[0]), call[1], observation) for call, observation in paired
        )

    target, lookalikes = _lookalikes(names, right)
    seeded_tokens = sum(pairs) if seeded else 0
    fault_tokens = sum(
        _pair_tokens(str(call[0]), call[1], observation)
        for call, observation in paired
        if fault_word is not None and _status(observation) == fault_word
    )
    stage_calls = tuple(call for call in calls if str(call[0]) not in _SPEC.read_tools)
    extras = tuple(_extra_values(by_name.get(str(call[0])), call[1]) for call in stage_calls)
    stated = tuple(dict.fromkeys(value for extra in extras for _name, value in extra))
    lowered = tuple(name.lower() for name in names)
    read_calls = tuple(
        (call, observation) for call, observation in paired if str(call[0]) in _SPEC.read_tools
    )
    entry = str(_SPEC.parameter_names["entry"])
    code = next(
        (
            str(call[1][entry])
            for call in stage_calls
            if isinstance(call[1], _Mapping) and entry in call[1]
        ),
        "",
    )

    values: dict[str, _Any] = {
        "N1": str(bundle.scenario_hash),
        "N2": required_slots,
        "N3": str(bundle.system_prompt),
        "N4": _hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        "N5": block_tokens,
        "N6": (
            str(bundle.template_id),
            tuple(_count_tokens(str(value)) for _name, value in slots),
        ),
        "N7": _lexical_overlap(instruction, tools),
        "N8": (widths, (min(counts), max(counts)) if counts else (0, 0)),
        "N9": pairs,
        "N11": str(bundle.verifier.strictness),
        "N12": (str(bundle.engine_hash), str(bundle.generator_hash)),
        # Similarity: the lookalike tools, the block's length, each lookalike ledger's
        # number with the digits it shares in place with the target's, and the right tools.
        "N19": len(lookalikes),
        "N20": block_tokens,
        "N21": (
            target or "",
            tuple(
                (number, sum(a == b for a, b in zip(number, target or "", strict=False)))
                for number in sorted(set(lookalikes))
            ),
        ),
        "N22": _block_digest(tuple(by_name[name] for name in right if name in by_name)),
        # History and faults: the seeded pairs' tokens, the seeded pairs that are not a
        # read in the block answered `ok`, the failures planned for each right tool, and
        # the seeded tokens beside the failed pairs' tokens.
        "N23": seeded_tokens,
        "N24": tuple(
            index
            for index, (name, _arguments, observation) in enumerate(seeded)
            if name not in _SPEC.read_tools or name not in by_name or _status(observation) != _OK
        ),
        "N25": tuple(
            (
                name,
                sum(
                    1
                    for call, observation in paired
                    if str(call[0]) == name
                    and fault_word is not None
                    and _status(observation) == fault_word
                ),
            )
            for name in right
        ),
        "N26": (seeded_tokens, fault_tokens),
        # Block: its size, the right tools' slots, and its length beside the system prompt's.
        "N27": len(tools),
        "N28": required_slots,
        "N29": (block_tokens, _count_tokens(str(bundle.system_prompt))),
        # Arguments: the stage tools' schemas, the extra values each stage call carries with
        # the ones the request does not state and the ones a tool name carries, and the
        # request's length.
        "N30": _block_digest(tuple(tool for tool in tools if tool["name"] in _SPEC.stage_tools)),
        "N31": (
            extras,
            tuple(value for value in stated if value not in instruction),
            tuple(value for value in stated if any(value.lower() in name for name in lowered)),
        ),
        "N32": _count_tokens(instruction),
        # Shape: the stage calls, the block's size and length, and the request's length.
        "N33": (len(stage_calls), len(tools), block_tokens),
        "N34": _count_tokens(instruction),
        # Spread: the reads the reference makes, the part each answers, and the code.
        "N35": (
            tuple(
                (str(call[0]), _json.dumps(call[1], sort_keys=True, separators=(",", ":")))
                for call, _observation in read_calls
            ),
            tuple(_part(observation) for _call, observation in read_calls),
            code,
        ),
    }
    unmeasured = {
        "N10": (
            "the serving pin is a run's configuration, the arm spec and the serving-pin hash "
            "each episode records; a bundle carries none of the three, so the row is "
            "enforced when a run starts and not at generation"
        ),
        "N13": (
            "server-reported usage exists only once an episode has run; a bundle carries "
            "no trace, so the row is enforced at analysis against the pre-registered band"
        ),
    }
    return PinRecord(arm_id=str(bundle.arm_id), values=values, unmeasured=unmeasured)


def _detail(arm_ids: tuple[str, ...], records: dict[str, PinRecord], row_id: str) -> str:
    """One row's measured value per arm, in arm-id order."""
    return ", ".join(f"{arm}={records[arm].values[row_id]!r}" for arm in arm_ids)


def _equal_across_arms(
    arm_ids: tuple[str, ...], records: dict[str, PinRecord], row_id: str
) -> str | None:
    """The shape most rows take: one measured value, held equal across every arm."""
    seen = {records[arm].values[row_id] for arm in arm_ids}
    if len(seen) <= 1:
        return None
    return f"not equal across arms: {_detail(arm_ids, records, row_id)}"


def _moved_slots(arm_ids: tuple[str, ...], records: dict[str, PinRecord], row_id: str) -> list[str]:
    """The tools that sit in different slots in two arms, compared on the tools they share."""
    slots: dict[str, dict[str, int]] = {}
    for arm in arm_ids:
        for name, index in records[arm].values[row_id]:
            slots.setdefault(name, {})[arm] = index
    return [
        f"{name}: " + ", ".join(f"{arm}={index}" for arm, index in sorted(by_arm.items()))
        for name, by_arm in sorted(slots.items())
        if len(set(by_arm.values())) > 1
    ]


def _check_n2(arm_ids: tuple[str, ...], records: dict[str, PinRecord]) -> str | None:
    """N2 on the tools two arms share.

    Name *and* index, never a bare index set: d1 requires one tool and d8 requires eight,
    so a bare index set legitimately differs between levels and could not be compared.
    """
    moved = _moved_slots(arm_ids, records, "N2")
    if not moved:
        return None
    return "a required tool moved slot between arms: " + "; ".join(moved)


def _check_n3(
    knob: str,
    arm_ids: tuple[str, ...],
    records: dict[str, PinRecord],
    parsed: dict[str, _ParsedArm],
) -> str | None:
    """N3, with a distractor or block control's filler as the one permitted difference.

    The filler is appended "at the end of the system prompt", so a control's prompt is a
    plain arm's plus a suffix.  A difference anywhere else is not a filler, which is what
    tells the two apart without a new bundle field.  The other knobs' controls put their
    length elsewhere -- seeded pairs, or the end of the request -- so a suffix on one of
    theirs is a difference like any other.
    """
    plain = tuple(arm for arm in arm_ids if parsed[arm].control is None)
    controls = tuple(arm for arm in arm_ids if parsed[arm].control is not None)
    if not plain:
        return _equal_across_arms(arm_ids, records, "N3")
    bases = {records[arm].values["N3"] for arm in plain}
    if len(bases) > 1:
        return f"the plain arms' system prompts differ: {_detail(plain, records, 'N3')}"
    base = bases.pop()
    offenders = []
    for arm in controls:
        prompt = records[arm].values["N3"]
        if prompt == base:
            continue
        if knob in (_DISTRACTOR, _BLOCK) and prompt.startswith(base):
            # The control's filler, and the only difference N3 lets through.
            continue
        offenders.append(arm)
    if not offenders:
        return None
    return (
        "a control's system prompt differs from the plain arms' by something other than "
        f"a distractor or block control's filler suffix: {_detail(tuple(offenders), records, 'N3')}"
    )


def _check_n5(arm_ids: tuple[str, ...], records: dict[str, PinRecord]) -> str | None:
    """N5: knob R's block must change, so its token count is described and not held equal.

    The difference is reported whenever there is one; the band it is reported against is
    the pre-registration's, and this row never refuses.
    """
    return _block_growth(arm_ids, {arm: records[arm].values["N5"] for arm in arm_ids})


def _block_growth(arm_ids: tuple[str, ...], counts: dict[str, int]) -> str | None:
    """A block whose token count moves across arms, as the rows that report it say it."""
    spread = max(counts.values()) - min(counts.values())
    if spread == 0:
        return None
    return f"tool-block token count differs by {spread} across arms: " + ", ".join(
        f"{arm}={counts[arm]}" for arm in arm_ids
    )


def _check_n8(arm_ids: tuple[str, ...], records: dict[str, PinRecord]) -> str | None:
    """N8, a per-arm property: `L_obs` exact and every observation's tokens in band.

    Not a cross-arm equality.  d1 and d8 carry different numbers of observations, so an
    equality here would refuse a clean contrast.
    """
    offenders = []
    for arm in arm_ids:
        widths, (low, high) = records[arm].values["N8"]
        if not widths:
            continue
        if tuple(widths) != (_L_OBS,):
            offenders.append(f"{arm}: observation widths {tuple(widths)}, expected ({_L_OBS},)")
        elif not (_BAND_LO <= low <= high <= _BAND_HI):
            offenders.append(
                f"{arm}: observation tokens [{low}, {high}] outside [{_BAND_LO}, {_BAND_HI}]"
            )
    if not offenders:
        return None
    return "; ".join(offenders)


def _check_n9(
    knob: str,
    arm_ids: tuple[str, ...],
    records: dict[str, PinRecord],
    parsed: dict[str, _ParsedArm],
) -> str | None:
    """N9: the aggregate over a control's seeded pairs against the pairs they stand in for.

    The control runs pairs 1..dL itself, so its seeded block stands in for the high arm's
    pairs dL+1..H, every one of them a chain pair -- which is why the single cheap stage-1
    call cancels out of the comparison.  The comparison is over sums and never
    per pair; the band is `_N9_BAND` tokens in both directions.
    """
    offenders = []
    for arm in arm_ids:
        reference = parsed[arm].control
        if reference is None:
            continue
        low = parsed[arm].level
        high_arm = _render_arm_id(knob, reference, None)
        if high_arm not in records:
            # Nothing to compare against.  N15 makes the constructor total, not the
            # contrast: a pre-registration that sweeps a control without its high arm is
            # a 4 error, and the row has no measurement here.
            continue
        seeded = records[arm].values["N9"]
        chain = records[high_arm].values["N9"]
        if len(seeded) != reference - low:
            offenders.append(
                f"{arm}: seeded {len(seeded)} pairs, expected H - dL = {reference - low}"
            )
            continue
        residual = sum(seeded) - sum(chain[low:])
        if abs(residual) > _N9_BAND:
            offenders.append(
                f"{arm}: seeded history is {residual:+d} tokens against the {high_arm} "
                f"pairs it stands in for, outside the +/-{_N9_BAND} band"
            )
    if not offenders:
        return None
    return "; ".join(offenders)


# ---------------------------------------------------------------------------
# the newer knobs' rows.  Each takes the contrast and gives what refuses it and what is
# reported, either or both of which may be nothing.
# ---------------------------------------------------------------------------


@_dataclass(frozen=True)
class _Contrast:
    """The arms of one knob's contrast, as the row checks read them."""

    knob: str
    arm_ids: tuple[str, ...]
    records: dict[str, PinRecord]
    parsed: dict[str, _ParsedArm]

    def value(self, arm: str, row_id: str) -> _Any:
        return self.records[arm].values[row_id]

    def controls(self) -> tuple[tuple[str, str], ...]:
        """Each control arm beside the arm of the level it stands in for, where the
        contrast holds that arm.  A control without it has nothing to be compared with."""
        out = []
        for arm in self.arm_ids:
            reference = self.parsed[arm].control
            if reference is None:
                continue
            high_arm = _render_arm_id(self.knob, reference, None)
            if high_arm in self.records:
                out.append((arm, high_arm))
        return tuple(out)


def _joined(offenders: list[str]) -> str | None:
    return "; ".join(offenders) if offenders else None


def _outside_band(residual: int) -> bool:
    """The one band every "plus or minus two tokens" in the ledger means."""
    return abs(residual) > _N9_BAND


def _check_n19(c: _Contrast) -> str | None:
    return _joined(
        [
            f"{arm}: {c.value(arm, 'N19')} lookalike tools, expected {_LOOKALIKES}"
            for arm in c.arm_ids
            if c.value(arm, "N19") != _LOOKALIKES
        ]
    )


def _check_n21(c: _Contrast) -> str | None:
    """Six lookalike ledgers, each sharing exactly the level's digits in place with the
    target's number, and none of the seven numbers starting with 0."""
    offenders = []
    for arm in c.arm_ids:
        level = c.parsed[arm].level
        target, shared = c.value(arm, "N21")
        if len(shared) != _LOOKALIKE_LEDGERS:
            offenders.append(
                f"{arm}: {len(shared)} lookalike ledgers, expected {_LOOKALIKE_LEDGERS}"
            )
        zeros = [number for number in (target, *(n for n, _count in shared)) if number[:1] == "0"]
        if zeros:
            offenders.append(f"{arm}: a ledger number starts with 0: {', '.join(zeros)}")
        off = [f"{number} shares {count}" for number, count in shared if count != level]
        if off:
            offenders.append(
                f"{arm}: a lookalike ledger's number does not share exactly {level} digits "
                f"in place with {target}: {', '.join(off)}"
            )
    return _joined(offenders)


def _check_n23(c: _Contrast) -> str | None:
    offenders = []
    for arm in c.arm_ids:
        residual = c.value(arm, "N23") - c.parsed[arm].level
        if _outside_band(residual):
            offenders.append(
                f"{arm}: seeded history is {residual:+d} tokens against its level, outside "
                f"the +/-{_N9_BAND} band"
            )
    return _joined(offenders)


def _check_n24(c: _Contrast) -> str | None:
    return _joined(
        [
            f"{arm}: seeded pairs {list(c.value(arm, 'N24'))} are not a read tool in the "
            "block answered ok"
            for arm in c.arm_ids
            if c.value(arm, "N24")
        ]
    )


def _check_n25(c: _Contrast) -> str | None:
    """The arm's own level, split over the right tools.  A control plans its own level's
    failures and never those of the level it stands in for.  On landed the plan is one answer
    on the last right tool at level 1, and none at level 0."""
    offenders = []
    for arm in c.arm_ids:
        planned = c.value(arm, "N25")
        level = c.parsed[arm].level
        if c.knob == _LANDED:
            expected = tuple(
                level if index == len(planned) - 1 else 0 for index in range(len(planned))
            )
        else:
            expected = _split_evenly(level, len(planned))
        if tuple(count for _name, count in planned) != expected or (
            not planned and c.parsed[arm].level
        ):
            offenders.append(
                f"{arm}: planned failures {list(planned)}, expected {list(expected)} over "
                "the right tools"
            )
    return _joined(offenders)


def _check_n26(c: _Contrast) -> str | None:
    """A control's seeded pairs against the failed calls of the arm it stands in for, less
    any the control fails itself."""
    offenders = []
    for arm, high_arm in c.controls():
        seeded, own_faults = c.value(arm, "N26")
        _high_seeded, high_faults = c.value(high_arm, "N26")
        residual = seeded - (high_faults - own_faults)
        if _outside_band(residual):
            offenders.append(
                f"{arm}: seeded history is {residual:+d} tokens against the {high_arm} "
                f"failed calls it stands in for, outside the +/-{_N9_BAND} band"
            )
    return _joined(offenders)


def _check_n27(c: _Contrast) -> str | None:
    return _joined(
        [
            f"{arm}: {c.value(arm, 'N27')} tools in the block, expected {c.parsed[arm].level}"
            for arm in c.arm_ids
            if c.value(arm, "N27") != c.parsed[arm].level
        ]
    )


def _check_n28(c: _Contrast) -> str | None:
    offenders = [
        f"{arm}: {name} sits in slot {index}, outside the first {_BLOCK_HEAD}"
        for arm in c.arm_ids
        for name, index in c.value(arm, "N28")
        if index >= _BLOCK_HEAD
    ]
    moved = _moved_slots(c.arm_ids, c.records, "N28")
    if moved:
        offenders.append("a right tool moved slot between arms: " + "; ".join(moved))
    return _joined(offenders)


def _check_n29(c: _Contrast) -> tuple[str | None, str | None]:
    """The block's growth, reported; and a control's system-prompt filler against the extra
    block of the arm it stands in for, which refuses outside the band."""
    growth = _block_growth(c.arm_ids, {arm: c.value(arm, "N29")[0] for arm in c.arm_ids})
    offenders = []
    for arm, high_arm in c.controls():
        block, prompt = c.value(arm, "N29")
        high_block, high_prompt = c.value(high_arm, "N29")
        residual = (prompt - high_prompt) - (high_block - block)
        if _outside_band(residual):
            offenders.append(
                f"{arm}: the filler is {residual:+d} tokens against the extra block of "
                f"{high_arm}, outside the +/-{_N9_BAND} band"
            )
    return _joined(offenders), growth


def _check_n31(c: _Contrast) -> str | None:
    offenders = []
    for arm in c.arm_ids:
        wanted = c.parsed[arm].level - _ENGINE_ARGUMENTS
        extras, unstated, named = c.value(arm, "N31")
        if len(set(extras)) > 1:
            offenders.append(f"{arm}: the stage calls carry different extra values")
        if any(len(extra) != wanted for extra in extras) or (not extras and wanted):
            offenders.append(
                f"{arm}: the stage calls carry {[len(extra) for extra in extras]} extra "
                f"values, expected {wanted} on each"
            )
        if unstated:
            offenders.append(f"{arm}: the request does not state {', '.join(unstated)}")
        if named:
            offenders.append(f"{arm}: a tool name carries {', '.join(named)}")
    return _joined(offenders)


def _check_request_length(c: _Contrast, row_id: str) -> str | None:
    """N32 and N34: a control's whole request against that of the arm it stands in for.
    The two requests differ in the filler and in what it stands in for, and nothing else."""
    offenders = []
    for arm, high_arm in c.controls():
        residual = c.value(arm, row_id) - c.value(high_arm, row_id)
        if _outside_band(residual):
            offenders.append(
                f"{arm}: the request is {residual:+d} tokens against that of {high_arm}, "
                f"outside the +/-{_N9_BAND} band"
            )
    return _joined(offenders)


def _check_n33(c: _Contrast) -> tuple[str | None, str | None]:
    offenders = []
    for arm in c.arm_ids:
        calls, tools, _tokens = c.value(arm, "N33")
        if calls != _SHAPE_CALLS or tools != _K_B:
            offenders.append(
                f"{arm}: {calls} stage calls and {tools} tools, expected {_SHAPE_CALLS} and {_K_B}"
            )
    growth = _block_growth(c.arm_ids, {arm: c.value(arm, "N33")[2] for arm in c.arm_ids})
    return _joined(offenders), growth


def _check_n35(c: _Contrast) -> str | None:
    offenders = []
    if len({c.value(arm, "N35")[0] for arm in c.arm_ids}) > 1:
        offenders.append("the reads the reference makes differ between arms")
    for arm in c.arm_ids:
        reads, parts, code = c.value(arm, "N35")
        level = c.parsed[arm].level
        if len(reads) != _SPREAD_READS:
            offenders.append(f"{arm}: {len(reads)} reads named, expected {_SPREAD_READS}")
        held = [part for part in parts if part]
        if len(held) != level:
            offenders.append(f"{arm}: {len(held)} reads answer with a part, expected {level}")
        if not code or "".join(parts) != code:
            offenders.append(f"{arm}: the parts do not join, in order, to the entry code")
    return _joined(offenders)


def _check_row(row_id: str, c: _Contrast) -> tuple[str | None, str | None]:
    """One row over one contrast: what refuses it, and what is reported."""
    if row_id == "N2":
        return _check_n2(c.arm_ids, c.records), None
    if row_id == "N3":
        return _check_n3(c.knob, c.arm_ids, c.records, c.parsed), None
    if row_id == "N5":
        return None, _check_n5(c.arm_ids, c.records)
    if row_id == "N7":
        # A wider shape request and its block name more ledgers, so the overlap set is the
        # knob there: reported, and refused on every other knob.
        moved = _equal_across_arms(c.arm_ids, c.records, "N7")
        return (None, moved) if c.knob == _SHAPE else (moved, None)
    if row_id == "N8":
        return _check_n8(c.arm_ids, c.records), None
    if row_id == "N9":
        return _check_n9(c.knob, c.arm_ids, c.records, c.parsed), None
    if row_id == "N29":
        return _check_n29(c)
    if row_id == "N33":
        return _check_n33(c)
    if row_id in ("N32", "N34"):
        return _check_request_length(c, row_id), None
    single = {
        "N19": _check_n19,
        "N21": _check_n21,
        "N23": _check_n23,
        "N24": _check_n24,
        "N25": _check_n25,
        "N26": _check_n26,
        "N27": _check_n27,
        "N28": _check_n28,
        "N31": _check_n31,
        "N35": _check_n35,
    }
    if row_id in single:
        return single[row_id](c), None
    return _equal_across_arms(c.arm_ids, c.records, row_id), None


def check_pins(bundles_by_arm: _Mapping[str, _Bundle]) -> PinReport:
    """Run the ledger over the arms of one contrast.

    Every row is an equality *across* arms, so one arm satisfies all of them vacuously and
    two knobs in one call is a caller error rather than a pin violation.  Both raise
    `ValueError`: a refusal is a report a reader files, and neither of these is one.
    """
    parsed = {arm: _parse_arm_id(arm) for arm in bundles_by_arm}
    seen = {arm.knob for arm in parsed.values()}
    if len(seen) > 1:
        raise ValueError(
            "check_pins runs over the arms of one knob; "
            f"these arms carry {sorted(seen)}"
        )
    if len(bundles_by_arm) < 2:
        raise ValueError(
            "a contrast is two or more arms; every ledger row is an equality across arms "
            f"and {len(bundles_by_arm)} arm(s) satisfies all of them vacuously"
        )
    knob = seen.pop()
    arm_ids = tuple(sorted(bundles_by_arm))
    records = {arm: measure_pins(bundles_by_arm[arm]) for arm in arm_ids}
    contrast = _Contrast(knob=knob, arm_ids=arm_ids, records=records, parsed=parsed)

    violations: list[tuple[str, str]] = []
    reported: list[tuple[str, str]] = []
    for row in pin_ledger(knob):
        if knob not in row.applies_to or row.row_id in records[arm_ids[0]].unmeasured:
            continue
        refusal, note = _check_row(row.row_id, contrast)
        if note is not None:
            reported.append((row.row_id, note))
        if refusal is not None:
            violations.append((row.row_id, refusal))

    return PinReport(
        knob=knob,
        refused=bool(violations),
        violations=tuple(violations),
        reported=tuple(reported),
        records=records,
    )
