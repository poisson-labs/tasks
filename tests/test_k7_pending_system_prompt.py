"""Pending a decision: a task-shape arm's system prompt is B's.

**This file waits on a decision** and is its own commit, so if it is declined it is dropped whole.

The ledger's N3 holds the system prompt equal across the knob's arms (the frozen
`tests/test_k7_request.py` runs the contrast); the design changes nothing in it for shape, and
B's system prompt, which every knob but faults shares, asks the model to "Make one tool call per
turn".  The design also makes batching part of what shape measures: `w4` can finish in two model
calls, `w2` in three and `w1` in five, and the card shows model calls beside tool calls.
Recommended: keep B's system prompt, so shape measures one change, the arrangement of the calls,
and the card shows how often a model batches against the instruction.  If it is declined, the
system prompt of a shape arm is a change to the design, to be worded then, and this file is dropped.
"""

from __future__ import annotations

from tests.k3_support import made
from tests.k7_support import ARMS, SPLITS, base


def test_every_width_and_the_control_keeps_bs_system_prompt() -> None:
    for split, seeds in SPLITS:
        for seed in seeds:
            wanted = base(seed, split).system_prompt
            for arm_id in ARMS:
                assert made(arm_id, seed, split).system_prompt == wanted, (arm_id, seed, split)
