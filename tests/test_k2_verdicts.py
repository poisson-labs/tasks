"""The similarity knob's verdicts, frozen as tests.

A lookalike is another
ledger's real stage tool under a shown name, and the scenario holds the target's record id in
every ledger under one entry code, so a call to the first-stage lookalike with the reference's
arguments succeeds, on the wrong ledger: a real side effect, `collateral_mutation`, which strict
fails and leaky can pass.  A call by a name the block does not show, an engine name the knob
hides included, never reaches the engine.

Shapes decided here
-------------------

**1. The new negative control is pinned by what it is, not by its key**: the reference calls,
then one call to the first-stage lookalike in the lowest slot with the reference's first
arguments; it must verify as `collateral_mutation` with `leaky_pass` true.  Every control's key
still opens with the label it produces, as the existing controls' keys do.

**2. No `overshoot` control.**  The block holds the first two stages of each ledger and the goal
is the second, so no call in it carries the target past the goal; G7 is carried by the
lookalike's collateral, as for knob R (`tasks.py`'s docstring, decision 4).
"""

from __future__ import annotations

from typing import Any

import pytest

from poisson_tasks.tasks import OUTCOMES, FormatSpec, Turn, verify
from tests.k2_support import (
    CARD_SEEDS,
    LEVELS,
    SPEC,
    engines,
    ledger_of,
    lookalike_slots,
    names,
    sim,
    stage_of,
)

FMT = FormatSpec(name="reference", markers=())
SEEDS = CARD_SEEDS[:6]


def verdict_of(bundle: Any, calls: Any, *, reply: bool = True, limit: bool = False) -> Any:
    turns = tuple(Turn(content="", calls=(call,), finish_reason="tool_calls") for call in calls)
    return verify(bundle, turns, reply, limit, FMT)


def first_stage_lookalikes(bundle: Any) -> list[tuple[str, str]]:
    """(shown name, engine name) of every first-stage lookalike, in slot order."""
    behind = engines(bundle)
    return [(names(bundle)[s], behind[s]) for s in lookalike_slots(bundle)
            if stage_of(behind[s]) == 0]


def moved(verdict: Any) -> set[tuple[str, str]]:
    return {(cls, record) for cls, record, _field in verdict.mutations}


def test_an_engine_name_the_knob_hides_changes_nothing() -> None:
    """The engine knows every hidden name.  Called by them, the right chain moves nothing (and the
    format check reports clause 3); a first-stage lookalike called by its engine name after the
    reference moves nothing either, so the episode passes with the clause reported, where the
    same call by its shown name is collateral."""
    for seed in SEEDS:
        bundle = sim(2, seed)
        cls, record, _goal = bundle.goal
        ref = list(bundle.reference_calls)
        behind = dict(zip(names(bundle), engines(bundle), strict=True))
        hidden = [(behind[name], args) for name, args in ref]
        assert all(name in SPEC.stage_tools for name, _args in hidden)
        got = verdict_of(bundle, hidden)
        assert got.mutations == () and got.format_clause == 3 and not got.leaky_pass, got
        shown, engine = first_stage_lookalikes(bundle)[0]
        quiet = verdict_of(bundle, ref + [(engine, dict(ref[0][1]))])
        assert (quiet.strict_label, quiet.format_clause) == ("passed", 3), quiet
        assert moved(quiet) == {(cls, record)}, quiet
        loud = verdict_of(bundle, ref + [(shown, dict(ref[0][1]))])
        assert loud.strict_label == "collateral_mutation", loud


def label_of(key: str) -> str:
    """The label a control's key names: the longest outcome the key opens with."""
    opening = [label for label in OUTCOMES if key == label or key.startswith(label + "_")]
    assert opening, key
    return max(opening, key=len)


@pytest.mark.parametrize("level", LEVELS)
def test_every_negative_control_produces_the_label_it_names(level: int) -> None:
    """G8 on similarity: each generated control gives the label its key opens with, through the
    shown names; no `overshoot` control is generated (shape 2); and one control is the reference
    plus the first-stage lookalike in the lowest slot, collateral and leaky, moving the target's
record in that lookalike's ledger (shape 1)."""
    for seed in SEEDS:
        bundle = sim(level, seed)
        ref = tuple(bundle.reference_calls)
        assert "overshoot" not in {label_of(key) for key in bundle.negative_controls}
        for key, calls in bundle.negative_controls.items():
            label = label_of(key)
            got = (verdict_of(bundle, calls, reply=False, limit=True) if label == "turn_limit"
                   else verdict_of(bundle, calls))
            assert got.strict_label == label, (seed, key, got)
            if "_clause_" in key:
                assert got.format_clause == int(key.rsplit("_", 1)[1]), (key, got)
        lowest, engine = first_stage_lookalikes(bundle)[0]
        wanted = ref + ((lowest, dict(ref[0][1])),)
        matching = [key for key, calls in bundle.negative_controls.items()
                    if tuple(calls) == wanted]
        assert len(matching) == 1, (seed, list(bundle.negative_controls))
        got = verdict_of(bundle, wanted)
        assert (got.strict_label, got.leaky_pass) == ("collateral_mutation", True)
        cls, record, _goal = bundle.goal
        assert moved(got) == {(cls, record), (ledger_of(engine), record)}, got
