"""What is offered on a user's own tools: the knobs that shipped and that the set reaches, and the
recipes made of them (spec §6.3, §8.1; knobs spec §17.4).

Names only: each body is the build's.  `tests/test_o2_knobs.py` says what each name does.  The
knobs a probe shipped are read from `arms.SHIPPED_KNOBS` when the caller gives none.
"""

from __future__ import annotations

from collections.abc import Mapping as _Mapping
from collections.abc import Sequence as _Sequence
from typing import Any as _Any

__all__ = ["offered_knobs", "recipes_for", "default_recipe"]


def offered_knobs(toolset: _Any, *, flows: _Sequence[_Any] = (),
                  shipped: _Sequence[str] | None = None) -> tuple[str, ...]:
    """The knobs offered on this set: depth, and each knob that shipped, that it reaches."""
    raise NotImplementedError("the own-tools offer is not built yet")


def recipes_for(toolset: _Any, *, flows: _Sequence[_Any] = (),
                shipped: _Sequence[str] | None = None) -> _Mapping[str, _Any]:
    """Every recipe, as `arms.Recipe`, with the arms it runs on this set."""
    raise NotImplementedError("the own-tools offer is not built yet")


def default_recipe(toolset: _Any, *, flows: _Sequence[_Any] = (),
                   shipped: _Sequence[str] | None = None) -> str | None:
    """The recipe `init` offers first on this set, or `None` when none is offered."""
    raise NotImplementedError("the own-tools offer is not built yet")
