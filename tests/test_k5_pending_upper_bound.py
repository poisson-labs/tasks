"""Pending a yes/no: the largest block the generator can build, and the refusal above it.

**This file waits on a yes/no** and is its own commit, so a "no" drops it whole.

Spec §3.2 (ruled 2026-10-04): a level the generator cannot build is refused when the arm is made,
not noted, and for block size that is a level below eight; "the block's upper bound is left to
K5".  Plan K5 names none.  The most a block can offer is the target ledger's two stage tools and
every `{verb}_{facet}` the table's sixteen read verbs and sixteen facets make, its own sixteen reads
among them: 258 tools.  Recommended: that is the bound.  `block:k258` generates, holding all 256
read names once, and `block:k259` is refused when the arm is made, by `ArmSpec` and so by
`arms.arm_from_id`, as `block:k7` is (the frozen `tests/test_k1_pending_level_bounds.py` takes 256).
`eval` takes 8 to 64, the ends of the candidate levels, whichever way this is ruled.

Not chosen: a bound at a provider's limit on tools per request (128 at OpenAI's chat completions
API), which is a property of where a task is run and differs by provider, not of the task.  If the
answer is no, a block above 258 is refused only when its tasks are generated, by whatever the
build raises there, and this file is dropped.
"""

from __future__ import annotations

import pytest

from poisson_tasks.arms import arm_from_id
from poisson_tasks.knobs import ArmSpec
from poisson_tasks.tasks import generate
from tests.k3_support import names
from tests.k5_support import FACETS, VERBS

TOP = 2 + len(VERBS) * len(FACETS)


def test_a_block_level_past_what_the_table_can_name_is_refused_when_the_arm_is_made() -> None:
    top = generate(arm_from_id(f"block:k{TOP}"), 404)
    shown = names(top)
    reads = {f"{verb}_{facet}" for verb in VERBS for facet in FACETS}
    assert len(set(shown)) == TOP == len(shown)
    assert reads <= set(shown) and len(set(shown) - reads) == 2
    with pytest.raises(ValueError):
        ArmSpec(
            knob="block",
            level=TOP + 1,
            control=None,
            strictness="strict",
            split="eval",
            generator_version="1",
        )
    with pytest.raises(ValueError):
        arm_from_id(f"block:k{TOP + 1}")
