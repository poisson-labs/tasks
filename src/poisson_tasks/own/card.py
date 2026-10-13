"""The card on a user's own tools: its first lines, beside a published card, and each level
against the first (spec §6.3, §9).

Names only: each body is the build's.  `tests/test_o2_card.py` says what each name does.
"""

from __future__ import annotations

from collections.abc import Mapping as _Mapping
from collections.abc import Sequence as _Sequence
from dataclasses import dataclass as _dataclass
from typing import Any as _Any

__all__ = [
    "DIFFERENT_TASKS",
    "first_lines",
    "beside_published",
    "AgainstFirst",
    "against_first",
    "bite",
    "near_duplicates",
]

DIFFERENT_TASKS = "different tasks: read each card on its own"


@_dataclass(frozen=True)
class AgainstFirst:
    """One level of a knob read against the knob's first level."""

    knob: str
    level: int
    first: int
    predicate: str
    delta: float | None
    low: float | None
    high: float | None
    verdict: str


def first_lines(tools: _Mapping[str, _Any]) -> str:
    """Spec §9's first lines, from the own-tools provenance kind."""
    raise NotImplementedError("the own-tools card is not built yet")


def beside_published(own: _Any, published: _Any) -> str:
    """The own card and the published card of its model, each on its own."""
    raise NotImplementedError("the own-tools card is not built yet")


def against_first(
    cells: _Mapping[tuple[str, str], _Sequence[_Any]], provenance: _Any
) -> tuple[AgainstFirst, ...]:
    """Each knob's levels against its first level."""
    raise NotImplementedError("the own-tools card is not built yet")


def bite(rows: _Sequence[AgainstFirst]) -> dict[str, str]:
    """Per knob, whether it made the tasks harder, in one line."""
    raise NotImplementedError("the own-tools card is not built yet")


def near_duplicates(toolset: _Any) -> dict[str, _Any]:
    """The set's own closest pairs by name and by description."""
    raise NotImplementedError("the own-tools card is not built yet")
