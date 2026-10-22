"""What the argument-difficulty knob holds fixed: B plus the stated values and nothing else, its
control a2 plus a filler, frozen as tests.

The scenario, the block (N4), the system prompt and the reference call sequence are equal across
levels.  The design names a2, the knob's base level, as B (`distractor:r0@k16`) with the
eight-parameter schema, and says what a level changes: the request states `A - 2` values and both
stage calls carry them; the control `arguments:a2+len(a8)` holds a2's request plus a neutral filler
at its end (where N3 does not look, and the filler words keep it neutral).

Shapes decided here
-------------------

**1. Every level and the control is B but for what the knob changes**, at every card seed on both
splits.  Equal to B's: the scenario, the system prompt, `seq_start`, the template, the initial and
expected records, the goal, the reference observations (the engine sees only its two arguments),
the verifier, the engine hash and the generator hash.  The fields that move, each held to B's once
the knob's own part is set aside: the tools (`tests/test_k6_schema.py` holds them to B's but the
stage tools' six more parameters); the prompt slots, B's with at most one more, the knob's own slot
`stated_values` (the slot the ledger's N6 leaves out, `knobs._OWN_SLOT`); the reference calls,
B's once each call's extra values are set aside; and every negative control, B's with the same
setting aside, each still giving the label it is named for (a build may add controls of its own,
each named for the label it gives).  So a level moves the request and what
the stage calls carry, and nothing a model meets on the way.  a2's request is B's.

**2. The control is a2 but for its request**, which is a2's followed by the filler, in words no part
of the vocabulary table spells, with no underscore, so they neither name a tool nor state a value.
Its length is the ledger's N32 (`tests/test_k6_stated.py`).
"""

from __future__ import annotations

import dataclasses
from typing import Any

from tests.k3_support import made, verdict_of
from tests.k6_support import (
    ARMS,
    CONTROL,
    SLOT,
    SPLITS,
    arguments,
    base,
    control,
    request,
    stripped,
    table_text,
)

MOVES = {
    "arm_id",
    "task_id",
    "pins",
    "tools",
    "prompt",
    "prompt_slots",
    "reference_calls",
    "negative_controls",
}


def kept(bundle: Any, moves: set[str]) -> dict[str, Any]:
    return {
        field.name: getattr(bundle, field.name)
        for field in dataclasses.fields(bundle)
        if field.name not in moves
    }


def plain(calls: Any) -> tuple[tuple[str, Any], ...]:
    return tuple(stripped(call) for call in calls)


def label_of(bundle: Any, key: str, calls: Any) -> tuple[str, int | None]:
    if key == "turn_limit":
        verdict = verdict_of(bundle, calls, reply=False, limit=True)
    else:
        verdict = verdict_of(bundle, calls)
    return verdict.label, verdict.format_clause


def named(key: str) -> tuple[str, int | None]:
    label, _sep, clause = key.partition("_clause_")
    for suffix in ("_lookalike",):
        label = label.removesuffix(suffix)
    return label, int(clause) if clause else None


def test_every_level_and_the_control_is_b_plus_what_the_knob_changes() -> None:
    """Shape 1."""
    for split, seeds in SPLITS:
        for seed in seeds:
            b = base(seed, split)
            for arm_id in ARMS:
                bundle = made(arm_id, seed, split)
                where = (arm_id, seed, split)
                assert kept(bundle, MOVES) == kept(b, MOVES), where
                slots = [slot for slot in bundle.prompt_slots if slot[0] != SLOT]
                assert len(bundle.prompt_slots) - len(slots) <= 1, where
                assert tuple(slots) == tuple(b.prompt_slots), where
                assert plain(bundle.reference_calls) == plain(b.reference_calls), where
                assert set(b.negative_controls) <= set(bundle.negative_controls), where
                for key, calls in bundle.negative_controls.items():
                    label, clause = label_of(bundle, key, calls)
                    if key in b.negative_controls:
                        assert plain(calls) == plain(b.negative_controls[key]), (key, *where)
                        assert (label, clause) == named(key), (key, *where)
                    else:
                        assert key.startswith(label), (key, label, *where)
            assert request(arguments(2, seed, split)) == request(b), (seed, split)


def test_the_control_is_a2_with_a_neutral_filler_after_its_request() -> None:
    """Shape 2."""
    table = table_text()
    for split, seeds in SPLITS:
        for seed in seeds:
            low, held = arguments(2, seed, split), control(seed, split)
            moves = {"arm_id", "task_id", "pins", "prompt"}
            assert kept(held, moves) == kept(low, moves), (seed, split)
            assert held.arm_id == CONTROL
            text, low_text = request(held), request(low)
            assert text.startswith(low_text), (seed, split)
            words = text[len(low_text) :].split()
            assert words, (seed, split)
            for word in words:
                assert "_" not in word and word.lower() not in table, (word, seed, split)
