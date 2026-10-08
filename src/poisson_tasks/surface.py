"""What the model sees of a task, and what is applied in front of the engine.

Private.  The generator, `tasks.verify` and the export's tool server all read this module, so
the three agree by construction: a block is shown under the names and descriptions
`display_map` gives, a call is replayed and served under the engine name it gives, and a
faults arm's planned failures are `fault_plan`'s, applied in front of the engine by
`apply_planned`.  It imports the engine and the knobs and never the generator, and its
bytes are part of the generator hash, because a change here changes tasks.
`tests/test_k1_surface.py` says what each name does; the similarity knob's draws and its
numbered names are pinned by `tests/test_k2_block.py`; the faults knob's plan and answer by
`tests/test_k3_plan.py` and `tests/test_k3_counting.py`.

`display_map` and `fault_plan` take the tools as an argument and never read the built-in
block themselves, so a block of a caller's own tools goes through them unchanged, with one
exception the block-size knob needs: on a block arm, a name made of one of the table's read
verbs and one of its facets that the engine does not read under is a read copy, shown as
the engine read of that facet (`_block_shown`; `tests/test_k5_aliases.py`).

The argument-difficulty knob's check lives here too, so the same three readers agree on
it: an arguments arm's stage call must carry exactly the extra values its request
states, read off the reference by `stated_values`, and `apply_planned` refuses any other
stage call with a `bad_args` line in front of the engine, which then sees only its own
two arguments (`tests/test_k6_check.py`, `tests/test_k6_live.py`).
"""

from __future__ import annotations

import hashlib as _hashlib
from collections.abc import Callable as _Callable
from collections.abc import Mapping as _Mapping
from collections.abc import Sequence as _Sequence
from dataclasses import dataclass as _dataclass
from dataclasses import replace as _replace
from typing import Any as _Any
from typing import TypeVar as _TypeVar

from poisson_tasks.engine import DomainState as _DomainState
from poisson_tasks.engine import EngineSpec as _EngineSpec
from poisson_tasks.engine import apply as _apply
from poisson_tasks.knobs import (
    _ARGUMENTS,
    _BLOCK,
    _D_B,
    _FAULTS,
    _LOOKALIKE_LEDGERS,
    _MAX_SIMILARITY,
    _NUMBER_WIDTH,
    _SIMILARITY,
    _SPREAD,
    _UNAVAILABLE,
    _parse_arm_id,
    _split_evenly,
)

_SPEC = _EngineSpec.load()

# The key of the keyed draw.  The spelling is deliberately not the package's: these bytes are
# hash input, so respelling them moves every seed-derived choice of every task.
_DRAW_KEY = b"task-generator/structure-draw/1"

# The similarity knob's four draws, each from a domain of its own: none is appended to the
# scenario's draw, so no task of another knob moves.  Respelling one moves every similarity
# task's numbers.
_NUMBER_DOMAIN = b"task-generator/similarity-number/1"
_LEDGERS_DOMAIN = b"task-generator/similarity-ledgers/1"
_PLACES_DOMAIN = b"task-generator/similarity-places/1"
_DIGITS_DOMAIN = b"task-generator/similarity-digits/1"
_DIGITS = "0123456789"
# A changed place may take eight digits or nine (never the target's, and never 0 in the first
# place).  A rank drawn from 72, a multiple of both, lands evenly on either set.
_RANK_RADIX = 72

# A name no engine knows.  A call to a name the block does not show is replayed as this, so it
# is answered as no tool and changes nothing, as the harness answers it without the server.
_NO_TOOL = ""

# What the first stage tool's description says of the entry code, and what it says on a spread
# arm, where the request does not state the code and four reads hold its parts.
_CODE_STATED = "stated in the request"
_CODE_ASSEMBLED = "assembled from the reads named in the request"

# How a block arm's read copy describes itself: each of the table's read verbs in the form
# the engine's own reads use ("returns the region field of the named catalogue item"), so a
# copy reads as the engine's reads do and as none of them.  `_check_said` refuses a table
# whose verbs this does not cover, below.
_SAID = {
    "lookup": "looks up",
    "fetch": "fetches",
    "query": "queries",
    "match": "matches",
    "scan": "scans",
    "probe": "probes",
    "trace": "traces",
    "count": "counts",
    "list": "lists",
    "read": "reads",
    "find": "finds",
    "report": "reports",
    "filter": "filters",
    "search": "searches",
    "select": "selects",
    "collect": "collects",
}


def _check_said() -> None:
    """Every read verb of the table has its form, or a block arm's copies could not be described;
    asserted at import, as the generator asserts its filler words, so a table version that
    added a verb is refused here and not met as a `KeyError` on one task."""
    verbs = set(_SPEC.table["read_verbs"])
    if set(_SAID) != verbs:
        raise ValueError(
            "the read copies have words for " + ", ".join(sorted(_SAID)) + " and the table's read "
            "verbs are " + ", ".join(sorted(verbs))
        )


_check_said()


def _prf(domain: bytes, seed: int, split: str) -> bytes:
    """A keyed pseudo-random function of the task seed and the split, and of nothing
    else -- the arm is not an argument, which is what makes N1 true by construction."""
    message = f"{seed}\x1f{split}".encode("ascii")
    return _hashlib.blake2b(domain + b"\x1f" + message, key=_DRAW_KEY, digest_size=32).digest()


@_dataclass(frozen=True)
class Shown:
    """One tool as a block shows it: the engine's name for it, and the description the block
    gives it when that is not the engine's own (`None` when it is)."""

    engine: str
    description: str | None


_T = _TypeVar("_T")


def _mixed_radix(material: bytes, radices: _Sequence[int]) -> tuple[int, ...]:
    """The keyed draw read as one integer, digit by digit, low digits first: the generator's
    own decoding, and uniform for the same reason its draws are (every radix list here
    multiplies to far below 2^256)."""
    value = int.from_bytes(material, "big")
    digits: list[int] = []
    for radix in radices:
        digits.append(value % radix)
        value //= radix
    return tuple(digits)


def _ordered(digits: _Sequence[int], items: _Sequence[_T]) -> tuple[_T, ...]:
    """An ordered selection of `len(digits)` of `items`, by the same decoding."""
    remaining = list(items)
    return tuple(remaining.pop(digit) for digit in digits)


def target_number(seed: int, split: str) -> str:
    """The target ledger's number: four digits, the first never 0, from its own domain."""
    lowest = 10 ** (_NUMBER_WIDTH - 1)
    (offset,) = _mixed_radix(_prf(_NUMBER_DOMAIN, seed, split), (9 * lowest,))
    return str(lowest + offset)


def lookalike_ledgers(seed: int, split: str, target: str) -> tuple[str, ...]:
    """The six ledgers whose first two stage tools are the lookalikes, in drawn order, out of
    the eleven that are not the target's."""
    others = tuple(qualifier for qualifier in _SPEC.qualifiers if qualifier != target)
    radices = tuple(range(len(others), len(others) - _LOOKALIKE_LEDGERS, -1))
    return _ordered(_mixed_radix(_prf(_LEDGERS_DOMAIN, seed, split), radices), others)


def lookalike_numbers(seed: int, split: str, level: int) -> tuple[str, ...]:
    """Each lookalike ledger's number at `level`, in the ledgers' drawn order.

    Each shares exactly `level` places with the target's number: the four places are drawn
    in an order and the first `level` are kept; each changed place takes a drawn digit that
    is not the target's there, and not 0 in the first place.  The seven numbers are distinct,
    a repeat taking the next digit in its last changed place.  The places and the digits are
    drawn once for every ledger, so the level changes how many places are kept and nothing
    else, and the lookalikes of one seed are kin across the levels.
    """
    if not 0 <= level <= _MAX_SIMILARITY:
        raise ValueError(f"no lookalike shares {level} of {_NUMBER_WIDTH} places")
    target = target_number(seed, split)
    width = _NUMBER_WIDTH
    places = _mixed_radix(
        _prf(_PLACES_DOMAIN, seed, split), tuple(range(width, 0, -1)) * _LOOKALIKE_LEDGERS
    )
    ranks = _mixed_radix(
        _prf(_DIGITS_DOMAIN, seed, split), (_RANK_RADIX,) * (width * _LOOKALIKE_LEDGERS)
    )
    numbers: list[str] = []
    for ledger in range(_LOOKALIKE_LEDGERS):
        at = ledger * width
        order = _ordered(places[at : at + width], range(width))
        kept = frozenset(order[:level])
        rank = dict(enumerate(ranks[at : at + width]))
        number = _lookalike_number(target, kept, rank)
        while number in numbers:
            rank[order[-1]] += 1
            number = _lookalike_number(target, kept, rank)
        numbers.append(number)
    return tuple(numbers)


def _lookalike_number(target: str, kept: frozenset[int], rank: dict[int, int]) -> str:
    digits: list[str] = []
    for place, digit in enumerate(target):
        if place in kept:
            digits.append(digit)
            continue
        allowed = [d for d in _DIGITS if d != digit and (place > 0 or d != "0")]
        digits.append(allowed[rank[place] % len(allowed)])
    return "".join(digits)


def _numbered_stage_tools(
    seed: int, split: str, level: int, target: str
) -> dict[str, tuple[str, str]]:
    """Engine name -> (shown name, shown description) for the first two stage tools of the
    target ledger and of its six lookalike ledgers.

    A ledger's tools are shown as `submit_<stage>_<number>`, the engine's name with the
    ledger's class word replaced by its number, and described by the table's own templates
    with the ledger named by number: the first stage "for a ledger 4417 record", the second
    "requires the token returned by" the first stage's shown name.  So the seven tools of a
    stage are one tool but for the number, and no class word is shown anywhere.
    """
    ledgers = (target,) + lookalike_ledgers(seed, split, target)
    numbers = (target_number(seed, split),) + lookalike_numbers(seed, split, level)
    templates = _SPEC.table["description_templates"]
    verb = _SPEC.table["write_verb"]
    out: dict[str, tuple[str, str]] = {}
    for qualifier, number in zip(ledgers, numbers, strict=True):
        shown_first = f"{verb}_{_SPEC.stage_names[0]}_{number}"
        for index in range(_D_B):
            stage = _SPEC.stage_names[index]
            shown = f"{verb}_{stage}_{number}"
            if index == 0:
                description = templates["stage_first"].format(qualifier=f"ledger {number}")
            else:
                description = templates["stage_chain"].format(previous_tool=shown_first)
            out[f"{verb}_{stage}_{qualifier}"] = (shown, description)
    return out


def shown_names(
    seed: int, split: str, arm_id: str, goal: _Sequence[_Any], engines: _Sequence[str]
) -> tuple[str, ...]:
    """The names a block shows for `engines`, the engine names in slot order.

    The generator's half of the map: it builds a block in engine names and asks here what to
    show, and then reads `display_map` with the answer, as the verifier and the tool server
    do.  Every knob but similarity shows the names the block is built in: the engine's own,
    and on a block arm the read copies' as well.
    """
    arm = _parse_arm_id(arm_id)
    if arm.knob != _SIMILARITY:
        return tuple(engines)
    numbered = _numbered_stage_tools(seed, split, arm.level, str(goal[0]))
    return tuple(numbered[name][0] if name in numbered else name for name in engines)


def display_map(
    seed: int, split: str, arm_id: str, goal: _Sequence[_Any], tools: _Sequence[str]
) -> dict[str, Shown]:
    """Each of `tools`, the names a block shows, mapped to what it stands for, in block order.

    Every knob but similarity shows the engine's own names.  Similarity shows the first two
    stage tools of the target ledger and of six other ledgers under numbered names
    (`_numbered_stage_tools`), drawn from `seed` and `split`; a name the knob hides, an
    engine stage tool's own, stands for no tool, so a block that showed one would serve
    nothing under it.  The spread knob changes one description: the target ledger's first
    stage tool says its entry code is stated in the request, which is false where the
    request names four reads instead, so there it says the code is assembled from them, the
    same at every level.  Block size shows a read copy, a name the engine does not read
    under made of one of the table's read verbs and one of its facets, as the engine read of
    that facet in words of its own, and every other name as itself (`_block_shown`).
    """
    arm = _parse_arm_id(arm_id)
    knob = arm.knob
    if knob == _SIMILARITY:
        numbered = _numbered_stage_tools(seed, split, arm.level, str(goal[0]))
        by_shown = {
            shown: Shown(engine=engine, description=description)
            for engine, (shown, description) in numbered.items()
        }
        mapped: dict[str, Shown] = {}
        for name in tools:
            if name in by_shown:
                mapped[name] = by_shown[name]
            elif name in _SPEC.stage_tools:
                mapped[name] = Shown(engine=_NO_TOOL, description=None)
            else:
                mapped[name] = Shown(engine=name, description=None)
        return mapped
    if knob == _BLOCK:
        return {name: _block_shown(name) for name in tools}
    first_stage = None
    if knob == _SPREAD:
        first_stage = next(
            (
                name
                for name, (index, qualifier) in _SPEC.stage_tools.items()
                if index == 0 and qualifier == goal[0]
            ),
            None,
        )
    shown: dict[str, Shown] = {}
    for name in tools:
        description = None
        if name == first_stage:
            own = next(tool.description for tool in _SPEC.tools if tool.name == name)
            description = own.replace(_CODE_STATED, _CODE_ASSEMBLED)
        shown[name] = Shown(engine=name, description=description)
    return shown


def _block_shown(name: str) -> Shown:
    """One of a block arm's tools: a read copy as the engine read of its facet, under words
    of its own, and any other name as itself, as every other knob shows it, so a block of a
    caller's own tools is shown unchanged (`tests/test_k1_surface.py`).  A copy is a name
    the engine does not read under, made of one of the table's read verbs and one of its
    facets; the engine's own reads are themselves."""
    verb, _sep, facet = name.partition("_")
    if (
        name not in _SPEC.read_tools
        and verb in _SPEC.table["read_verbs"]
        and facet in _SPEC.table["facets"]
    ):
        engine = next(read for read, own in _SPEC.read_tools.items() if own == facet)
        return Shown(
            engine=engine,
            description=f"{_SAID[verb]} the {facet} field of the named catalogue item",
        )
    return Shown(engine=name, description=None)


def engine_name(shown: dict[str, Shown], name: _Any) -> str:
    """The engine's name for a called name, or a name no engine knows when the block does not
    show it."""
    entry = shown.get(name) if isinstance(name, str) else None
    return _NO_TOOL if entry is None else entry.engine


def fault_plan(arm_id: str, path: _Sequence[str]) -> dict[str, int]:
    """How many times each tool on the reference path answers `unavailable` before it works.

    A faults arm's level, split over the path's tools as evenly as it goes, the earlier tools
    taking the extra; a tool the path calls twice is one tool, and a tool planned no failure
    is left out.  A faults control plans its own level's failures, never those of the level
    it stands in for, and an arm of any other knob plans none.
    """
    arm = _parse_arm_id(arm_id)
    if arm.knob != _FAULTS:
        return {}
    tools = tuple(dict.fromkeys(path))
    return {
        tool: count
        for tool, count in zip(tools, _split_evenly(arm.level, len(tools)), strict=True)
        if count
    }


def reference_plan(
    arm_id: str, shown: dict[str, Shown], reference_calls: _Sequence[tuple[str, _Any]]
) -> dict[str, int]:
    """The arm's fault plan over its reference path: `fault_plan` of the reference's tools,
    each under the engine name its shown name stands for.  The generator, `tasks.verify`, the
    tool server and the record reader all derive the plan this way, from the arm id and the
    reference calls a bundle already carries, so no bundle field holds it."""
    return fault_plan(arm_id, tuple(engine_name(shown, name) for name, _args in reference_calls))


def _status_line(seq: int, status_word: str) -> str:
    """A refusal answered in front of the engine: the engine's own line at `seq`, saying
    `status_word` in the status field (`unavailable` for a planned failure, `bad_args` for a
    stage call the argument check refuses), with the table's error payload.  Rendered from
    the table's layout, so the line is `L_obs` bytes like every other observation and the
    engine's private renderer stays private."""
    layout = _SPEC.layout
    rendered_seq = str(seq).rjust(layout["seq_width"], layout["seq_fill"])
    if len(rendered_seq) != layout["seq_width"]:
        raise ValueError(f"seq {seq} does not fit the {layout['seq_width']}-byte field")
    status = status_word.ljust(layout["status_width"], layout["status_fill"])
    separator: str = layout["separator"]
    return separator.join((rendered_seq, status, str(layout["error_payload"])))


_Step = _Callable[[_DomainState, tuple[str, _Any]], tuple[_DomainState, str]]

# The status word the argument check refuses with: the engine's own for a call whose
# arguments it cannot take, so a refused stage call reads as any refused call does.
_BAD_ARGS = "bad_args"


def _engine_parameters(engine: str) -> frozenset[str]:
    """The parameters the engine's tool `engine` takes, the ones a call reaches it with."""
    return frozenset(next(tool.parameters for tool in _SPEC.tools if tool.name == engine))


def stated_values(
    arm_id: str, shown: dict[str, Shown], reference_calls: _Sequence[tuple[str, _Any]]
) -> dict[str, str] | None:
    """The extra values an arguments arm's request states, which every stage call must
    carry: the values the reference's first stage call carries beside the engine's own
    parameters, each under its parameter.  Read off the reference the generator already
    writes, so no bundle field holds them, and derived the same way by the generator's
    verifier, the tool server and the record reader.  `None` on every other knob, whose
    stage calls take no check; an arguments arm whose reference makes no stage call states
    nothing."""
    if _parse_arm_id(arm_id).knob != _ARGUMENTS:
        return None
    for name, arguments in reference_calls:
        engine = engine_name(shown, name)
        if engine in _SPEC.stage_tools and isinstance(arguments, _Mapping):
            own = _engine_parameters(engine)
            return {str(k): str(v) for k, v in arguments.items() if k not in own}
    return {}


def _checked_stage_call(
    name: str, arguments: _Mapping[str, _Any], stated: _Mapping[str, str]
) -> tuple[str, _Any] | None:
    """A stage call as the engine is to see it, with only its own parameters, or `None`
    when the call does not carry exactly the stated values: one missing, one in another
    parameter, one that is not the value exactly (another case is another value), or one
    in a parameter the request did not state, an empty string among them."""
    own = _engine_parameters(name)
    extras = {k: v for k, v in arguments.items() if k not in own}
    if extras != stated:
        return None
    return name, {k: v for k, v in arguments.items() if k in own}


def apply_planned(
    state: _DomainState,
    counts: dict[str, int],
    call: tuple[str, _Any],
    plan: dict[str, int],
    *,
    step: _Step = _apply,
    stated: _Mapping[str, str] | None = None,
) -> tuple[_DomainState, dict[str, int], str]:
    """One call that reached the tool server, with the planned failures and the argument
    check applied in front of the engine.

    `counts` is how many times each tool has been called so far, whatever the arguments, and
    the first `plan[tool]` calls to a tool answer `unavailable`: the counter advances, as it
    does on every call (E5), and the records do not.  Every other call reaches the engine
    through `step`, the engine's own `apply` unless the caller hands in its own name for it;
    the tool server does, so that every engine step it takes goes through one name under its
    lock.  The counts after the call are returned, and the ones given are not written.

    `stated` is an arguments arm's stated values (`stated_values`), and `None` on any other
    arm.  With them, a stage call whose extra values are not exactly the stated ones is
    answered `bad_args` at its number and reaches no engine, so the records do not move;
    one that carries them reaches the engine with only its own two arguments.  The check
    stands before the engine, so a wrong second stage call before the first is `bad_args`
    and not the engine's `not_ready`.
    """
    name, arguments = call
    made = counts.get(name, 0)
    after_counts = {**counts, name: made + 1}
    if made < plan.get(name, 0):
        seq = state.next_seq
        return _replace(state, next_seq=seq + 1), after_counts, _status_line(seq, _UNAVAILABLE)
    if stated is not None and name in _SPEC.stage_tools and isinstance(arguments, _Mapping):
        checked = _checked_stage_call(name, arguments, stated)
        if checked is None:
            seq = state.next_seq
            return _replace(state, next_seq=seq + 1), after_counts, _status_line(seq, _BAD_ARGS)
        call = checked
    after, observation = step(state, call)
    return after, after_counts, observation
