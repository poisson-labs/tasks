"""Pending a decision: the census of an arguments arm is B's, and the stated values are masked.

**This file waits on a decision** and is its own commit, so if it is declined it is dropped whole.

`structure_space` must take every arm `eval` takes (the frozen `tests/test_k6_eval.py` holds it to),
and the design does not say what it counts for argument difficulty.  Recommended: B's count, the
target ledger times the order of B's sixteen slots, at every level and the control.  An arguments
arm's block is B's at every level, its schema the same at every level (`tests/test_k6_schema.py`),
and which parameters a level states is the level's.  The stated values are opaque words the model
copies, as the record id and the entry code are, so G15's fingerprint masks them as it masks those
two: the build adds the knob's own slot, `stated_values`, to the slots the fingerprint masks.  Then
nothing a level or a seed can vary beyond B's is structure, and B's count is what the arm can make
(for the control a lower bound, as for every control).  If the answer is no, the count and the
fingerprint's reading of the stated values are the build's, and this file is dropped.
"""

from __future__ import annotations

import dataclasses

import pytest

from poisson_tasks.arms import arm_from_id
from poisson_tasks.tasks import structural_fingerprint, structure_space
from tests.k3_support import B_ARM, CARD_SEEDS
from tests.k6_support import ARMS, OFF_CARD_LEVELS, SLOT, arguments, arm, stated


@pytest.mark.parametrize("text", ARMS + tuple(arm(level) for level in OFF_CARD_LEVELS))
def test_the_census_of_an_arguments_arm_is_bs(text: str) -> None:
    assert structure_space(arm_from_id(text)) == structure_space(arm_from_id(B_ARM))


def test_the_fingerprint_masks_the_stated_values() -> None:
    for seed in CARD_SEEDS[:12]:
        bundle = arguments(8, seed)
        slots = dict(bundle.prompt_slots)
        text = slots[SLOT]
        for value in stated(bundle).values():
            text = text.replace(value, value[::-1] + "x")
        assert text != slots[SLOT], seed
        moved = tuple((name, text if name == SLOT else held) for name, held in bundle.prompt_slots)
        other = dataclasses.replace(bundle, prompt_slots=moved)
        assert structural_fingerprint(other) == structural_fingerprint(bundle), seed
