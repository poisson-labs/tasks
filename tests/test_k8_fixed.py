"""What the information-spread knob holds fixed: one task at every level but the answers, and the
base task's fields the design does not move, frozen as tests.

The prompt, the block, the system prompt and the six tool calls the episode needs (four reads, two
stage calls) are equal across levels (N35); only how the code is spread across the four answers
changes.  With it, the standing decision that every information-spread arm is the base task plus
only what the design says this knob changes: the design's task is B, but the request does not state
the entry code and names four reads instead, and the stage-1 tool's description, "requires the entry
code stated in the request", which would be false here, says through the display map that the code
is assembled from the named reads (the second half of `tests/test_k8_only.py`'s rule).  Spread has
no control arm (N15 as decided): the request and the calls are the same at every level, so there is
no length to hold.

Shapes decided here
-------------------

**1. One task at every level but its answers**: at every card seed on both splits, the card's three
levels and the one between them the generator can build are equal in every field but the arm id,
the task id, the pins and the reference observations; and the observations differ only in the
named reads' answers (`tests/test_k8_parts.py` holds what those are).

**2. B in every field the design does not move**: the seed and split, the scenario, `seq_start` (no
spread arm seeds a history), the initial and the expected records, the goal, the system prompt,
the verifier, the engine hash and the generator hash.  The block is B's, tool for tool and slot for
slot, but the target ledger's first stage tool, whose description is the display map's for a
spread arm (`surface.display_map`): the engine's own with "stated in the request" replaced by the
design's "assembled from the reads named in the request".
Every line of B's request but the one that states the entry code is a line of the spread request,
in B's order.  The reference's stage calls are B's two, with B's arguments, and each answers as the
engine answers it at its place in the reference; its other calls are the four named reads
(`tests/test_k8_reads.py`).  The fields that move are the id, the pins, the request with its
template and slots, the reference and its observations, and the negative controls built from it
(`tests/test_k8_verdict.py`).
"""

from __future__ import annotations

import dataclasses
from typing import Any

from poisson_tasks import surface
from poisson_tasks.engine import replay
from poisson_tasks.tasks import scenario_for
from tests.k3_support import SPEC
from tests.k8_support import LEVELS, SPLITS, base, entry_code, names, request, spread

# The design: the stage-1 tool's description, "requires the entry code stated in the request",
# says "requires the entry code assembled from the reads named in the request" for spread arms.
STATED = "stated in the request"
ASSEMBLED = "assembled from the reads named in the request"
ACROSS_LEVELS = {"arm_id", "task_id", "pins", "reference_observations"}
FROM_B = (
    "seed",
    "split",
    "scenario_hash",
    "seq_start",
    "initial_state",
    "expected_final_state",
    "goal",
    "system_prompt",
    "verifier",
    "engine_hash",
    "generator_hash",
)


def kept(bundle: Any, moves: set[str]) -> dict[str, Any]:
    return {
        field.name: getattr(bundle, field.name)
        for field in dataclasses.fields(bundle)
        if field.name not in moves
    }


def test_every_level_is_one_task_but_the_named_reads_answers() -> None:
    """Shape 1."""
    for split, seeds in SPLITS:
        for seed in seeds:
            bundles = [spread(level, seed, split) for level in LEVELS]
            first = bundles[0]
            reads = [i for i, (n, _a) in enumerate(first.reference_calls) if n in SPEC.read_tools]
            for bundle in bundles[1:]:
                where = (bundle.arm_id, seed, split)
                assert kept(bundle, ACROSS_LEVELS) == kept(first, ACROSS_LEVELS), where
                for index, observation in enumerate(bundle.reference_observations):
                    if index not in reads:
                        assert observation == first.reference_observations[index], where


def first_stage(bundle: Any) -> str:
    (name,) = [
        n for n, (index, q) in SPEC.stage_tools.items() if index == 0 and q == bundle.goal[0]
    ]
    return str(name)


def test_every_level_is_b_in_every_field_the_spec_does_not_move() -> None:
    """Shape 2."""
    for split, seeds in SPLITS:
        for seed in seeds:
            b = base(seed, split)
            b_lines = [line for line in request(b).split("\n") if f'"{entry_code(b)}"' not in line]
            for level in LEVELS:
                bundle = spread(level, seed, split)
                where = (level, seed, split)
                for name in FROM_B:
                    assert getattr(bundle, name) == getattr(b, name), (name, *where)

                stage = first_stage(bundle)
                shown = surface.display_map(seed, split, bundle.arm_id, bundle.goal, names(b))
                said = shown[stage].description
                own = next(tool["description"] for tool in b.tools if tool["name"] == stage)
                assert said == own.replace(STATED, ASSEMBLED), where
                expected = tuple(
                    {**tool, "description": said} if tool["name"] == stage else tool
                    for tool in b.tools
                )
                assert bundle.tools == expected, where

                lines = request(bundle).split("\n")
                at = [lines.index(line) for line in b_lines if line in lines]
                assert len(at) == len(b_lines) and at == sorted(at), where

                calls = list(bundle.reference_calls)
                stages = [i for i, (n, _a) in enumerate(calls) if n in SPEC.stage_tools]
                assert [calls[i] for i in stages] == list(b.reference_calls), where
                _state, engine = replay(scenario_for(seed, split), calls, bundle.seq_start)
                for index in stages:
                    assert bundle.reference_observations[index] == engine[index], where
