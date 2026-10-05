"""The verifier reads a task's targets from its records, and the argument check takes optional
parameters, frozen as tests.

Two changes to `tasks.verify` that the new knobs need, and that give today's verdict on every
task generated so far:

* **Targets.**  A task's targets are the records whose stage differs between its
  `initial_state` and its `expected_final_state`.  Leaky passes when every target reached its
  goal stage (its stage in the expected records); a change to any record that is not a target is
  collateral; a target short of its goal is `wrong_state`, and one past it is `overshoot`.  The
  shape knob needs this, because at its wider widths a task moves more than one record.  `goal`
  keeps its shape and names the first target.
* **Argument check.**  A call's arguments pass the schema clause when every required key is
  present, no key falls outside the tool's properties, and every value is a string.  Every
  schema generated so far requires all of its properties, so for those this is the old rule,
  "exactly the properties"; the argument knob needs it, because its stage tools list parameters
  a call may leave out.

What "today's verdict" is compared against
------------------------------------------

`tests/fixtures/k1/published-tasks.json.gz` (see `tests/test_k1_content.py`) holds, for each of
the 840 published tasks, the verdict the generator before the change gave on every negative
control the task carries and on sixteen random call sequences, all computed by that tree's own
`verify`.  The sequences were drawn with a seeded generator from calls a model could make inside
the block: prefixes of the reference solution with up to three calls inserted from a pool of the
decoy's first stage, wrong entry codes and tokens, missing, extra and non-string arguments,
arguments that are not an object, a call past the goal where the block holds one, and reads; and
each ends with a reply, at the turn limit, or with neither.  None names a tool outside the block:
that is the one place the rule moves on purpose (`tests/test_k1_surface.py`), and nothing here
should pass or fail because of it.

Shapes decided here
-------------------

**1. One call per turn, no format markers.**  The fixture's verdicts were computed so; the
format's markers decide only clause 1, which no change here touches.

**2. A turn-limit control ends at the limit and every other control with a reply**, as the
negative controls are labelled.
"""

from __future__ import annotations

import dataclasses
import gzip
import json
from functools import lru_cache, cache
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks.arms import arm_from_id
from poisson_tasks.engine import EngineSpec, replay
from poisson_tasks.tasks import FormatSpec, Turn, generate, scenario_for, verify

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "k1" / "published-tasks.json.gz"
FMT = FormatSpec(name="reference", markers=())
SPEC = EngineSpec.load()


@lru_cache(maxsize=1)
def fixture() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(gzip.decompress(FIXTURE.read_bytes()))
    return doc


@cache
def bundle_for(arm: str, seed: int) -> Any:
    return generate(arm_from_id(arm), seed)


def turns_of(calls: Any) -> tuple[Turn, ...]:
    return tuple(Turn(content="", calls=(tuple(call),), finish_reason="tool_calls")
                 for call in calls)


def verdict(bundle: Any, calls: Any, ended_with_reply: bool = True,
            turn_limit_hit: bool = False) -> dict[str, Any]:
    v = verify(bundle, turns_of(calls), ended_with_reply, turn_limit_hit, FMT)
    return {"strict_label": v.strict_label, "leaky_pass": v.leaky_pass, "label": v.label,
            "mutations": [list(m) for m in v.mutations], "format_clause": v.format_clause}


# --------------------------------------------------------------------------
# today's verdict, on every published task
# --------------------------------------------------------------------------


def test_every_negative_control_of_every_published_task_keeps_its_verdict() -> None:
    changed = []
    for entry in fixture()["tasks"]:
        bundle = bundle_for(entry["arm_id"], entry["seed"])
        assert sorted(bundle.negative_controls) == sorted(entry["control_verdicts"])
        for key, calls in bundle.negative_controls.items():
            limit = key == "turn_limit"
            got = verdict(bundle, calls, ended_with_reply=not limit, turn_limit_hit=limit)
            if got != entry["control_verdicts"][key]:
                changed.append((entry["arm_id"], entry["seed"], key, got))
    assert not changed, changed[:5]


def test_random_call_sequences_on_every_published_task_keep_their_verdict() -> None:
    changed, labels = [], set()
    for entry in fixture()["tasks"]:
        bundle = bundle_for(entry["arm_id"], entry["seed"])
        for sequence in entry["sequences"]:
            got = verdict(bundle, sequence["calls"], sequence["ended_with_reply"],
                          sequence["turn_limit_hit"])
            labels.add(got["strict_label"])
            if got != sequence["verdict"]:
                changed.append((entry["arm_id"], entry["seed"], sequence["calls"], got))
    assert not changed, changed[:5]
    # The sample reaches every label a call sequence can produce, or it would pin less than it
    # claims to.
    assert labels == {"passed", "malformed_call", "turn_limit", "overshoot", "wrong_state",
                      "collateral_mutation", "verifier_error"}


# --------------------------------------------------------------------------
# targets: more than one record
# --------------------------------------------------------------------------

SEED = 404


def chain(bundle: Any, record: str, depth: int) -> list[tuple[str, dict[str, str]]]:
    """`depth` stage calls on `record` in the task's ledger, each with the token the one before
    returned, worked out on the engine."""
    cls = bundle.goal[0]
    tools = sorted((index, name) for name, (index, q) in SPEC.stage_tools.items() if q == cls)
    scenario = scenario_for(bundle.seed, bundle.split)
    calls: list[tuple[str, dict[str, str]]] = []
    for stage in range(depth):
        if stage == 0:
            args = {"record_id": record, "entry_code": scenario.records[(cls, record)]}
        else:
            _state, observations = replay(scenario, calls, bundle.seq_start)
            args = {"record_id": record, "chain_token": observations[-1].split()[2]}
        calls.append((tools[stage][1], args))
    return calls


@lru_cache(maxsize=1)
def two_targets() -> tuple[Any, str, str]:
    """A depth-3 task whose expected records also move the ledger's other record (the decoy) to
    stage 2, so it has two targets with different goals; and the two record ids."""
    bundle = generate(arm_from_id("depth:d3"), SEED)
    cls, record, _goal = bundle.goal
    decoy = next(r for c, r, _s, _t in bundle.initial_state if c == cls and r != record)
    scenario = scenario_for(bundle.seed, bundle.split)
    state, _ = replay(scenario, list(bundle.reference_calls) + chain(bundle, decoy, 2),
                      bundle.seq_start)
    expected = tuple(sorted((c, r, e.stage, e.token) for (c, r), e in state.records.items()))
    return dataclasses.replace(bundle, expected_final_state=expected), record, decoy


def test_a_task_with_two_targets_passes_only_when_both_reach_their_goals() -> None:
    bundle, _record, decoy = two_targets()
    both = list(bundle.reference_calls) + chain(bundle, decoy, 2)
    got = verdict(bundle, both)
    assert (got["strict_label"], got["leaky_pass"], got["label"]) == ("passed", True, "passed")
    # The goal field keeps its shape and names the first target; the second target is read from
    # the records.
    assert bundle.goal[2] == 3 and len(bundle.goal) == 3


def test_a_second_target_short_of_its_goal_is_wrong_state_and_not_leaky() -> None:
    bundle, _record, decoy = two_targets()
    for calls in (list(bundle.reference_calls),
                  list(bundle.reference_calls) + chain(bundle, decoy, 1)):
        got = verdict(bundle, calls)
        assert (got["strict_label"], got["leaky_pass"]) == ("wrong_state", False), calls


def test_a_target_past_its_goal_is_overshoot_and_leaky() -> None:
    bundle, _record, decoy = two_targets()
    calls = list(bundle.reference_calls) + chain(bundle, decoy, 3)
    got = verdict(bundle, calls)
    assert (got["strict_label"], got["leaky_pass"]) == ("overshoot", True)


def test_a_change_to_a_record_that_is_no_target_is_collateral() -> None:
    bundle, _record, decoy = two_targets()
    other = next(c for c, _r, _s, _t in bundle.initial_state if c != bundle.goal[0])
    stage_one = next(n for n, (i, q) in SPEC.stage_tools.items() if i == 0 and q == other)
    # The other ledger's first-stage tool is outside a depth block, so the bundle is widened to
    # show it: the point is the label, not the block.
    shown = dataclasses.replace(
        bundle,
        tools=bundle.tools + ({"name": stage_one, "description": "d", "parameters": {
            "type": "object", "properties": {"record_id": {"type": "string"},
                                             "entry_code": {"type": "string"}},
            "required": ["record_id", "entry_code"], "additionalProperties": False}},),
    )
    scenario = scenario_for(bundle.seed, bundle.split)
    calls = list(bundle.reference_calls) + chain(bundle, decoy, 2) + [
        (stage_one, {"record_id": decoy, "entry_code": scenario.records[(other, decoy)]})]
    got = verdict(shown, calls)
    assert (got["strict_label"], got["leaky_pass"]) == ("collateral_mutation", True)
    assert [other, decoy, "stage"] in got["mutations"]


def test_a_goal_that_is_not_one_of_the_targets_makes_a_defective_bundle() -> None:
    """The goal field names the first target; a bundle whose goal the records do not move to
    that stage is defective, an instrument condition and not a failed episode."""
    bundle = generate(arm_from_id("depth:d3"), SEED)
    cls, record, _goal = bundle.goal
    for goal in ((cls, record, 8), (cls, "no-such-record", 3)):
        got = verdict(dataclasses.replace(bundle, goal=goal), bundle.reference_calls)
        assert (got["strict_label"], got["leaky_pass"]) == ("verifier_error", False), goal
    two, _record, decoy = two_targets()
    second = next((c, r, s) for c, r, s, _t in two.expected_final_state if r == decoy and s)
    got = verdict(dataclasses.replace(two, goal=second),
                  list(two.reference_calls) + chain(two, decoy, 2))
    assert got["strict_label"] == "passed"


# --------------------------------------------------------------------------
# the argument check: required keys, nothing extra, strings
# --------------------------------------------------------------------------


def optional_bundle() -> tuple[Any, str]:
    """A real task whose first stage tool lists a third, optional parameter."""
    bundle = generate(arm_from_id("depth:d2"), SEED)
    name = bundle.reference_calls[0][0]
    tools = []
    for tool in bundle.tools:
        if tool["name"] == name:
            tool = json.loads(json.dumps(tool))
            tool["parameters"]["properties"]["lot_code"] = {"type": "string"}
        tools.append(tool)
    return dataclasses.replace(bundle, tools=tuple(tools)), name


@pytest.mark.parametrize("extra, fires", [
    ({}, False),
    ({"lot_code": "amber"}, False),
    ({"lot_code": 7}, True),
    ({"batch_code": "amber"}, True),
])
def test_an_optional_parameter_may_be_left_out_but_not_invented_or_mistyped(
    extra: dict[str, Any], fires: bool
) -> None:
    bundle, name = optional_bundle()
    first, rest = bundle.reference_calls[0], list(bundle.reference_calls[1:])
    calls = [(name, {**first[1], **extra})] + rest
    got = verdict(bundle, calls)
    assert (got["format_clause"] == 4) is fires, got


def test_a_required_parameter_left_out_still_fires_the_argument_clause() -> None:
    bundle, name = optional_bundle()
    args = dict(bundle.reference_calls[0][1])
    args.pop("record_id")
    got = verdict(bundle, [(name, {**args, "lot_code": "amber"})])
    assert got["format_clause"] == 4
