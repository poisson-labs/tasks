"""How a task-shape episode is judged: every target, through the targets `verify` reads, frozen as
tests.

Every target is in the
expected final state; a mutation of a record that is not a target is collateral; G4 passes at every
width; `w2` generates no `collateral_mutation` control, because no call in its block can mutate a
non-target (as stage 8 has no overshoot control); and an episode that makes
`w4`'s four calls in one turn passes.  The design also says `goal` keeps the first target and the
fingerprint adds the target list for shape arms only; the knob's plan does not carry that clause,
and the design's wording holds.

Shapes decided here
-------------------

**1. G4 and every target** are not tested here: the generator refuses any task whose reference does
not verify as `passed`, strict and leaky (its own gate), `tests/test_k7_calls.py` holds the targets
to exactly the width's, and shape 3 below verifies the reference batched.  A test of the
reference, and of the reference less each target's last call, was written and removed before
the freeze: no deliberate bug failed it that another `test_k7_*` test did not.

**2. Collateral**: at `w1` and `w4`, the reference followed by a first-stage call on a record of a
ledger the block can reach that is not a target (the decoy in the target ledger) is
`collateral_mutation`, strict false and leaky true, and the task carries that control.  At `w2`
every stage tool in the block is the target ledger's, both of whose records are targets, and the
task carries no `collateral_mutation` control.  Every control a task carries gives the label it is
named for (a build may add controls, each named for its label).

**3. Batching**: the reference's calls grouped by stage, every target's first stage in one turn,
then every second and so on (`w4` one turn of four, `w2` two of two, `w1` four of one), then a
reply, is `passed`: the design's two, three and five model calls.

**4. The fingerprint's target list**: a shape task's fingerprint moves when its targets' goal
stages move in its expected records, and at `w4` when one of the other ledgers is swapped for one
it does not advance; it does not move when every record id is renamed in every field that carries
it, the prompt slots included (G15 masks record ids); B's fingerprint does not move when its
expected records do (the list is for shape arms only).
"""

from __future__ import annotations

import dataclasses
from typing import Any

from poisson_tasks.tasks import Turn, structural_fingerprint, verify
from tests.k3_support import FMT, SPEC, made, verdict_of
from tests.k7_support import (
    ARMS,
    SPLITS,
    base,
    entry_code,
    ledger_of,
    records,
    stage_names_in,
    stage_of,
    stage_tool,
    targets,
    width_of,
)

RECORD = SPEC.parameter_names["record"]
ENTRY = SPEC.parameter_names["entry"]
# The controls B carries, each named for the label it gives.
NAMED = (
    "wrong_state",
    "turn_limit",
    "collateral_mutation",
    "malformed_call_clause_2",
    "malformed_call_clause_3",
    "malformed_call_clause_4",
)


def label_of(bundle: Any, key: str, calls: Any) -> tuple[str, int | None]:
    if key == "turn_limit":
        verdict = verdict_of(bundle, calls, reply=False, limit=True)
    else:
        verdict = verdict_of(bundle, calls)
    return verdict.label, verdict.format_clause


def named(key: str) -> tuple[str, int | None]:
    label, _sep, clause = key.partition("_clause_")
    return label, int(clause) if clause else None


def test_a_change_to_a_non_target_is_collateral_and_w2_has_no_such_control() -> None:
    """Shape 2."""
    for split, seeds in SPLITS:
        for seed in seeds:
            for arm_id in ARMS:
                bundle = made(arm_id, seed, split)
                where = (arm_id, seed, split)
                found = targets(bundle)
                ledger = bundle.goal[0]
                _target, decoy = records(bundle)
                carried = set(NAMED) - ({"collateral_mutation"} if width_of(arm_id) == 2 else set())
                assert carried <= set(bundle.negative_controls), where
                for key, calls in bundle.negative_controls.items():
                    label, clause = label_of(bundle, key, calls)
                    if key in NAMED:
                        assert (label, clause) == named(key), (key, *where)
                    else:
                        assert key.startswith(label), (key, label, *where)
                if width_of(arm_id) == 2:
                    assert "collateral_mutation" not in bundle.negative_controls, where
                    for name in stage_names_in(bundle):
                        assert ledger_of(name) == ledger, (name, *where)
                    assert {(ledger, r) for r in records(bundle)} <= set(found), where
                    continue
                assert "collateral_mutation" in bundle.negative_controls, where
                assert (ledger, decoy) not in found, where
                extra = (stage_tool(ledger, 1), {RECORD: decoy, ENTRY: entry_code(bundle)})
                verdict = verdict_of(bundle, [*bundle.reference_calls, extra])
                assert (verdict.label, verdict.leaky_pass) == ("collateral_mutation", True), where


def by_stage(calls: Any) -> list[list[Any]]:
    """The calls grouped by the stage each moves its record to, in that order: every target's first
    stage in one turn, then every second, and so on.  A record's token for a stage is fixed by its
    ledger, its id and its stage (the engine's chain token), so the reference's own arguments
    serve in any grouping."""
    turns: dict[int, list[Any]] = {}
    for call in calls:
        turns.setdefault(stage_of(call[0]), []).append(call)
    return [turns[stage] for stage in sorted(turns)]


def test_the_reference_batched_stage_by_stage_passes() -> None:
    """Shape 3."""
    for split, seeds in SPLITS:
        for seed in seeds:
            for width in (1, 2, 4):
                bundle = made(f"shape:w{width}", seed, split)
                turns = by_stage(bundle.reference_calls)
                assert [len(turn) for turn in turns] == [width] * (4 // width), (width, seed)
                episode = tuple(
                    Turn(content="", calls=tuple(turn), finish_reason="tool_calls")
                    for turn in turns
                ) + (Turn(content="Done.", calls=(), finish_reason="stop"),)
                verdict = verify(bundle, episode, True, False, FMT)
                assert (verdict.label, verdict.leaky_pass) == ("passed", True), (width, seed)


def fingerprint_moves(bundle: Any, **changed: Any) -> bool:
    other = dataclasses.replace(bundle, **changed)
    return structural_fingerprint(other) != structural_fingerprint(bundle)


def rows_with(rows: Any, change: Any) -> Any:
    return tuple(sorted(change(row) for row in rows))


def targets_up(bundle: Any) -> Any:
    """The expected records with every target's goal stage one higher."""
    found = targets(bundle)
    return rows_with(
        bundle.expected_final_state,
        lambda row: (*row[:2], row[2] + 1, row[3]) if (row[0], row[1]) in found else row,
    )


def renamed(text: str, ids: dict[str, str]) -> str:
    for old, new in ids.items():
        text = text.replace(old, new)
    return text


def test_the_fingerprint_reads_the_target_list_for_shape_arms_only() -> None:
    """Shape 4."""
    for seed in SPLITS[0][1][:12]:
        for width in (1, 2, 4):
            bundle = made(f"shape:w{width}", seed)
            found = targets(bundle)
            where = (width, seed)
            assert fingerprint_moves(bundle, expected_final_state=targets_up(bundle)), where

            # Every record id renamed in every field that carries it: masked, so nothing moves.
            ids = {record: "x" + record for record in records(bundle)}

            def rename(row: Any, ids: dict[str, str] = ids) -> Any:
                return (row[0], ids[row[1]], *row[2:])

            assert not fingerprint_moves(
                bundle,
                initial_state=rows_with(bundle.initial_state, rename),
                expected_final_state=rows_with(bundle.expected_final_state, rename),
                goal=(bundle.goal[0], ids[bundle.goal[1]], bundle.goal[2]),
                prompt_slots=tuple((n, renamed(v, ids)) for n, v in bundle.prompt_slots),
            ), where
            if width != 4:
                continue
            # One of w4's other ledgers swapped for a ledger it does not advance, in both records
            # values: only the target list's ledgers change.
            ledger = next(q for q, _r in found if q != bundle.goal[0])
            spare = next(q for q in SPEC.qualifiers if (q, bundle.goal[1]) not in found)
            swap = {ledger: spare, spare: ledger}

            def swapped(row: Any, swap: dict[str, str] = swap) -> Any:
                return (swap.get(row[0], row[0]), *row[1:])

            assert fingerprint_moves(
                bundle,
                initial_state=rows_with(bundle.initial_state, swapped),
                expected_final_state=rows_with(bundle.expected_final_state, swapped),
            ), where
        b = base(seed)
        assert not fingerprint_moves(b, expected_final_state=targets_up(b)), seed
