"""The simulator: what a user's tools answer in a Tasks episode, shaped by their schemas, and the
state a task's calls move (spec §4).

Names only: each body is the build's.  `tests/test_o2_simulator.py` says what each name does.  It
is pure: no clock but a fixed one, no randomness but a draw keyed on the call, no network.
"""

from __future__ import annotations

from collections.abc import Mapping as _Mapping
from collections.abc import Sequence as _Sequence
from dataclasses import dataclass as _dataclass
from typing import Any as _Any

from poisson_tasks.own._types import OwnTool as _OwnTool

__all__ = [
    "CLOCK",
    "ERROR_CODES",
    "OUTPUT_PASSED_OVER",
    "Answer",
    "State",
    "respond",
    "success",
    "error",
    "start",
    "step",
    "replay",
]

CLOCK = "2026-01-01T00:00:00Z"
ERROR_CODES = ("not_found", "invalid_arguments", "not_ready", "unavailable")
OUTPUT_PASSED_OVER: tuple[str, ...] = ()


@_dataclass(frozen=True)
class Answer:
    """One answer: the tool message's text, the MCP result's `structuredContent` or `None`, and
    the MCP result's `isError`."""

    text: str
    structured: _Mapping[str, _Any] | None
    is_error: bool


@_dataclass(frozen=True)
class State:
    """The store a task's calls move: one flag per write the task expects, the accepted writes it
    did not expect, and every call the server received."""

    done: tuple[bool, ...]
    side_effects: tuple[_Any, ...]
    calls: int


def respond(tool: _OwnTool, arguments: _Mapping[str, _Any], *, digest: str, seed: int,
            split: str) -> _Any:
    """The object an accepted call to `tool` answers with, drawn from the call's content."""
    raise NotImplementedError("the simulator is not built yet")


def success(source_format: str, tool: _OwnTool, value: _Any) -> Answer:
    """An accepted call's answer in the format's idiom."""
    raise NotImplementedError("the simulator is not built yet")


def error(source_format: str, code: str, message: str) -> Answer:
    """An error in the format's idiom; `code` is one of `ERROR_CODES`."""
    raise NotImplementedError("the simulator is not built yet")


def start(task: _Any) -> State:
    """The store before a task's first call."""
    raise NotImplementedError("the simulator is not built yet")


def step(task: _Any, state: State, call: tuple[str, _Any]) -> tuple[State, Answer]:
    """One call that reached the server, answered, and the store after it."""
    raise NotImplementedError("the simulator is not built yet")


def replay(task: _Any, calls: _Sequence[tuple[str, _Any]]) -> tuple[State, tuple[Answer, ...]]:
    """The calls that reach the server, in order, from the task's start."""
    raise NotImplementedError("the simulator is not built yet")
