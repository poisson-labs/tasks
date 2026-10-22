"""The export of tasks on a user's own tools: its taskset, its task, its tool server and the replay
of a run, frozen as tests.

The invariant: the export's tool server serves an own-tools task's block byte for byte and replays
to the verdict's observations on a fake endpoint.  The design: the package has its own task data
class, task, verdict and toolset, since the built-in export's cannot carry a tool file, and the own
toolset answers MCP's `isError` and `structuredContent` where the built-in one cannot.

Shapes decided here
-------------------

**1. `poisson_tasks.own.export`** holds `OWN_TASKSET_ID`, `OwnTasksetConfig`, `OwnTaskData`,
`OwnTask`, `OwnTaskset`, `OwnToolsetConfig`, `OwnToolset`, `task_from_bundle` and
`bundle_from_data`.  `OWN_TASKSET_ID` names the taskset verifiers' loader finds, with the
package's own `Env` (the measured `null` harness): which id is the pending file
`test_o2_pending_taskset_id.py`.

**2. The wire.**  `bundle_from_data(task_from_bundle(bundle).data)` is the bundle, field for
field, after the data has crossed JSON (`model_dump_json`, then `model_validate_json`), as a
launched tool server receives it.  `OwnTask.key` is the task id.

**3. The served block** is the task's `tools`, each advertised with its name, its description and
its argument schema exactly; an answer is the simulator's: its text the tool message, its
`structured` the result's `structuredContent`, its `is_error` the result's `isError`.  Each rollout
gets a toolset of its own.

**4. The taskset's config** carries `own`, the tool file's settings as a resolved plan carries
them (at least `file`, an absolute path, `format`, `name`, `read`, `write`, `intents`, `flows` as
`from`/`field`/`to`/`param` tables, and `file_digest`; a plan's `own` holds more, which the taskset
reads past), `arm` and `seeds`; it loads one task per
seed in the order declared, and refuses a file whose bytes no longer have the digest the plan
was made with.

A live run through the `null` harness on a fake endpoint, its replay and a planted change are in
`tests/test_o2_run.py`, which runs a plan end to end.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import own
from tests.o1_support import fixture
from tests.o2_support import (
    acme,
    acme_flows,
    arm,
    every_arm,
    export,
    fixture_sets,
    flows_for,
    generator,
    make,
)


def run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


async def _session_calls(bundle: Any, calls: list[tuple[str, Any]]) -> tuple[list[Any], list[Any]]:
    from mcp.server.fastmcp import FastMCP
    from mcp.shared.memory import create_connected_server_and_client_session

    task = export().task_from_bundle(bundle)
    (toolset,) = type(task).toolsets(task.config)
    mcp = FastMCP(toolset.server_name)
    await toolset.setup()
    await toolset.setup_task(task.data)
    toolset.register(mcp)
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        listed = (await client.list_tools()).tools
        results = [await client.call_tool(name, args) for name, args in calls]
    return listed, results


def served(bundle: Any, calls: list[tuple[str, Any]]) -> tuple[list[Any], list[Any]]:
    listed, results = run(_session_calls(bundle, calls))
    return list(listed), list(results)


def text_of(result: Any) -> str:
    (block,) = result.content
    return str(block.text)


# --------------------------------------------------------------------------
# the served block and its answers
# --------------------------------------------------------------------------


@pytest.mark.parametrize("label", ["acme-mcp", "acme-openai", "acme-openapi-3.0", "petstore", "everything"])
def test_the_server_advertises_the_block_byte_for_byte(label: str) -> None:
    toolset, flows = fixture_sets()[label], flows_for(label)
    for spec in every_arm(toolset, flows)[::3]:
        bundle = generator().generate(toolset, spec, 4, flows=flows)
        listed, _results = served(bundle, [])
        assert [(t.name, t.description, t.inputSchema) for t in listed] == [
            (str(t["name"]), str(t["description"]), dict(t["parameters"])) for t in bundle.tools], spec


@pytest.mark.parametrize("label", ["acme-mcp", "acme-openai", "acme-openapi-3.1", "petstore"])
def test_the_servers_answers_to_the_reference_are_the_verdicts_observations(label: str) -> None:
    toolset, flows = fixture_sets()[label], flows_for(label)
    for spec in every_arm(toolset, flows):
        bundle = generator().generate(toolset, spec, 6, flows=flows)
        _listed, results = served(bundle, list(bundle.reference_calls))
        assert [text_of(r) for r in results] == list(bundle.reference_observations), spec


def test_an_mcp_tool_answers_with_structured_content_and_an_mcp_error_with_is_error() -> None:
    from tests.o2_support import answers

    bundle = next(b for b in (make(acme("mcp"), "faults", 2, seed=seed) for seed in range(100))
                  if b.target == "refund_order")

    expected = answers(bundle, list(bundle.reference_calls))
    _listed, results = served(bundle, list(bundle.reference_calls))
    for result, answer in zip(results, expected, strict=True):
        assert bool(result.isError) == answer.is_error
        assert result.structuredContent == (None if answer.structured is None else dict(answer.structured))
    assert results[0].isError is True and results[-1].isError is not True
    assert results[-1].structuredContent == json.loads(text_of(results[-1]))


def test_a_call_whose_arguments_break_the_schema_is_answered_by_the_simulator_not_refused() -> None:
    """The arguments go to the simulator as they came, so a call that breaks the schema is answered
    `invalid_arguments` and counted, as the replay counts it."""
    bundle = make(acme("openai"), "faults", 0, seed=8)
    bad: tuple[str, dict[str, Any]] = (bundle.target, {})
    _listed, results = served(bundle, [bad, *bundle.reference_calls])
    assert json.loads(text_of(results[0]))["error"]["code"] == "invalid_arguments"
    assert [text_of(r) for r in results[1:]] == list(bundle.reference_observations)


def test_each_rollout_gets_a_toolset_of_its_own() -> None:
    bundle = make(acme(), "faults", 1, seed=2)
    task = export().task_from_bundle(bundle)
    first = type(task).toolsets(task.config)
    second = type(task).toolsets(task.config)
    assert first[0] is not second[0]
    _listed, again = served(bundle, list(bundle.reference_calls))
    assert [text_of(r) for r in again] == list(bundle.reference_observations)


# --------------------------------------------------------------------------
# the wire and the task
# --------------------------------------------------------------------------


def test_the_task_data_crosses_the_json_wire_and_comes_back_the_bundle() -> None:
    x = export()
    for label in ("acme-mcp", "acme-openai", "petstore"):
        toolset, flows = fixture_sets()[label], flows_for(label)
        for spec in every_arm(toolset, flows):
            bundle = generator().generate(toolset, spec, 11, flows=flows)
            task = x.task_from_bundle(bundle)
            wired = x.OwnTaskData.model_validate_json(task.data.model_dump_json())
            assert x.bundle_from_data(wired) == bundle, spec
            assert task.key == bundle.task_id
            assert task.data.system_prompt == bundle.system_prompt


def test_validate_is_g4_and_fails_a_task_whose_reference_does_not_pass() -> None:
    x = export()
    for spec in every_arm(acme(), acme_flows())[::2]:
        bundle = generator().generate(acme(), spec, 3, flows=acme_flows())
        assert run(x.task_from_bundle(bundle).validate(None)) is True
        short = dataclasses.replace(bundle, reference_calls=bundle.negative_controls["wrong_state"])
        assert run(x.task_from_bundle(short).validate(None)) is False
        extra = dataclasses.replace(bundle, reference_calls=bundle.negative_controls["collateral_mutation"])
        assert run(x.task_from_bundle(extra).validate(None)) is False


def test_the_taskset_id_resolves_to_the_own_taskset_and_the_measured_env() -> None:
    from verifiers.v1.utils.loaders import environment_class, taskset_class

    from poisson_tasks.taskset import PoissonTasksEnv

    x = export()
    assert taskset_class(x.OWN_TASKSET_ID) is x.OwnTaskset
    assert environment_class(x.OWN_TASKSET_ID) is PoissonTasksEnv


def own_settings(path: Path, **extra: Any) -> dict[str, Any]:
    data = path.read_bytes()
    return {"file": str(path), "format": "auto", "name": "acme-support", "read": [], "write": [],
            "intents": {}, "flows": [], "file_digest": hashlib.sha256(data).hexdigest(), **extra}


def test_the_taskset_loads_one_task_per_seed_in_the_declared_order(tmp_path: Path) -> None:
    x = export()
    path = tmp_path / "tools.json"
    path.write_bytes(fixture("acme-mcp-tools-list.json"))
    flows = [{"from": f.from_tool, "field": f.field, "to": f.to_tool, "param": f.param} for f in acme_flows()]
    intents = {"refund_order": "refund a customer's order"}
    spec = arm("depth", 3)
    config = x.OwnTasksetConfig(own=own_settings(path, flows=flows, intents=intents),
                                arm=dataclasses.asdict(spec), seeds=[55, 404, 7])
    loaded = list(x.OwnTaskset(config).load())
    toolset = own.read_tools(path.read_bytes(), name="acme-support").toolset
    expected = [generator().generate(toolset, spec, seed, intents=intents, flows=acme_flows())
                for seed in (55, 404, 7)]
    assert [x.bundle_from_data(task.data) for task in loaded] == expected


def test_the_taskset_applies_the_declared_effects(tmp_path: Path) -> None:
    x = export()
    path = tmp_path / "tools.json"
    path.write_bytes(fixture("acme-openai-chat.json"))
    settings = own_settings(path, read=["get_order", "search_orders", "list_channels"])
    config = x.OwnTasksetConfig(own=settings, arm=dataclasses.asdict(arm("history", 300)), seeds=[9])
    (task,) = list(x.OwnTaskset(config).load())
    assert x.bundle_from_data(task.data) == generator().generate(acme("openai"), arm("history", 300), 9)


def test_a_tool_file_changed_since_the_plan_is_refused_in_one_line(tmp_path: Path) -> None:
    x = export()
    path = tmp_path / "tools.json"
    path.write_bytes(fixture("acme-mcp-tools-list.json"))
    settings = own_settings(path)
    path.write_bytes(fixture("acme-mcp-tools-list.json") + b"\n")
    config = x.OwnTasksetConfig(own=settings, arm=dataclasses.asdict(arm("faults", 1)), seeds=[1])
    with pytest.raises(ValueError) as refused:
        list(x.OwnTaskset(config).load())
    assert "\n" not in str(refused.value)


def test_a_taskset_with_no_file_no_arm_or_no_seeds_is_refused_before_a_task_is_made(tmp_path: Path) -> None:
    x = export()
    path = tmp_path / "tools.json"
    path.write_bytes(fixture("acme-mcp-tools-list.json"))
    good = {"own": own_settings(path), "arm": dataclasses.asdict(arm("faults", 1)), "seeds": [1]}
    assert len(list(iter(x.OwnTaskset(x.OwnTasksetConfig(**good))))) == 1
    for missing in ("own", "arm", "seeds"):
        config = x.OwnTasksetConfig(**{k: v for k, v in good.items() if k != missing})
        with pytest.raises(ValueError):
            list(iter(x.OwnTaskset(config)))
