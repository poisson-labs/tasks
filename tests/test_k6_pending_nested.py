"""Pending a yes/no: a level states the values of the level below it and more.

**This file waits on a yes/no** and is its own commit, so a "no" drops it whole.

Spec §14.2 says the request states `A - 2` of the six values, and plan K6.2 that the values are
opaque words drawn from `(seed, split)`; neither says which of the six a level states.  The frozen
`tests/test_k6_stated.py` holds the values a level states to be among the six a8 states.
Recommended: one order of the six, read as far as the level goes, so each level states what the
level below states, each parameter with the same value, and more (`a3` within `a4` within `a5` and so on up to `a8`), and a level adds
values and changes none it already stated: the factor moves and nothing else does, as each block
level is the start of the next (K5).  Not chosen: a drawn subset per level, under which `a4` and
`a6` of one task could ask for different parameters and a drop between them would mix the count
with which fields are asked for.  If the answer is no, which values a level states is the build's,
and this file is dropped.
"""

from __future__ import annotations

from tests.k3_support import made
from tests.k6_support import SPLITS, arm, stated

CHAIN = (2, 3, 4, 5, 6, 7, 8)


def test_each_level_states_what_the_level_below_states_and_more() -> None:
    for split, seeds in SPLITS:
        for seed in seeds:
            below: dict[str, str] = {}
            for level in CHAIN:
                values = stated(made(arm(level), seed, split))
                assert len(values) == level - 2, (level, seed, split)
                assert below.items() <= values.items(), (level, seed, split, below, values)
                below = values
