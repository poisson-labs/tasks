"""What the block-size knob holds fixed: everything but the block, frozen as a test.

The invariant is K5.4 of the knobs plan, from spec §3.1 and §14.1: the prompt, the system prompt
(but the control's filler), the scenario and the reference calls are equal across levels, and K1.1
still holds for every published task (frozen `tests/test_k1_content.py`).  Spec §3.1 lists block
size among the knobs that measure departures from one base task, B (`distractor:r0@k16`).

Shapes decided here
-------------------

**1. Equal across levels, and equal to B's.**  A block task is B in every field but `arm_id`,
`task_id`, `pins`, its tools and one negative control, at every level and seed on both splits; the
control is that and k8's block, its system prompt B's with the filler after it
(`tests/test_k5_length.py`).  Holding the fields to B's rather than to one another's also says the
knob's base task is the base task: B's system prompt, B's request, B's scenario and goal, B's two
reference calls and their answers, B's `seq_start`.

**2. The one negative control that moves is the call outside the block** (format clause 3): it
names the first read the block does not offer, and from k32 on, where the block offers every read,
a stage tool of another ledger aimed at a record the scenario does not hold, as the generator does
on a table too small to leave a read out.  Either way it names no tool of its block, and the
verifier gives it its label and clause.  Every other negative control is B's.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from tests.k3_support import B_ARM, made, names, verdict_of
from tests.k5_support import ARMS, CONTROL, SPLITS

MOVES = {"arm_id", "task_id", "pins", "tools", "negative_controls"}
OUTSIDE = "malformed_call_clause_3"


def kept(bundle: Any, *, also: frozenset[str] = frozenset()) -> dict[str, Any]:
    return {
        field.name: getattr(bundle, field.name)
        for field in dataclasses.fields(bundle)
        if field.name not in MOVES | also
    }


def test_every_level_and_the_control_is_b_in_all_but_its_tools() -> None:
    for split, seeds in SPLITS:
        for seed in seeds:
            b = made(B_ARM, seed, split)
            b_controls = {k: v for k, v in b.negative_controls.items() if k != OUTSIDE}
            for arm_id in ARMS:
                bundle = made(arm_id, seed, split)
                also = frozenset({"system_prompt"}) if arm_id == CONTROL else frozenset()
                assert kept(bundle, also=also) == kept(b, also=also), (arm_id, seed, split)
                assert bundle.system_prompt.startswith(b.system_prompt), (arm_id, seed, split)
                controls = dict(bundle.negative_controls)
                outside = controls.pop(OUTSIDE)
                assert controls == b_controls, (arm_id, seed, split)
                ((name, _args),) = outside
                assert name not in names(bundle), (arm_id, seed, split)
                verdict = verdict_of(bundle, outside)
                assert (verdict.label, verdict.format_clause) == ("malformed_call", 3), (
                    arm_id,
                    seed,
                    split,
                )
