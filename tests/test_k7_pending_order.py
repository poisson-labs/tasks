"""Pending a decision: the order of a task-shape request's goal lines, and of its reference.

**This file waits on a decision** and is its own commit, so if it is declined it is dropped whole.

The design says the reference makes one call per turn and that `goal` keeps the first target; it
does not say in which order the request lists the targets or the reference advances them.  The
frozen `tests/test_k7_calls.py` holds each target's own calls to stage order.  Recommended: one
order for both.  The goal lines list the targets with the goal first (the target record in the
target ledger), then the others (at `w2` the decoy, at `w4` the three other ledgers); and
the reference advances them side by side, stage by stage: every target's first stage in the lines'
order, then every target's second.  So the reference is the batched episode made one call per turn
(`w2`'s two turns of two calls, `w4`'s one of four), and the reference's `wrong_state` control,
its calls but the last, leaves the last line's target short.  If the answer is no, both orders are
the build's, and this file is dropped.
"""

from __future__ import annotations

from tests.k3_support import SPEC, made
from tests.k7_support import ARMS, SPLITS, goal_lines, records, targets, words

RECORD = SPEC.parameter_names["record"]


def test_the_goal_lines_list_the_goal_first_and_the_reference_goes_stage_by_stage() -> None:
    for split, seeds in SPLITS:
        for seed in seeds:
            for arm_id in ARMS:
                bundle = made(arm_id, seed, split)
                where = (arm_id, seed, split)
                found = targets(bundle)
                ledger, target, _stage = bundle.goal
                held = records(bundle)
                listed = []
                for line in goal_lines(bundle):
                    (record,) = [r for r in held if r in line]
                    (named,) = [q for q in SPEC.qualifiers if q in words(line)]
                    listed.append((named, record))
                assert listed[0] == (ledger, target) and set(listed) == set(found), where
                wanted = [
                    key
                    for stage in range(1, max(found.values()) + 1)
                    for key in listed
                    if found[key] >= stage
                ]
                calls = [
                    (SPEC.stage_tools[n][1], args[RECORD]) for n, args in bundle.reference_calls
                ]
                assert calls == wanted, where
