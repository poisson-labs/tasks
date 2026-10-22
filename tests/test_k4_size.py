"""The history knob's size: the seeded pairs total the level, frozen as tests.

It rests on the pin ledger's N23.  A history arm is B
with read pairs seeded after the user's instruction, as the depth controls seed them; the pairs'
reference tokens (tool name, compact arguments, observation: N9's unit) total the level T; the
count is `round(T / m)`, with `m` the median reachable read-pair total in the block, and the
search then moves single pairs until the total is T; `seq_start` is the pairs plus one.  T = 0
seeds nothing and leaves the prompt a string, which `tests/test_k4_kind.py` pins by holding
`history:t0` equal to B.

Shapes decided here
-------------------

**1. The total is pinned exactly, not within N23's +/- 2.**  The read pair's reachable totals
are consecutive, so a search that converges lands on T; a total off by one or two is a search
that stuck or stopped early, which the design ("the search never exhausts its steps at any card
level") rules out.  Measured on the reference: residual 0 at every card seed on both splits at every
level, as the code audit found over ten seeds.  The ledger's band is the contrast's tolerance,
not the generator's target.

**2. `m` is the median at the first seeded position.**  An observation carries its `seq`, so
each position has its own reachable totals; at B's block they share one median (57 reference
tokens at every position), so the choice is stated and does not matter.  The test computes it
from the engine, over every read in the block, every catalogue item and every page answered
`ok`, and never from a literal.  The counts that follow are 5, 11, 21 and 42.

**3. The bound on time** is ten times the reference's measurement: the sixty card seeds at
`history:t2400` generated afresh in about 55 seconds on the reference machine, so the budget is
600 seconds, checked after every seed so a slow build fails as soon as the budget is spent and
not after an hour.  It catches a search that recomputes the read-pair table at every step, not a
loaded machine.
"""

from __future__ import annotations

import time

import pytest

from poisson_tasks.arms import arm_from_id
from poisson_tasks.tasks import generate
from tests.k4_support import (
    CARD_SEEDS,
    LEVELS,
    SPLITS,
    arm,
    history,
    median_pair_total,
    seeded,
    seeded_tokens,
)

TIME_BUDGET_SECONDS = 600.0


@pytest.mark.parametrize("level", LEVELS[1:])
def test_the_seeded_pairs_total_the_level_exactly_from_round_t_over_m(level: int) -> None:
    """At every card seed on the eval split and twelve on train: `round(T / m)` pairs,
    whose tokens total T exactly; `seq_start` the pairs plus one; the ledger's N23 reads the
    same total."""
    for split, seeds in SPLITS:
        for seed in seeds:
            bundle = history(level, seed, split)
            pairs = seeded(bundle)
            assert len(pairs) == round(level / median_pair_total(bundle)), (split, seed, len(pairs))
            assert seeded_tokens(bundle) == level, (split, seed, seeded_tokens(bundle))
            assert bundle.pins.values["N23"] == level
            assert bundle.seq_start == len(pairs) + 1


def test_the_top_level_generates_for_the_sixty_card_seeds_in_bounded_time() -> None:
    """`history:t2400` afresh at every card seed, the search converging every time (shape
    1), within the stated budget (shape 3)."""
    spec = arm_from_id(arm(2400))
    start = time.perf_counter()
    for seed in CARD_SEEDS:
        bundle = generate(spec, seed)
        assert seeded_tokens(bundle) == 2400, seed
        assert time.perf_counter() - start <= TIME_BUDGET_SECONDS, seed
