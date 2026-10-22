"""Pending a decision: which of a set's levels a recipe runs on own tools.

**Why it is open.**  A built-in recipe takes, for each of its knobs, every level, the first and last,
or the first, middle and last of the knob's card levels.  On own tools a knob's
levels are those the set reaches (block to the set's size, arguments to the target's counts, depth to
the longest chain), and the design does not say how a recipe maps onto them.

**Recommended.**  The same choice made over the levels this set reaches: `first-look` on a
chain of three runs depth 1, 2 and 3; `tool-choice` on a set of twenty runs block 8 and 16.  A no
takes the recipe's card levels that the set reaches (first-look on a chain of three would then run
depth 1 and 3 only).
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from poisson_tasks import arms as arms_module
from poisson_tasks import knobs
from tests.o2_support import arm, fixture_sets, flows_for, generator, recipes

SHIPPABLE = ("similarity", "faults", "history", "block", "arguments", "shape", "spread")


def which(name: str, knob: str) -> str:
    """How the built-in recipe chooses a knob's levels, read off its full design."""
    full = arms_module.recipe_table(SHIPPABLE)[name]
    chosen = [knobs.levels(knob).index(arms_module.arm_from_id(a).level)
              for a in full.arms if a.startswith(knob + ":")]
    every = list(range(len(knobs.levels(knob))))
    if chosen == every:
        return "every"
    if chosen == [0, every[-1]]:
        return "ends"
    assert chosen == [0, len(every) // 2, every[-1]], (name, knob, chosen)
    return "three"


def chosen(found: Sequence[int], how: str) -> list[int]:
    if how == "every":
        return list(found)
    if how == "ends":
        return list(dict.fromkeys((found[0], found[-1])))
    return list(dict.fromkeys((found[0], found[len(found) // 2], found[-1])))


@pytest.mark.parametrize("label", ["acme-mcp", "acme-openai", "petstore"])
def test_a_recipes_choice_is_made_over_the_levels_the_set_reaches(label: str) -> None:
    toolset, flows = fixture_sets()[label], flows_for(label)
    table = recipes().recipes_for(toolset, flows=flows, shipped=SHIPPABLE)
    built_in = arms_module.recipe_table(SHIPPABLE)
    for name, recipe in table.items():
        if name == "card":
            continue
        design = []
        for knob in built_in[name].knobs:
            found = generator().knob_levels(toolset, knob, flows=flows)
            if found:
                design += [knobs.arm_id(arm(knob, level)) for level in chosen(found, which(name, knob))]
        assert list(recipe.arms) == design, name
