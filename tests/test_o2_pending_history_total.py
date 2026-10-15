"""Pending a yes/no: history on a user's own tools seeds the fewest pairs that reach T tokens.

**Why it is open.**  Spec §6.1: "seeded calls to your read tools, with simulated answers, totalling T
reference tokens".  The built-in knob reaches T exactly, by a search over its table's reads.  A user's
reads answer what the simulator draws, so an exact total is not reachable in general.

**Recommendation: yes.**  The fewest seeded pairs whose total reaches T: the total is at least T, and
without its last pair it is below T.  A no searches the drawn arguments for a total of exactly T and
refuses a level it cannot reach.
"""

from __future__ import annotations

import json

import pytest

from tests.o2_support import acme, fixture_sets, generator, make


@pytest.mark.parametrize("level", [300, 600, 1200, 2400])
def test_the_total_is_the_first_to_reach_the_level(level: int) -> None:
    for toolset in (acme(), fixture_sets()["petstore"]):
        for seed in range(8):
            bundle = make(toolset, "history", level, seed=seed)
            pairs = list(zip(bundle.prompt[1::2], bundle.prompt[2::2], strict=True))
            counts = []
            for call, result in pairs:
                (made,) = call["tool_calls"]
                counts.append(generator().pair_tokens(made["function"]["name"],
                                                      json.loads(made["function"]["arguments"]),
                                                      result["content"]))
            assert sum(counts) >= level > sum(counts[:-1])
