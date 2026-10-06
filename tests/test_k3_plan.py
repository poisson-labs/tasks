"""The faults knob's tasks: the plan, the answer, the system prompt and the reference, frozen as
tests.

The invariants are K3.1, K3.2, K3.5 and K3.6 of the knobs plan, from spec §6.2, §6.3 and §3.1.  A
faults arm is B -- `distractor:r0@k16`'s task, two chained stage calls in a sixteen-tool block --
plus one system-prompt sentence at every level, and at level F the first ceil(F/2) calls to the
first stage tool and the first floor(F/2) calls to the second answer `unavailable`.  The reference
solution makes each planned failure and the same call again after it.

Shapes decided here
-------------------

**1. The sentence is spec §6.3's, word for word, backticks included, on a line of its own after
B's system prompt.**  The spec gives the sentence and says it is added; B's prompt is four lines,
so the sentence is a fifth.  The backticks are kept because the spec prints them inside the quoted
sentence, and they mark `unavailable` as the status word the line carries.

**2. A faults arm differs from B in nothing the knob does not need.**  `faults:f0` is B field for
field but `arm_id`, `task_id`, `pins` and the system prompt (spec §3.1).  A level above 0 is
`faults:f0` field for field but those three, the reference calls and observations, and the
negative controls, which are built from the reference.  The control is `faults:f0` but those three,
the prompt (its seeded pairs), `seq_start` and the reference observations (their `seq` moves);
`tests/test_k3_control.py` pins what it seeds.

**3. The planned call is the same call.**  The reference repeats the right call with the same
arguments, as many times as it is planned to fail, plus once: "the same call can be made again".

**4. A planned failure is the engine's own line.**  `seq` is the next number, the status is
`unavailable` in the status field, the payload is the table's error payload, and the line is the
table's `L_obs` bytes.  It is rendered from the table's layout (`EngineSpec.layout`); `surface`
imports nothing private from the engine (spec §3.4), checked by reading its source.
"""

from __future__ import annotations

import ast
import dataclasses
import math
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import surface
from poisson_tasks.arms import arm_from_id
from poisson_tasks.tasks import OUTCOMES
from poisson_tasks.tokenizer import count_tokens
from tests.k3_support import (
    CARD_SEEDS,
    CONTROL,
    LEVELS,
    SENTENCE,
    SPEC,
    UNAVAILABLE,
    answers,
    arm,
    base,
    faults,
    made,
    right,
    seq,
    status,
    verdict_of,
)

SURFACE = Path(surface.__file__)


def planned(level: int) -> tuple[int, int]:
    """Spec §6.2's table: the first stage takes the odd failure."""
    return math.ceil(level / 2), level // 2


@pytest.mark.parametrize("level", LEVELS)
def test_the_reference_makes_each_planned_failure_and_then_the_same_call_again(level: int) -> None:
    """K3.1 and K3.6, at every card seed on both splits: the calls, the statuses, the numbering,
    the plan `surface.fault_plan` gives for the arm's id and the reference's tools, the ledger's
    N25, and a reference one call per planned failure longer than B's."""
    first_fails, second_fails = planned(level)
    for split in ("eval", "train"):
        for seed in CARD_SEEDS:
            bundle = faults(level, seed, split)
            first, second = right(bundle)
            assert list(bundle.reference_calls) == (
                [first] * (first_fails + 1) + [second] * (second_fails + 1)
            ), (split, seed)
            observations = list(bundle.reference_observations)
            assert [status(o) for o in observations] == (
                [UNAVAILABLE] * first_fails + ["ok"] + [UNAVAILABLE] * second_fails + ["ok"]
            )
            assert [seq(o) for o in observations] == list(
                range(bundle.seq_start, bundle.seq_start + len(observations))
            )
            done = [o for o in observations if status(o) == "ok"]
            b_done = list(base(seed, split).reference_observations)
            assert [o.split()[2] for o in done] == [o.split()[2] for o in b_done]
            path = (first[0], second[0])
            plan = {name: count for name, count in zip(path, planned(level), strict=True) if count}
            assert surface.fault_plan(bundle.arm_id, path) == plan
            assert bundle.pins.values["N25"] == ((first[0], first_fails), (second[0], second_fails))
            assert len(bundle.reference_calls) + 1 == arm_from_id(arm(level)).reference_turns


def test_a_planned_failure_is_one_engine_line_that_changes_nothing() -> None:
    """K3.2: every `unavailable` line of `faults:f4` at the card seeds is the table's layout at
    its `seq`, `L_obs` bytes, inside N8's token band.  At `faults:f1` the first right call alone
    moves no record, in `verify` and in the tool server, whose next call meets the record where
    it was."""
    layout = SPEC.layout
    low, high = SPEC.table["token_band"]
    for seed in CARD_SEEDS:
        for line in faults(4, seed).reference_observations:
            if status(line) != UNAVAILABLE:
                continue
            assert line == layout["separator"].join(
                (
                    str(seq(line)).rjust(layout["seq_width"], layout["seq_fill"]),
                    UNAVAILABLE.ljust(layout["status_width"], layout["status_fill"]),
                    layout["error_payload"],
                )
            ), line
            assert len(line.encode("ascii")) == SPEC.L_obs
            assert low <= count_tokens(line) <= high
    bundle = faults(1, CARD_SEEDS[0])
    first, second = right(bundle)
    got = verdict_of(bundle, [first])
    assert (got.strict_label, got.leaky_pass, got.mutations) == ("wrong_state", False, ())
    assert [status(line) for line in answers(bundle, [first, second])] == [UNAVAILABLE, "not_ready"]
    tree = ast.parse(SURFACE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "poisson_tasks.engine":
            assert all(not alias.name.startswith("_") for alias in node.names), ast.dump(node)


def other_fields(a: Any, b: Any) -> set[str]:
    return {
        field.name
        for field in dataclasses.fields(a)
        if getattr(a, field.name) != getattr(b, field.name)
    }


def test_every_faults_arm_is_b_with_one_sentence_and_the_retries_it_plans() -> None:
    """K3.5 and spec §3.1, at twelve card seeds on both splits (shape 2)."""
    for split in ("eval", "train"):
        for seed in CARD_SEEDS[:12]:
            b = base(seed, split)
            f0 = faults(0, seed, split)
            assert other_fields(f0, b) == {"arm_id", "task_id", "pins", "system_prompt"}
            assert f0.system_prompt == b.system_prompt + "\n" + SENTENCE
            for level in LEVELS[1:]:
                assert other_fields(faults(level, seed, split), f0) == {
                    "arm_id",
                    "task_id",
                    "pins",
                    "reference_calls",
                    "reference_observations",
                    "negative_controls",
                }, (split, seed, level)
            control = made(CONTROL, seed, split)
            assert other_fields(control, f0) == {
                "arm_id",
                "task_id",
                "pins",
                "prompt",
                "seq_start",
                "reference_observations",
            }


def label_of(key: str) -> str:
    """The label a control's key names: the longest outcome the key opens with."""
    opening = [label for label in OUTCOMES if key == label or key.startswith(label + "_")]
    assert opening, key
    return max(opening, key=len)


@pytest.mark.parametrize("arm_id", [arm(level) for level in LEVELS] + [CONTROL])
def test_every_negative_control_produces_the_label_it_names(arm_id: str) -> None:
    """G8 on faults: each generated control gives the label its key opens with, with the planned
    failures applied, so the controls are built from the reference that makes them."""
    for seed in CARD_SEEDS[:6]:
        bundle = made(arm_id, seed)
        for key, calls in bundle.negative_controls.items():
            label = label_of(key)
            got = (
                verdict_of(bundle, calls, reply=False, limit=True)
                if label == "turn_limit"
                else verdict_of(bundle, calls)
            )
            assert got.strict_label == label, (seed, key, got)
            if "_clause_" in key:
                assert got.format_clause == int(key.rsplit("_", 1)[1]), (key, got)
