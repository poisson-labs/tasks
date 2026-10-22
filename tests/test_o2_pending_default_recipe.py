"""Pending a decision: the default recipe on a user's own tools.

**Why it is open.**  The design offers the recipes that apply to the set "with `tool-choice` as the
default".  `tool-choice` needs similarity or block to have shipped, and it was decided
2026-10-13 that this must hold whatever `arms.SHIPPED_KNOBS` holds (empty today).

**Recommended.**  `tool-choice` when it is offered on the set, else the first offered recipe in the
table's order, else none (`own.recipes.default_recipe`).  If it is declined, the build has no
default when `tool-choice` is not offered, so `init` asks with no answer pre-selected.
"""

from __future__ import annotations

import pytest

from tests.o2_support import acme, acme_flows, recipes

SHIPPABLE = ("similarity", "faults", "history", "block", "arguments", "shape", "spread")


@pytest.mark.parametrize("shipped", [(), ("faults",), ("block",), ("similarity",), SHIPPABLE],
                         ids=["none", "faults", "block", "similarity", "all"])
def test_the_default_is_tool_choice_when_offered_else_the_first_offered(shipped: tuple[str, ...]) -> None:
    rec = recipes()
    for flows in ((), acme_flows()):
        table = rec.recipes_for(acme(), flows=flows, shipped=shipped)
        offered = [name for name, recipe in table.items() if recipe.offered]
        expected = "tool-choice" if "tool-choice" in offered else (offered[0] if offered else None)
        assert rec.default_recipe(acme(), flows=flows, shipped=shipped) == expected
