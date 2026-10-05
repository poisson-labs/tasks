"""What the model sees of a task, and what is applied in front of the engine.

Private.  Names only: each body is the build's (`tests/test_k1_surface.py` says what each does).
"""

from __future__ import annotations

from collections.abc import Sequence as _Sequence
from dataclasses import dataclass as _dataclass
from typing import Any as _Any


def _prf(domain: bytes, seed: int, split: str) -> bytes:
    """The keyed draw every seed-derived choice uses, moved here from `tasks.py`."""
    raise NotImplementedError


@_dataclass(frozen=True)
class Shown:
    """One tool as a block shows it: the engine's name for it, and the description the block
    gives it when that is not the engine's own (`None` when it is)."""

    engine: str
    description: str | None


def display_map(
    seed: int, split: str, arm_id: str, goal: _Sequence[_Any], tools: _Sequence[str]
) -> dict[str, Shown]:
    """Each of `tools`, the names a block shows, mapped to what it stands for, in block order."""
    raise NotImplementedError


def fault_plan(arm_id: str, path: _Sequence[str]) -> dict[str, int]:
    """How many times each tool on the reference path answers `unavailable` before it works."""
    raise NotImplementedError
