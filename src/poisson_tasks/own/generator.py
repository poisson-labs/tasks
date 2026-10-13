"""The own-tools generator: tasks on a user's own tools, the knobs applied to them (spec §5 to §7).

Names only: each body is the build's.  `tests/test_o2_*.py` say what each name does.  Its version
label is `own-1` and its hash covers this module's bytes and every module of the package it
imports, the shared `surface.py` and `knobs.py` among them; it never changes a built-in task.
"""

from __future__ import annotations

from collections.abc import Mapping as _Mapping
from collections.abc import Sequence as _Sequence
from dataclasses import dataclass as _dataclass
from typing import Any as _Any

__all__ = [
    "GENERATOR_VERSION",
    "KNOBS",
    "HASHED_MODULES",
    "UNAVAILABLE_WITHOUT_FLOWS",
    "Flow",
    "OwnBundle",
    "generator_hash",
    "hash_of",
    "check_flows",
    "knob_levels",
    "pair_tokens",
    "generate",
]

GENERATOR_VERSION = "own-1"
KNOBS = ("similarity", "faults", "history", "block", "arguments", "spread", "depth", "shape")
HASHED_MODULES: tuple[str, ...] = ()
UNAVAILABLE_WITHOUT_FLOWS = (
    "Depth and shape need the model to carry a value from one tool's output into another's "
    "input in a way that makes sense for your domain. Tasks will not guess that."
)


@_dataclass(frozen=True)
class Flow:
    """One declared link: the `from_tool`'s output at `field` goes into the `to_tool`'s `param`."""

    from_tool: str
    field: str
    to_tool: str
    param: str


@_dataclass(frozen=True)
class OwnBundle:
    """One task on a user's own tools.  The build may add fields that carry what the simulator and
    the verdict need; these are the ones the tests read."""

    task_id: str
    arm_id: str
    seed: int
    split: str
    strictness: str
    set_name: str
    source_format: str
    file_digest: str
    generator_hash: str
    form: str
    system_prompt: str
    request: str
    prompt: str | tuple[dict[str, _Any], ...]
    tools: tuple[dict[str, _Any], ...]
    target: str
    target_tool: str
    stated: tuple[tuple[str, _Any], ...]
    named_reads: tuple[tuple[str, _Any, str], ...]
    fault_plan: _Mapping[str, int]
    reference_calls: tuple[tuple[str, _Any], ...]
    reference_observations: tuple[str, ...]
    negative_controls: _Mapping[str, tuple[tuple[str, _Any], ...]]


def generator_hash() -> str:
    """The own-tools generator's hash: `hash_of` the bytes of `HASHED_MODULES`."""
    raise NotImplementedError("the own-tools generator is not built yet")


def hash_of(sources: _Mapping[str, bytes]) -> str:
    """The hash of a mapping from module name to the module's bytes."""
    raise NotImplementedError("the own-tools generator is not built yet")


def check_flows(toolset: _Any, flows: _Sequence[Flow]) -> None:
    """Refuse, in one line, a flow that names no tool of the set, no path in the from-tool's
    output or no argument of the to-tool."""
    raise NotImplementedError("the own-tools generator is not built yet")


def knob_levels(toolset: _Any, knob: str, *, flows: _Sequence[Flow] = ()) -> tuple[int, ...]:
    """The levels of `knob` this set reaches; empty where it reaches none."""
    raise NotImplementedError("the own-tools generator is not built yet")


def pair_tokens(name: str, arguments: _Any, observation: str) -> int:
    """A seeded read pair's tokens, counted as the built-in history knob counts them."""
    raise NotImplementedError("the own-tools generator is not built yet")


def generate(
    toolset: _Any,
    arm: _Any,
    seed: int,
    *,
    intents: _Mapping[str, str] | None = None,
    flows: _Sequence[Flow] = (),
) -> OwnBundle:
    """The task on `toolset` for `arm` (a `knobs.ArmSpec` at generator `own-1`) and `seed`."""
    raise NotImplementedError("the own-tools generator is not built yet")
