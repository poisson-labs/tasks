"""What is offered on a user's own tools: the knobs that shipped and that the set reaches, and the
recipes made of them (spec §6.3, §8.1; knobs spec §17.4).

A knob is offered on a set when the set reaches a level of it and either it is depth, which the
published cards measured and needs no probe, or the probe shipped it: the knobs a probe shipped
are read from `arms.SHIPPED_KNOBS` at call time when the caller gives none, whatever it holds
(ruled 2026-10-13).  A recipe is offered when one of its knobs is offered on the set, and runs
the arms of those knobs only, each knob's levels chosen as the built-in recipe chooses them
(every level, the first and last, or the first, middle and last) over the levels this set
reaches (yes/no 18); `card`, the published design, is never offered on own tools (yes/no 19).
The default recipe is `tool-choice` when it is offered, else the first offered in the table's
order, else none (yes/no 20).  `tests/test_o2_knobs.py` pins this.
"""

from __future__ import annotations

import types as _types
from collections.abc import Mapping as _Mapping
from collections.abc import Sequence as _Sequence
from typing import Any as _Any

from poisson_tasks import arms as _arms
from poisson_tasks import knobs as _knobs
from poisson_tasks.own import generator as _generator

__all__ = ["offered_knobs", "recipes_for", "default_recipe"]

_DEPTH = "depth"
_CARD = "card"
_DEFAULT = "tool-choice"
_PROBE_KNOBS = ("similarity", "faults", "history", "block", "arguments", "shape", "spread")


def _shipped(shipped: _Sequence[str] | None) -> tuple[str, ...]:
    return tuple(_arms.SHIPPED_KNOBS if shipped is None else shipped)


def offered_knobs(toolset: _Any, *, flows: _Sequence[_Any] = (),
                  shipped: _Sequence[str] | None = None) -> tuple[str, ...]:
    """The knobs offered on this set: depth, and each knob that shipped, that it reaches."""
    chosen = _shipped(shipped)
    return tuple(
        knob for knob in _generator.KNOBS
        if (knob == _DEPTH or knob in chosen)
        and _generator.knob_levels(toolset, knob, flows=flows)
    )


def _how(recipe: _arms.Recipe, knob: str) -> str:
    """How the built-in recipe chooses the knob's levels, read off its full design: `every`,
    `ends` or `three`."""
    axis = _knobs.levels(knob)
    chosen = [axis.index(_arms.arm_from_id(arm).level) for arm in recipe.arms
              if _arms.arm_from_id(arm).knob == knob]
    every = list(range(len(axis)))
    if chosen == every:
        return "every"
    if chosen == [0, every[-1]]:
        return "ends"
    return "three"


def _chosen(found: _Sequence[int], how: str) -> list[int]:
    if how == "every":
        return list(found)
    if how == "ends":
        return list(dict.fromkeys((found[0], found[-1])))
    return list(dict.fromkeys((found[0], found[len(found) // 2], found[-1])))


def recipes_for(toolset: _Any, *, flows: _Sequence[_Any] = (),
                shipped: _Sequence[str] | None = None) -> _Mapping[str, _Any]:
    """Every recipe, as `arms.Recipe`, with the arms it runs on this set."""
    chosen = _shipped(shipped)
    offered = offered_knobs(toolset, flows=flows, shipped=chosen)
    full = _arms.recipe_table(_PROBE_KNOBS)
    table: dict[str, _arms.Recipe] = {}
    for name, design in full.items():
        waiting = tuple(knob for knob in design.knobs if knob != _DEPTH and knob not in chosen)
        if name == _CARD:
            table[name] = _arms.Recipe(
                name=name, asks=design.asks, knobs=design.knobs, arms=(),
                tasks_per_level=design.tasks_per_level, attempts=design.attempts,
                offered=False, waiting=waiting,
            )
            continue
        mine = [knob for knob in design.knobs if knob in offered]
        arm_ids: list[str] = []
        for knob in mine:
            found = _generator.knob_levels(toolset, knob, flows=flows)
            arm_ids += [
                _knobs.arm_id(_knobs.ArmSpec(knob=knob, level=level, control=None,
                                             strictness="strict", split="eval",
                                             generator_version=_generator.GENERATOR_VERSION))
                for level in _chosen(found, _how(design, knob))
            ]
        table[name] = _arms.Recipe(
            name=name, asks=design.asks, knobs=design.knobs, arms=tuple(arm_ids),
            tasks_per_level=design.tasks_per_level, attempts=design.attempts,
            offered=bool(mine), waiting=waiting,
        )
    return _types.MappingProxyType(table)


def default_recipe(toolset: _Any, *, flows: _Sequence[_Any] = (),
                   shipped: _Sequence[str] | None = None) -> str | None:
    """The recipe `init` offers first on this set, or `None` when none is offered."""
    table = recipes_for(toolset, flows=flows, shipped=shipped)
    offered = [name for name, recipe in table.items() if recipe.offered]
    if _DEFAULT in offered:
        return _DEFAULT
    return offered[0] if offered else None
