"""Pending a decision: a task-shape block is B's, its stage tools in the same four slots at every
width.

**This file waits on a decision** and is its own commit, so if it is declined it is dropped whole.

The design says the block holds exactly the stage tools the width needs, with reads to sixteen, and
that its composition moves with the width; the frozen `tests/test_k7_block.py` holds that, and the
ledger's N2 holds the target ledger's stage tools that two widths share to one slot.  It does not
say which reads, or where.  Recommended: as little moves as the width needs.  `w2` needs exactly
B's stage tools, so its block is B's.  At `w1` and `w4` every read is one of B's, in B's slot for
it, and the width's stage tools take four slots that are the same at both: B's two stage slots and
the slots of the same two of B's reads, which give way.  So between any two widths only stage
tools change places with stage tools or with those two reads, and the twelve reads every width
holds never move.  If the answer is no, which reads give way and where the stage tools sit (N2
apart) are the build's, and this file is dropped.
"""

from __future__ import annotations

from tests.k3_support import SPEC
from tests.k7_support import SPLITS, base, names, shape


def test_w2s_block_is_bs_and_the_reads_keep_bs_slots_at_every_width() -> None:
    for split, seeds in SPLITS:
        for seed in seeds:
            b = base(seed, split)
            assert shape(2, seed, split).tools == b.tools, (seed, split)
            b_names = names(b)
            stage_slots = set()
            for width in (1, 4):
                shown = names(shape(width, seed, split))
                for slot, name in enumerate(shown):
                    if name in SPEC.read_tools:
                        assert b_names[slot] == name, (width, slot, seed, split)
                stage_slots.add(
                    frozenset(slot for slot, name in enumerate(shown) if name in SPEC.stage_tools)
                )
            assert len(stage_slots) == 1, (seed, split)
