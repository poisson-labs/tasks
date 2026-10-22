"""The history knob's kind: what is seeded, and what stays B, frozen as tests.

It rests on the pin ledger's N24.  Every
seeded pair is a read tool in the block, answered `ok`, mutating nothing; the system prompt, the
block, the instruction, the goal and the reference calls are equal across levels (N3, N4, N6),
which is why history has its own branch in the generator's block rule and never knob R's
designation; `history:t0` is `distractor:r0@k16` at every seed in every field but `arm_id`,
`task_id` and `pins`.

Shapes decided here
-------------------

**1. "Mutating nothing" is measured through the engine.**  The seeded calls, replayed from the
scenario's initial state at `seq` 1, give back the seeded observations byte for byte and leave
every record where it was: the seeded history is the engine's own answers to the calls as made,
not text that looks like them.  That is what lets a run's replay check take in history without
replaying the seeded pairs (`tests/test_k4_records.py`).

**2. A level above 0 differs from `history:t0` in nothing the knob does not need**: `arm_id`,
`task_id`, `pins`, the prompt (its seeded pairs), `seq_start` and the reference observations,
whose `seq` moves with `seq_start` and whose statuses and payloads do not.  The negative
controls are built from the reference calls, which are equal, so they are equal too.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from poisson_tasks.engine import init_state, mutations, replay
from poisson_tasks.tasks import scenario_for
from tests.k3_support import SPEC, base, names, seq, status
from tests.k4_support import LEVELS, SPLITS, history, seeded


def other_fields(a: Any, b: Any) -> set[str]:
    return {
        field.name
        for field in dataclasses.fields(a)
        if getattr(a, field.name) != getattr(b, field.name)
    }


def test_t0_is_b_in_every_field_but_its_id_and_pins() -> None:
    """At every card seed on both splits."""
    for split, seeds in SPLITS:
        for seed in seeds:
            assert other_fields(history(0, seed, split), base(seed, split)) == {
                "arm_id",
                "task_id",
                "pins",
            }, (split, seed)


@pytest.mark.parametrize("level", LEVELS[1:])
def test_a_level_above_zero_is_t0_but_its_seeded_prompt_and_numbering(level: int) -> None:
    """Shape 2: the block is B's, not knob R's designation, at every level."""
    for split, seeds in SPLITS:
        for seed in seeds:
            t0 = history(0, seed, split)
            bundle = history(level, seed, split)
            assert other_fields(bundle, t0) == {
                "arm_id",
                "task_id",
                "pins",
                "prompt",
                "seq_start",
                "reference_observations",
            }, (split, seed)
            assert not isinstance(bundle.prompt, str)
            assert bundle.prompt[0] == {"role": "user", "content": t0.prompt}
            theirs = list(bundle.reference_observations)
            assert [o.split()[1:] for o in theirs] == [
                o.split()[1:] for o in t0.reference_observations
            ]
            assert [seq(o) for o in theirs] == list(
                range(bundle.seq_start, bundle.seq_start + len(theirs))
            )


@pytest.mark.parametrize("level", LEVELS[1:])
def test_every_seeded_pair_is_a_read_in_the_block_the_engine_answers_ok_and_moves_nothing(
    level: int,
) -> None:
    """Shape 1, at every card seed on both splits; the ledger's N24 names no
    offender."""
    for split, seeds in SPLITS:
        for seed in seeds:
            bundle = history(level, seed, split)
            pairs = seeded(bundle)
            assert pairs, (split, seed)
            for index, (name, _args, observation) in enumerate(pairs):
                assert name in SPEC.read_tools and name in names(bundle), name
                assert (status(observation), seq(observation)) == ("ok", index + 1)
            scenario = scenario_for(seed, split)
            final, replayed = replay(scenario, [(name, args) for name, args, _o in pairs], 1)
            assert replayed == [observation for _n, _a, observation in pairs]
            assert mutations(init_state(scenario, 1), final) == []
            assert bundle.pins.values["N24"] == ()
