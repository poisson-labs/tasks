"""Pending a yes/no: the census of a task-shape arm, and the goal lines masked in the fingerprint.

**This file waits on a yes/no** and is its own commit, so a "no" drops it whole.

`structure_space` must take every arm `eval` takes (the frozen `tests/test_k7_eval.py` holds it to),
and spec §14.3 does not say what it counts for task shape.  The goal lines name record ids, which
G15's fingerprint masks, beside ledgers and stages, which the block, the goal and the target list
(spec §14.3; the frozen `tests/test_k7_verdict.py`) already show.  Recommended: the fingerprint
masks the knob's own slot, `goal_lines`, whole, as it masks the argument knob's stated values
(ruled 2026-10-08), so nothing in it is structure twice and no record id is structure at all.  Then
the count is B's (the target ledger times the order of sixteen distinct tools) at `w1` and `w2`,
whose blocks hold one ledger's tools, and on the control (a lower bound, as for every control); and
at `w4` B's times the choice of the three other ledgers among the eleven (165), each set of four
first-stage tools taking every order of the sixteen slots.  If the answer is no, the count and
whether the fingerprint reads the goal lines are the build's, and this file is dropped.
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from poisson_tasks.arms import arm_from_id
from poisson_tasks.tasks import structural_fingerprint, structure_space
from tests.k3_support import B_ARM, CARD_SEEDS, SPEC
from tests.k7_support import ARMS, SLOT, shape

OTHERS = math.comb(len(SPEC.qualifiers) - 1, 3)


@pytest.mark.parametrize("text", ARMS)
def test_the_census_of_a_shape_arm_is_bs_and_w4_chooses_three_more_ledgers(text: str) -> None:
    times = OTHERS if text == "shape:w4" else 1
    assert structure_space(arm_from_id(text)) == structure_space(arm_from_id(B_ARM)) * times


def test_the_fingerprint_masks_the_goal_lines_whole() -> None:
    """The record ids in them are masked in any case (the frozen `tests/test_k7_verdict.py`); this
    is the rest of the slot: replaced by anything, the fingerprint does not move."""
    for seed in CARD_SEEDS[:12]:
        for width in (1, 2, 4):
            bundle = shape(width, seed)
            moved = tuple(
                (name, "x" if name == SLOT else held) for name, held in bundle.prompt_slots
            )
            other = dataclasses.replace(bundle, prompt_slots=moved)
            assert structural_fingerprint(other) == structural_fingerprint(bundle), (width, seed)
