"""Pending a yes/no: on a user's own tools a knob's levels are its card levels.

**Why it is open.**  Spec §6.1 bounds block's levels by the set's size, arguments' by the target's
counts and depth's by the longest chain; for similarity, faults, history and spread it gives no
levels of its own.  The built-in `eval` takes any level between a knob's card ends (`faults:f3`,
`history:t900`, `spread:p3`) with a note that no card measured it.

**Recommendation: yes.**  Similarity, faults, history and spread take their card levels
(`knobs.levels`), and a level between them is refused on own tools in one line: an own-tools card is
read level against first level within itself (spec §6.3), and its recipes choose among card levels.
A no takes any buildable level, as the built-in `eval` does.
"""

from __future__ import annotations

import pytest

from poisson_tasks import knobs
from tests.o2_support import acme, arm, generator


@pytest.mark.parametrize("knob, between", [("faults", 3), ("history", 900), ("spread", 3)])
def test_a_level_between_two_card_levels_is_refused_on_own_tools(knob: str, between: int) -> None:
    assert generator().knob_levels(acme(), knob) == knobs.levels(knob)
    with pytest.raises(ValueError):
        generator().generate(acme(), arm(knob, between), 1)
