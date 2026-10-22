"""The similarity knob's census, exactly: pending a decision.

**This file waits on a decision** and is its own commit, so if it is declined it is dropped whole.

The design says `structure_space(similarity:sS)` "counts the target class, the slot permutation,
the six lookalike ledgers and the kept positions; the numbers themselves are masked".  But G16's
count is the number of structures the fingerprint can tell apart (`test_g16_1` holds it equal to a
brute-force count of distinct fingerprints), and once the numbers are masked and the seven tools of
a stage are identical but for their number, two things on that list cannot be told apart:
- which ledger a lookalike is (it shows only its masked number), and
- the order of the twelve reads B held where the lookalikes now sit (they are gone).
Counting them would overstate `k` by a factor of 12! (the swapped reads' order) times 11!/5! (six
lookalike ledgers drawn in order from eleven), about 1.6 x 10^14, which is the direction G16's floor
must never err in.

So, recommended: the count is what the fingerprint keeps (`tests/test_k2_fingerprint.py`, shape 1;
`tests/test_k2_block.py`, shape 2): the target class (12), the right tools' two slots and the two
reads that stay, which take the first two of the remaining slots (16 * 15 * 14 * 13 = 43,680), and
the places each of the six lookalike ledgers shares with the target (C(4, S) each):

    k(S) = 12 * 43,680 * C(4, S)**6

which is 524,160 at s0 and s1's 2,146,959,360, s2's 24,455,208,960 and s3's 2,146,959,360.  Each
clears the floor of 360,000 at N = 60 (`test_k2_fingerprint.py` pins the floor whichever way this is
decided).  It cannot be brute-forced as `test_g16_1` does, since no reduced vocabulary holds seven
ledgers and a sixteen-tool block, so it is stated.
"""

from __future__ import annotations

from math import comb

import pytest

from poisson_tasks.arms import arm_from_id
from poisson_tasks.engine import EngineSpec
from poisson_tasks.tasks import structure_space

SPEC = EngineSpec.load()


@pytest.mark.parametrize(("level", "k"), [
    (0, 524_160), (1, 2_146_959_360), (2, 24_455_208_960), (3, 2_146_959_360),
])
def test_each_level_counts_the_structures_its_fingerprint_can_tell_apart(level: int, k: int) -> None:
    assert len(SPEC.qualifiers) * 16 * 15 * 14 * 13 * comb(4, level) ** 6 == k
    assert structure_space(arm_from_id(f"similarity:s{level}")) == k
