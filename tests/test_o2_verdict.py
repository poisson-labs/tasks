"""The verdict on a user's own tools, frozen as tests.

The invariant is O2.3 of the knobs plan (spec §5.2, §10): each task's reference calls verify as
passed under strict and leaky (G4's analogue) over thousands of seeds per fixture set, and every
outcome label is reachable by a generated negative control.  And §5.2's clauses: the built-in
outcome vocabulary in its order; passed means the store ends exactly as expected and the episode
ends with a reply; collateral_mutation, the goal reached and another write accepted;
wrong_state, the goal not reached; malformed_call, a call naming a tool outside the block or
breaking its schema; turn_limit and the instrument labels as for built-in tasks; leaky accepts
collateral; arguments compare exactly (strings byte for byte, numbers by value, booleans and
enums exactly), and an argument the request did not state is ignored.

Shapes decided here
-------------------

**1. `poisson_tasks.own.verdict.verify(task, turns, ended_with_reply, turn_limit_hit, fmt)`**
takes `tasks.Turn`s and a `tasks.FormatSpec` and returns a `tasks.Verdict`, as `tasks.verify`
does, so the export and the card read both alike.  Every raise inside is `verifier_error`, and so
is an episode that neither replied nor hit the turn limit.  `Verdict.mutations` holds one entry
per accepted write, expected or not.

**2. No overshoot.**  A user's write has no stage past its goal, so `overshoot` is never an own
verdict (every label a negative control reaches is one of the five below).  Whether the expected write made again is a side effect is the pending file
`test_o2_pending_repeat_write.py`.

**3. The negative controls** are `negative_controls` on the task, named for their label as the
built-in ones are: `wrong_state` (the reference without its last write), `turn_limit` (the
reference, no reply, the limit hit), `collateral_mutation` (the reference and one more accepted
write), `malformed_call_clause_2`, `_3` and `_4` (arguments that are not an object, a name
outside the block, arguments that break the schema), and on a similarity arm
`collateral_mutation_lookalike` (the reference and a write to a numbered copy).  The format
clauses are the built-in ones; the pass predicate is decided first, so a malformed call in an
episode that passes is still `passed` with its clause reported.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from tests.o1_support import fixture
from tests.o2_support import (
    ACME_READS,
    acme,
    acme_flows,
    every_arm,
    fixture_sets,
    flows_for,
    generator,
    judge,
    label_of,
    make,
    mcp_set,
    read_tool,
    write_tool,
)

# Spec §10: "thousands of seeds per fixture set".
SEEDS_PER_SET = 2000
SETS = ("acme-mcp", "acme-openai", "acme-openapi-3.0", "acme-openapi-3.1", "petstore", "everything")
SYSTEM_LABELS = {"passed", "collateral_mutation", "wrong_state", "malformed_call", "turn_limit"}


@pytest.mark.parametrize("label", SETS)
def test_g4_each_tasks_reference_passes_under_strict_and_leaky_over_thousands_of_seeds(label: str) -> None:
    toolset = fixture_sets()[label]
    flows = flows_for(label)
    arms = every_arm(toolset, flows)
    assert arms, label
    for seed in range(SEEDS_PER_SET):
        spec = arms[seed % len(arms)]
        bundle = generator().generate(toolset, spec, seed, flows=flows)
        for strictness in ("strict", "leaky"):
            probe = dataclasses.replace(bundle, strictness=strictness)
            found = judge(probe, bundle.reference_calls)
            assert (found.label, found.strict_label, found.leaky_pass, found.format_clause) == (
                "passed", "passed", True, None), (label, spec, seed, strictness, found)


@pytest.mark.parametrize("label", SETS)
def test_every_outcome_label_is_reachable_by_a_generated_negative_control(label: str) -> None:
    toolset = fixture_sets()[label]
    flows = flows_for(label)
    for spec in every_arm(toolset, flows):
        for seed in range(25):
            bundle = generator().generate(toolset, spec, seed, flows=flows)
            reached = {"passed"}
            for name, calls in bundle.negative_controls.items():
                limit = name == "turn_limit"
                found = judge(bundle, calls, reply=not limit, turn_limit=limit)
                assert found.strict_label == label_of(name), (label, spec, seed, name, found)
                reached.add(found.strict_label)
            assert reached == SYSTEM_LABELS, (label, spec, seed, reached)
            if spec.knob == "similarity":
                assert "collateral_mutation_lookalike" in bundle.negative_controls


def test_leaky_accepts_collateral_and_strict_does_not() -> None:
    for knob, level in (("faults", 1), ("similarity", 2), ("spread", 2)):
        bundle = make(fixture_sets()["acme-mcp"], knob, level, flows=())
        calls = bundle.negative_controls["collateral_mutation"]
        strict = judge(bundle, calls)
        leaky = judge(dataclasses.replace(bundle, strictness="leaky"), calls)
        assert (strict.label, strict.strict_label, strict.leaky_pass) == (
            "collateral_mutation", "collateral_mutation", True)
        assert (leaky.label, leaky.strict_label, leaky.leaky_pass) == (
            "passed", "collateral_mutation", True)
        short = bundle.negative_controls["wrong_state"]
        assert judge(dataclasses.replace(bundle, strictness="leaky"), short).label == "wrong_state"


def test_a_malformed_call_in_an_episode_that_passes_is_still_passed_with_its_clause() -> None:
    bundle = make(fixture_sets()["acme-mcp"], "faults", 0)
    outside = bundle.negative_controls["malformed_call_clause_3"]
    found = judge(bundle, outside + bundle.reference_calls)
    assert (found.strict_label, found.format_clause) == ("passed", 3)
    alone = judge(bundle, outside)
    assert (alone.strict_label, alone.format_clause) == ("malformed_call", 3)
    broken = judge(bundle, bundle.negative_controls["malformed_call_clause_4"] + bundle.reference_calls)
    assert (broken.strict_label, broken.format_clause) == ("passed", 4)


def test_a_call_outside_the_block_changes_nothing_even_when_it_names_a_real_write() -> None:
    """The block arm offers some of the set: a write of the set left out of the block is answered
    by the harness, never reaches the server and moves nothing."""
    toolset = fixture_sets()["petstore"]
    bundle = make(toolset, "block", 8, seed=2)
    shown = {str(tool["name"]) for tool in bundle.tools}
    left_out = [tool for tool in toolset.tools if tool.name not in shown and tool.effect == "write"]
    assert left_out
    stray: tuple[str, dict[str, Any]] = (left_out[0].name, {})
    found = judge(bundle, (stray,) + bundle.reference_calls)
    assert found.strict_label == "passed" and len(found.mutations) == 1


def test_an_episode_that_neither_replied_nor_hit_the_limit_and_a_broken_task_are_verifier_error() -> None:
    bundle = make(fixture_sets()["acme-mcp"], "faults", 1)
    found = judge(bundle, bundle.reference_calls, reply=False, turn_limit=False)
    assert (found.strict_label, found.label, found.leaky_pass) == ("verifier_error", "verifier_error", False)
    from tests.o2_support import FMT, turns_of, verdict

    found = verdict().verify(None, turns_of(bundle.reference_calls), True, False, FMT)
    assert (found.strict_label, found.label, found.leaky_pass) == ("verifier_error", "verifier_error", False)


def test_the_turn_limit_without_a_reply_is_turn_limit_and_with_the_goal_short_too() -> None:
    bundle = make(fixture_sets()["acme-mcp"], "faults", 0)
    for calls in (bundle.reference_calls, bundle.negative_controls["wrong_state"]):
        found = judge(bundle, calls, reply=False, turn_limit=True)
        assert found.strict_label == "turn_limit"


def test_mutations_count_every_accepted_write() -> None:
    bundle = make(fixture_sets()["acme-mcp"], "faults", 2)
    assert len(judge(bundle, bundle.reference_calls).mutations) == 1
    assert len(judge(bundle, bundle.negative_controls["collateral_mutation"]).mutations) == 2
    assert len(judge(bundle, bundle.negative_controls["wrong_state"]).mutations) == 0


# --------------------------------------------------------------------------
# arguments compare exactly
# --------------------------------------------------------------------------

EXACT = mcp_set(
    write_tool(
        "file_claim",
        {
            "code": {"type": "string", "minLength": 4, "maxLength": 8},
            "count": {"type": "integer", "minimum": 1, "maximum": 9},
            "amount": {"type": "number", "minimum": 0},
            "urgent": {"type": "boolean"},
            "kind": {"type": "string", "enum": ["damage", "loss"]},
            "switch": {"enum": [True, 1]},
            "priority": {"type": "integer", "minimum": 1, "maximum": 3},
            "note": {"type": "string"},
        },
        ["code", "count", "amount", "urgent", "kind", "switch"],
    ),
    read_tool("look", {"key": {"type": "string", "maxLength": 5}}, ["key"]),
    name="claims",
)


def target_call(bundle: Any) -> tuple[str, dict[str, Any]]:
    (call,) = [c for c in bundle.reference_calls if c[0] == bundle.target]
    return (str(call[0]), dict(call[1]))


def with_value(bundle: Any, name: str, value: Any) -> tuple[tuple[str, Any], ...]:
    tool, args = target_call(bundle)
    return tuple((tool, {**args, name: value}) if c[0] == tool else c for c in bundle.reference_calls)


def test_strings_compare_byte_for_byte_numbers_by_value_and_booleans_and_enums_exactly() -> None:
    bundle = make(EXACT, "faults", 0, seed=5)
    _tool, args = target_call(bundle)
    stated = dict(bundle.stated)
    assert set(stated) == {"code", "count", "amount", "urgent", "kind", "switch"}
    assert judge(bundle, bundle.reference_calls).strict_label == "passed"
    as_float = with_value(bundle, "count", float(args["count"]))
    assert judge(bundle, as_float).strict_label == "passed"
    if float(args["amount"]).is_integer():
        assert judge(bundle, with_value(bundle, "amount", int(args["amount"]))).strict_label == "passed"
    cased = args["code"].swapcase() if args["code"].swapcase() != args["code"] else args["code"][:-1] + (
        "x" if args["code"][-1] != "x" else "y")
    for name, value in (("code", cased), ("count", args["count"] % 9 + 1),
                        ("amount", args["amount"] + 0.01), ("urgent", not args["urgent"]),
                        ("kind", "loss" if args["kind"] == "damage" else "damage"),
                        ("switch", 1 if args["switch"] is True else True)):
        found = judge(bundle, with_value(bundle, name, value))
        assert found.strict_label == "wrong_state" and found.leaky_pass is False, (name, value, found)


def test_an_argument_the_request_did_not_state_is_ignored() -> None:
    """Free text, and on any arm but arguments (`test_o2_pending_arguments_unstated.py`) a checkable
    argument too."""
    bundle = make(EXACT, "faults", 0, seed=5)
    assert "note" not in dict(bundle.stated) and "priority" not in dict(bundle.stated)
    for name, value in (("note", "anything"), ("note", ""), ("priority", 1), ("priority", 3)):
        assert judge(bundle, with_value(bundle, name, value)).strict_label == "passed", (name, value)


def test_a_tool_whose_effect_is_unknown_is_treated_as_a_write() -> None:
    """Spec §2.3: a stray accepted call to a tool of unknown effect counts against the model, until
    `tasks.toml` says the tool reads."""
    from poisson_tasks import own

    unknown = own.read_tools(fixture("acme-openai-chat.json"), name="acme").toolset
    declared = own.apply_effects(unknown, read=ACME_READS)
    for toolset, expected in ((unknown, "collateral_mutation"), (declared, "passed")):
        for seed in range(5):
            bundle = make(toolset, "faults", 0, seed=seed)
            stray: tuple[str, dict[str, Any]] = ("list_channels", {})
            assert judge(bundle, bundle.reference_calls + (stray,)).strict_label == expected, seed


def test_a_free_text_argument_of_a_named_read_or_a_chain_step_is_ignored() -> None:
    """§5.2: an argument the request did not state is ignored.  A depth chain's first call here takes
    only free text (`search_orders(query)`), and a spread read may carry an argument beyond the key the
    request names: either way the read still answers with the value the task needs."""
    for seed in range(8):
        bundle = make(acme(), "depth", 3, seed=seed, flows=acme_flows())
        (first, args), *rest = bundle.reference_calls
        assert first == "search_orders"
        other = ((first, {"query": "something else entirely"}), *rest)
        assert judge(bundle, other).strict_label == "passed"
    for seed in range(8):
        bundle = make(acme(), "spread", 2, seed=seed)
        reads = len(bundle.named_reads)
        moved = tuple((name, {**args, "note": "unasked"}) if index < reads else (name, args)
                      for index, (name, args) in enumerate(bundle.reference_calls))
        assert judge(bundle, moved).strict_label == "passed"
