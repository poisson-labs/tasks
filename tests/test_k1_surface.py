"""The shared surface: what a block shows, and what answers in front of the engine, frozen as
tests.

`poisson_tasks.surface` is a private module the generator, `tasks.verify` and the export's tool
server all read, so the three agree by construction.  It holds the keyed draw every seed-derived
choice uses (moved out of `tasks.py`, which imports it), `display_map`, and `fault_plan`.

Shapes decided here
-------------------

**1. `display_map(seed, split, arm_id, goal, tools)`** maps each name in `tools` -- the names a
block shows, in block order -- to a `Shown(engine, description)`: the engine's name for it, and
the description the block gives it when that is not the engine's own (`None` otherwise).  It
takes the tool list as an argument, so a block that is not the built-in one works unchanged.
For every knob built so far the names map to themselves; for the spread knob the target
ledger's first stage tool is given a description that no longer says its code is stated in the
request.

**2. The seam is `poisson_tasks.surface.display_map`, read through the module when a task is
verified or served.**  Every knob built so far maps names to themselves, so the only way to show
that the verifier and the tool server translate names through the map, and do not map names of
their own, is to replace the map: a test here shows both under a map that renames one tool.

**3. A called name the block does not show changes nothing.**  `verify` used to replay every call
through the engine, so a call to a real engine tool outside the block -- which the harness
refuses and the server never sees -- still moved records in the replay.  Now it reaches the
engine as a name the engine does not know.  The format check still reports the call.

**4. `fault_plan(arm_id, path)`** gives, for a faults arm, how many times each tool on the
reference path answers `unavailable` before it works: the level split over the path's tools as
evenly as it goes, the earlier tools taking the extra (with two tools, the first stage takes the
odd one).  Tools planned no failure are left out, and an arm of any other knob plans none.
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP

from poisson_tasks import export, surface
from poisson_tasks import tasks as tasks_module
from poisson_tasks.arms import arm_from_id
from poisson_tasks.engine import EngineSpec
from poisson_tasks.tasks import FormatSpec, Turn, generate, verify

REPO = Path(__file__).resolve().parent.parent
SPEC = EngineSpec.load()
SEED = 404
FMT = FormatSpec(name="reference", markers=())
IDENTITY_ARMS = ("depth:d3", "depth:d1+h8", "distractor:r4@k16", "distractor:r0+len(r8)@k16",
                 "faults:f2", "faults:f0+len(f4)", "history:t600", "arguments:a6",
                 "arguments:a2+len(a8)", "shape:w2", "shape:w1+len(w4)", "spread:p2")
OWN_TOOLS = ("lookup_order", "refund_order", "notify_customer")


def run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


def base(arm: str = "distractor:r0@k16") -> Any:
    return generate(arm_from_id(arm), SEED)


def names(bundle: Any) -> tuple[str, ...]:
    return tuple(tool["name"] for tool in bundle.tools)


def verdict_of(bundle: Any, calls: Any) -> Any:
    turns = tuple(Turn(content="", calls=(call,), finish_reason="tool_calls") for call in calls)
    return verify(bundle, turns, True, False, FMT)


# --------------------------------------------------------------------------
# the keyed draw lives in one place
# --------------------------------------------------------------------------


def test_the_keyed_draw_is_surfaces_and_tasks_keeps_no_copy() -> None:
    assert vars(tasks_module)["_prf"] is surface._prf
    tree = ast.parse((REPO / "src" / "poisson_tasks" / "tasks.py").read_text())
    defined = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    assigned = {target.id for node in tree.body if isinstance(node, ast.Assign)
                for target in node.targets if isinstance(target, ast.Name)}
    assert "_prf" not in defined and "_DRAW_KEY" not in assigned


# --------------------------------------------------------------------------
# the display map
# --------------------------------------------------------------------------


@pytest.mark.parametrize("arm", IDENTITY_ARMS)
def test_every_knob_built_so_far_shows_the_engines_names(arm: str) -> None:
    bundle = base()
    shown = surface.display_map(SEED, "eval", arm, bundle.goal, names(bundle))
    assert list(shown) == list(names(bundle))
    assert all(entry.engine == name for name, entry in shown.items())
    if not arm.startswith("spread"):
        assert all(entry.description is None for entry in shown.values())


def first_stage(bundle: Any) -> str:
    return next(n for n, (i, q) in SPEC.stage_tools.items() if i == 0 and q == bundle.goal[0])


def test_spread_describes_the_first_stage_tool_as_taking_the_assembled_code() -> None:
    bundle = base()
    stage = first_stage(bundle)
    engine_description = next(t.description for t in SPEC.tools if t.name == stage)
    descriptions = set()
    for arm in ("spread:p1", "spread:p2", "spread:p4"):
        shown = surface.display_map(SEED, "eval", arm, bundle.goal, names(bundle))
        assert [n for n, e in shown.items() if e.description is not None] == [stage]
        descriptions.add(shown[stage].description)
    (description,) = descriptions
    assert description is not None and description != engine_description
    assert "stated in the request" in engine_description
    assert "stated in the request" not in description


def test_the_map_works_on_a_block_that_is_not_the_built_in_one() -> None:
    goal = ("orders", "order-17", 1)
    for arm in ("faults:f2", "history:t300", "arguments:a4", "block:k8"):
        shown = surface.display_map(7, "eval", arm, goal, OWN_TOOLS)
        assert {name: entry.engine for name, entry in shown.items()} == {n: n for n in OWN_TOOLS}


# --------------------------------------------------------------------------
# verify and the tool server read the map, and only the map
# --------------------------------------------------------------------------


ALIAS = "begin_the_review"


@lru_cache(maxsize=1)
def renamed() -> tuple[Any, str]:
    """A real task whose first stage tool is shown under a name the engine does not have."""
    bundle = base()
    stage = bundle.reference_calls[0][0]
    tools = tuple({**tool, "name": ALIAS} if tool["name"] == stage else tool
                  for tool in bundle.tools)
    calls = tuple((ALIAS if name == stage else name, args)
                  for name, args in bundle.reference_calls)
    return dataclasses.replace(bundle, tools=tools, reference_calls=calls), stage


@pytest.fixture
def aliased_map(monkeypatch: pytest.MonkeyPatch) -> str:
    """`display_map` replaced by one that shows the first stage tool as `ALIAS`."""
    _bundle, stage = renamed()
    real = surface.display_map

    def shown(seed: int, split: str, arm_id: str, goal: Any, tools: Any) -> Any:
        out = real(seed, split, arm_id, goal, tuple(stage if n == ALIAS else n for n in tools))
        return {(ALIAS if name == stage else name): entry for name, entry in out.items()}

    monkeypatch.setattr(surface, "display_map", shown)
    return stage


def test_verify_replays_a_shown_name_as_the_engine_name_the_map_gives(aliased_map: str) -> None:
    bundle, _stage = renamed()
    got = verdict_of(bundle, bundle.reference_calls)
    assert (got.strict_label, got.format_clause) == ("passed", None)


def test_without_the_map_the_shown_name_reaches_no_engine_tool() -> None:
    bundle, _stage = renamed()
    got = verdict_of(bundle, bundle.reference_calls)
    assert got.strict_label == "wrong_state" and got.mutations == ()


def started(bundle: Any) -> FastMCP:
    task = export.task_from_bundle(bundle)
    (toolset,) = type(task).toolsets(task.config)
    mcp = FastMCP(toolset.server_name)

    async def start() -> None:
        await toolset.setup()
        await toolset.setup_task(task.data)

    run(start())
    toolset.register(mcp)
    return mcp


def call(mcp: FastMCP, name: str, args: Any) -> str:
    result = run(mcp.call_tool(name, args))
    if isinstance(result, tuple):
        result = result[0]
    (block,) = list(result)
    return str(block.text)


def test_the_tool_server_applies_the_engine_name_the_map_gives(aliased_map: str) -> None:
    bundle, _stage = renamed()
    mcp = started(bundle)
    listed = [tool.name for tool in run(mcp.list_tools())]
    assert listed == list(names(bundle))
    observations = [call(mcp, name, args) for name, args in bundle.reference_calls]
    assert observations == list(bundle.reference_observations)


def test_without_the_map_the_server_answers_the_shown_name_as_no_tool() -> None:
    bundle, _stage = renamed()
    mcp = started(bundle)
    name, args = bundle.reference_calls[0]
    assert call(mcp, name, args).split()[1] == "no_such_tool"


# --------------------------------------------------------------------------
# a name the block does not show changes nothing
# --------------------------------------------------------------------------


@pytest.mark.parametrize("arm", ["depth:d2", "distractor:r0@k16", "distractor:r8@k16",
                                 "depth:d2+h5"])
def test_a_call_to_a_real_tool_outside_the_block_mutates_nothing(arm: str) -> None:
    """Another ledger's first stage tool, which the engine would run on the target id with the
    scenario's code: outside every depth and distractor block it is refused by the harness, so
    the replay must not let it change a record either."""
    bundle = base(arm)
    cls, record, _goal = bundle.goal
    shown = set(names(bundle))
    outside = next(n for n, (i, q) in SPEC.stage_tools.items()
                   if i == 0 and q != cls and n not in shown)
    code = bundle.reference_calls[0][1]["entry_code"]
    calls = list(bundle.reference_calls) + [(outside, {"record_id": record, "entry_code": code})]
    got = verdict_of(bundle, calls)
    assert got.format_clause == 3
    assert {(c, r) for c, r, _field in got.mutations} == {(cls, record)}
    assert got.strict_label == "passed" and got.leaky_pass


# --------------------------------------------------------------------------
# the fault plan
# --------------------------------------------------------------------------


@pytest.mark.parametrize("arm, plan", [
    ("faults:f0", {}),
    ("faults:f1", {"refund_order": 1}),
    ("faults:f2", {"refund_order": 1, "notify_customer": 1}),
    ("faults:f4", {"refund_order": 2, "notify_customer": 2}),
    ("faults:f3", {"refund_order": 2, "notify_customer": 1}),
    ("faults:f0+len(f4)", {}),
    ("history:t300", {}),
    ("depth:d2", {}),
])
def test_the_fault_plan_splits_the_level_over_the_path_first_stage_taking_the_odd_one(
    arm: str, plan: dict[str, int]
) -> None:
    assert surface.fault_plan(arm, ("refund_order", "notify_customer")) == plan


def test_the_fault_plan_takes_any_path_of_tools() -> None:
    """A path of one tool takes every failure; a longer one spreads them, earliest first; a tool
    called twice on the path is one tool."""
    assert surface.fault_plan("faults:f4", ("refund_order",)) == {"refund_order": 4}
    path = ("lookup_order", "refund_order", "notify_customer")
    assert surface.fault_plan("faults:f4", path) == {
        "lookup_order": 2, "refund_order": 1, "notify_customer": 1}
    assert surface.fault_plan("faults:f4", ("refund_order", "notify_customer", "refund_order")) == {
        "refund_order": 2, "notify_customer": 2}
