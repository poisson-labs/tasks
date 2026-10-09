"""What the task-shape knob holds fixed: the base task's fields it does not move, and its control
`w1` plus a filler, frozen as tests.

Spec §14.3: fixed at every width are four stage calls and a reply, the scenario and the block's
size; what moves is how the four calls are arranged, so the targets, the block's composition (its
token count reported, N33), the request's goal lines (N34) and the reference.  Spec §3.1 names
`w1` the knob's base, because shape has four stage calls at every width where B has two; spec
§3.6 puts the control's filler at the end of the request, where N3 does not look.

Shapes decided here
-------------------

**1. Every width and the control is B in every field the knob does not move**, at every card seed on
both splits: the seed and split, the scenario, `seq_start` (no shape arm seeds a history), the
initial records, the verifier, the engine hash and the generator hash.  The system prompt is held
equal across the widths by the ledger's N3 (`tests/test_k7_request.py`'s contrast); whether it is
B's, whose "Make one tool call per turn" sits beside the batching spec §14.3 measures, waits on a
yes/no (`tests/test_k7_pending_system_prompt.py`).  The fields that move are the id, the pins,
the tools, the request and its template and slots, the expected records and the goal, the
reference calls and observations and the negative controls; each is held by its own test file
(`tests/test_k7_calls.py`, `test_k7_block.py`, `test_k7_request.py`, `test_k7_verdict.py`).

**2. The control is `w1` but for its request**, which is `w1`'s followed by the filler, in words no
part of the vocabulary table spells, with no underscore, so they name no tool, no ledger and no
record.  Its length is the ledger's N34 (`tests/test_k7_request.py`).
"""

from __future__ import annotations

import dataclasses
from typing import Any

from tests.k3_support import made
from tests.k7_support import ARMS, CONTROL, SPLITS, base, control, request, shape, table_text

MOVES = {
    "system_prompt",
    "arm_id",
    "task_id",
    "pins",
    "tools",
    "prompt",
    "template_id",
    "prompt_slots",
    "expected_final_state",
    "goal",
    "reference_calls",
    "reference_observations",
    "negative_controls",
}


def kept(bundle: Any, moves: set[str]) -> dict[str, Any]:
    return {
        field.name: getattr(bundle, field.name)
        for field in dataclasses.fields(bundle)
        if field.name not in moves
    }


def test_every_width_and_the_control_is_b_in_every_field_the_knob_does_not_move() -> None:
    """Shape 1."""
    for split, seeds in SPLITS:
        for seed in seeds:
            b = kept(base(seed, split), MOVES)
            for arm_id in ARMS:
                assert kept(made(arm_id, seed, split), MOVES) == b, (arm_id, seed, split)


def test_the_control_is_w1_with_a_neutral_filler_after_its_request() -> None:
    """Shape 2."""
    table = table_text()
    for split, seeds in SPLITS:
        for seed in seeds:
            low, held = shape(1, seed, split), control(seed, split)
            moves = {"arm_id", "task_id", "pins", "prompt"}
            assert kept(held, moves) == kept(low, moves), (seed, split)
            assert held.arm_id == CONTROL
            text, low_text = request(held), request(low)
            assert text.startswith(low_text), (seed, split)
            words = text[len(low_text) :].split()
            assert words, (seed, split)
            for word in words:
                assert "_" not in word and word.lower() not in table, (word, seed, split)
