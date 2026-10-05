"""What the model sees of a task, and what is applied in front of the engine.

Private.  The generator, `tasks.verify` and the export's tool server all read this module, so
the three agree by construction: a block is shown under the names and descriptions
`display_map` gives, a call is replayed and served under the engine name it gives, and a
faults arm's planned failures are `fault_plan`'s.  It imports the engine and the knobs and
never the generator, and its bytes are part of the generator hash, because a change here
changes tasks.  `tests/test_k1_surface.py` says what each name does.

`display_map` and `fault_plan` take the tools as an argument and never read the built-in
block themselves, so a block of a caller's own tools goes through them unchanged.
"""

from __future__ import annotations

import hashlib as _hashlib
from collections.abc import Sequence as _Sequence
from dataclasses import dataclass as _dataclass
from typing import Any as _Any

from poisson_tasks.engine import EngineSpec as _EngineSpec
from poisson_tasks.knobs import _FAULTS, _SPREAD, _parse_arm_id, _split_evenly

_SPEC = _EngineSpec.load()

# The key of the keyed draw.  The spelling is deliberately not the package's: these bytes are
# hash input, so respelling them moves every seed-derived choice of every task.
_DRAW_KEY = b"task-generator/structure-draw/1"

# A name no engine knows.  A call to a name the block does not show is replayed as this, so it
# is answered as no tool and changes nothing, as the harness answers it without the server.
_NO_TOOL = ""

# What the first stage tool's description says of the entry code, and what it says on a spread
# arm, where the request does not state the code and four reads hold its parts.
_CODE_STATED = "stated in the request"
_CODE_ASSEMBLED = "assembled from the reads named in the request"


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


def display_map(
    seed: int, split: str, arm_id: str, goal: _Sequence[_Any], tools: _Sequence[str]
) -> dict[str, Shown]:
    """Each of `tools`, the names a block shows, mapped to what it stands for, in block order.

    Every knob built so far shows the engine's own names.  The spread knob changes one
    description: the target ledger's first stage tool says its entry code is stated in the
    request, which is false where the request names four reads instead, so there it says the
    code is assembled from them, the same at every level.  `seed` and `split` are what a
    knob that draws its shown names draws them from; no knob built so far draws any.
    """
    knob = _parse_arm_id(arm_id).knob
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
