"""The verifiers export of tasks on a user's own tools: the taskset, the task, its data and the
tool server.

The built-in export's task data mirrors the built-in bundle's fields and has nowhere to carry a
tool file, its toolset builds its state from the engine, and its reward goes through
`tasks.verify`; so own tools have a task data class, a task, a taskset and a toolset of their
own.  The taskset's id is `poisson-tasks-own`, the second top-level module of the wheel
(`poisson_tasks_own`; decided 2026-10-13): verifiers 0.3.1 finds a taskset by a top-level
module only.  Its config carries `own`, the tool file's settings as a resolved plan carries them
(`file`, `format`, `name`, `read`, `write`, `intents`, `flows`, `file_digest`), the arm and the
seeds; it loads one task per seed in the declared order, and refuses a file whose bytes no longer
have the digest the plan was made with.

The wire is JSON: `bundle_from_data(task_from_bundle(bundle).data)` is the bundle, field for
field, after `model_dump_json` and `model_validate_json`, the tuples restored here.  The tool
server advertises the task's block byte for byte and answers with the simulator: each answer a
`CallToolResult` with its text, its `structuredContent` and its `isError`, which FastMCP passes
through unchanged; the body is total, the raw arguments handed to the simulator, so a call that
breaks the schema is answered `invalid_arguments` and counted as the replay counts it.  The
answer is the object alone, no sequence number.  `tests/test_o2_server.py` and
`tests/test_o2_run.py` pin this.
"""

from __future__ import annotations

import asyncio as _asyncio
import dataclasses as _dc
import hashlib as _hashlib
from collections.abc import Iterator as _Iterator
from pathlib import Path as _Path
from typing import Any as _Any

import verifiers.v1 as _vf
from mcp.server.fastmcp import FastMCP as _FastMCP
from mcp.server.fastmcp.tools import Tool as _Tool
from mcp.types import CallToolResult as _CallToolResult
from mcp.types import TextContent as _TextContent
from pydantic import Field as _Field

from poisson_tasks import own as _own
from poisson_tasks.export import _from_wire_message, _ordered_turns, _to_wire_message
from poisson_tasks.knobs import ArmSpec as _ArmSpec
from poisson_tasks.own import generator as _generator
from poisson_tasks.own import simulator as _sim
from poisson_tasks.own.generator import GENERATOR_VERSION as _GENERATOR_VERSION
from poisson_tasks.own.generator import Flow as _Flow
from poisson_tasks.own.generator import OwnBundle as _OwnBundle
from poisson_tasks.own.verdict import verify as _verify
from poisson_tasks.tasks import FormatSpec as _FormatSpec
from poisson_tasks.tasks import Turn as _Turn
from poisson_tasks.tasks import Verdict as _Verdict

__all__ = [
    "OWN_TASKSET_ID",
    "OwnTasksetConfig",
    "OwnTaskData",
    "OwnTask",
    "OwnTaskset",
    "OwnToolsetConfig",
    "OwnToolset",
    "task_from_bundle",
    "bundle_from_data",
]

OWN_TASKSET_ID = "poisson-tasks-own"
_EXPORT_FORMAT = _FormatSpec(name="export", markers=())
_OWN_KEYS = ("file", "format", "name", "read", "write", "intents", "flows", "file_digest")


# ---------------------------------------------------------------------------
# configs
# ---------------------------------------------------------------------------


class OwnTaskConfig(_vf.TaskConfig):
    """The task's config: the strictness and the arm id, every field defaulted."""

    strictness: str = "strict"
    arm_id: str = ""


class OwnTasksetConfig(_vf.TasksetConfig):
    """The taskset's config: the tool file's settings (`own`), the arm and the seeds."""

    own: dict[str, _Any] = _Field(
        default_factory=dict,
        description=(
            "The tool file's settings as a resolved plan carries them: file (an absolute path),"
            " format, name, read, write, intents, flows (from/field/to/param tables) and"
            " file_digest, the SHA-256 of the file the plan was made with."
        ),
    )
    arm: dict[str, _Any] = _Field(
        default_factory=dict,
        description=("The arm: the six ArmSpec fields as one JSON object, at generator "
                     f"{_GENERATOR_VERSION}."),
    )
    seeds: list[int] = _Field(
        default_factory=list,
        description="The task seeds: one task per seed, in the order given, no repeats.",
    )
    task: OwnTaskConfig = _Field(default_factory=OwnTaskConfig)

    def arm_spec(self) -> _ArmSpec:
        if not self.arm:
            raise ValueError("this taskset config declares no arm")
        return _ArmSpec(**self.arm)


# ---------------------------------------------------------------------------
# the task data, and the two directions of the wire
# ---------------------------------------------------------------------------


class OwnTaskData(_vf.TaskData):
    """One task as the wire carries it: every field of the bundle, nothing a tuple."""

    task_id: str = ""
    arm_id: str = ""
    seed: int = 0
    split: str = ""
    strictness: str = "strict"
    set_name: str = ""
    source_format: str = ""
    file_digest: str = ""
    generator_hash: str = ""
    form: str = ""
    request: str = ""
    tools: list[dict[str, _Any]] = _Field(default_factory=list)
    target: str = ""
    target_tool: str = ""
    stated: list[list[_Any]] = _Field(default_factory=list)
    named_reads: list[list[_Any]] = _Field(default_factory=list)
    fault_plan: dict[str, int] = _Field(default_factory=dict)
    reference_calls: list[list[_Any]] = _Field(default_factory=list)
    reference_observations: list[str] = _Field(default_factory=list)
    negative_controls: dict[str, list[list[_Any]]] = _Field(default_factory=dict)
    effects: list[list[str]] = _Field(default_factory=list)
    output_schemas: list[list[_Any]] = _Field(default_factory=list)
    steps: list[dict[str, _Any]] = _Field(default_factory=list)


def _call_pair(pair: _Any) -> tuple[str, _Any]:
    """One `(name, arguments)` call; a control's arguments that are not an object came as a
    tuple and arrive as a list."""
    name, arguments = pair
    return (str(name), tuple(arguments) if isinstance(arguments, list) else arguments)


def _data_from_bundle(bundle: _OwnBundle) -> OwnTaskData:
    prompt: _Any = (
        bundle.prompt if isinstance(bundle.prompt, str)
        else [_to_wire_message(dict(message)) for message in bundle.prompt]
    )
    return OwnTaskData(
        prompt=prompt,
        system_prompt=bundle.system_prompt,
        task_id=bundle.task_id,
        arm_id=bundle.arm_id,
        seed=bundle.seed,
        split=bundle.split,
        strictness=bundle.strictness,
        set_name=bundle.set_name,
        source_format=bundle.source_format,
        file_digest=bundle.file_digest,
        generator_hash=bundle.generator_hash,
        form=bundle.form,
        request=bundle.request,
        tools=[dict(tool) for tool in bundle.tools],
        target=bundle.target,
        target_tool=bundle.target_tool,
        stated=[[name, value] for name, value in bundle.stated],
        named_reads=[[tool, args, field] for tool, args, field in bundle.named_reads],
        fault_plan=dict(bundle.fault_plan),
        reference_calls=[list(call) for call in bundle.reference_calls],
        reference_observations=list(bundle.reference_observations),
        negative_controls={label: [list(call) for call in calls]
                           for label, calls in bundle.negative_controls.items()},
        effects=[[name, effect] for name, effect in bundle.effects],
        output_schemas=[[name, schema] for name, schema in bundle.output_schemas],
        steps=[dict(step) for step in bundle.steps],
    )


def bundle_from_data(data: _Any) -> _Any:
    """The bundle a task's data carries, every tuple restored."""
    prompt: _Any = (
        data.prompt if isinstance(data.prompt, str)
        else tuple(_from_wire_message(message) for message in data.prompt or [])
    )
    return _OwnBundle(
        task_id=data.task_id,
        arm_id=data.arm_id,
        seed=data.seed,
        split=data.split,
        strictness=data.strictness,
        set_name=data.set_name,
        source_format=data.source_format,
        file_digest=data.file_digest,
        generator_hash=data.generator_hash,
        form=data.form,
        system_prompt=data.system_prompt or "",
        request=data.request,
        prompt=prompt,
        tools=tuple(dict(tool) for tool in data.tools),
        target=data.target,
        target_tool=data.target_tool,
        stated=tuple((str(name), value) for name, value in data.stated),
        named_reads=tuple((str(tool), args, str(field)) for tool, args, field in data.named_reads),
        fault_plan=dict(data.fault_plan),
        reference_calls=tuple(_call_pair(call) for call in data.reference_calls),
        reference_observations=tuple(data.reference_observations),
        negative_controls={label: tuple(_call_pair(call) for call in calls)
                           for label, calls in data.negative_controls.items()},
        effects=tuple((str(name), str(effect)) for name, effect in data.effects),
        output_schemas=tuple((str(name), schema) for name, schema in data.output_schemas),
        steps=tuple(dict(step) for step in data.steps),
    )


# ---------------------------------------------------------------------------
# the verdict and the task
# ---------------------------------------------------------------------------


def _verdict(data: OwnTaskData, trace: _Any) -> _Verdict:
    """The own verdict on a trace: the sampled calls in the order the harness sent them."""
    turns, ended_with_reply = _ordered_turns(trace)
    verdict: _Verdict = _verify(bundle_from_data(data), turns, ended_with_reply,
                                trace.stop_condition == "max_turns", _EXPORT_FORMAT)
    return verdict


class OwnTask(_vf.Task[OwnTaskData, _vf.State, OwnTaskConfig]):
    """One task: its key, its reward and metrics, its toolset and G4."""

    @property
    def key(self) -> str:
        return str(self.data.task_id)

    @_vf.reward(weight=1.0)
    async def strict(self, task: OwnTaskData, trace: _vf.Trace) -> float:
        return 1.0 if _verdict(task, trace).strict_label == "passed" else 0.0

    @_vf.metric
    async def leaky_pass(self, task: OwnTaskData, trace: _vf.Trace) -> float:
        return 1.0 if _verdict(task, trace).leaky_pass else 0.0

    @_vf.metric
    async def mutation_count(self, task: OwnTaskData, trace: _vf.Trace) -> float:
        return float(len(_verdict(task, trace).mutations))

    @_vf.metric
    async def sampled_calls(self, trace: _vf.Trace) -> float:
        return float(sum(len(message.tool_calls or []) for message in trace.assistant_messages))

    @_vf.metric
    async def turns(self, trace: _vf.Trace) -> float:
        return float(trace.num_turns)

    @classmethod
    def toolsets(cls, config: OwnTaskConfig) -> list[_vf.Toolset]:
        """A toolset of its own for every rollout."""
        return [OwnToolset(OwnToolsetConfig())]

    async def validate(self, runtime: _Any) -> bool:
        """G4: under both strictnesses, the reference verifies as passed."""
        bundle = bundle_from_data(self.data)
        turns = tuple(
            _Turn(content="", calls=(call,), finish_reason="tool_calls")
            for call in bundle.reference_calls
        ) + (_Turn(content="", calls=(), finish_reason="stop"),)
        for strictness in ("strict", "leaky"):
            probe = _dc.replace(bundle, strictness=strictness)
            verdict = _verify(probe, turns, True, False, _EXPORT_FORMAT)
            if verdict.label != "passed" or verdict.strict_label != "passed":
                return False
        return True


def task_from_bundle(bundle: _Any) -> OwnTask:
    """One own-tools bundle as one task."""
    return OwnTask(
        _data_from_bundle(bundle),
        OwnTaskConfig(strictness=bundle.strictness, arm_id=bundle.arm_id),
    )


# ---------------------------------------------------------------------------
# the taskset
# ---------------------------------------------------------------------------


def _toolset_of(own: dict[str, _Any]) -> _own.OwnToolSet:
    """The tool set the plan's `own` names, read again and checked against the digest the plan
    was made with, with the declared effects applied."""
    missing = [key for key in _OWN_KEYS if key not in own]
    if missing:
        raise ValueError("the taskset's own settings lack " + ", ".join(missing))
    path = _Path(str(own["file"]))
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ValueError(f"the tool file {path} cannot be read: {error}") from None
    digest = _hashlib.sha256(data).hexdigest()
    if digest != own["file_digest"]:
        raise ValueError(
            f"the tool file {path} has changed since the plan was made (sha256 {digest[:12]}, the"
            f" plan's {str(own['file_digest'])[:12]}): its tasks changed, so make the plan again"
        )
    reading = _own.read_tools(data, format=str(own["format"]), name=str(own["name"]))
    return _own.apply_effects(reading.toolset, read=list(own["read"]), write=list(own["write"]))


class OwnTaskset(_vf.Taskset[OwnTask, OwnTasksetConfig]):
    """One task per declared seed, in the order declared."""

    INFINITE = False

    def __iter__(self) -> _Iterator[OwnTask]:
        if not self.config.own:
            raise ValueError("no tool file given: the taskset's own settings are empty")
        if not self.config.arm:
            raise ValueError("no arm given: pass the arm's six fields as one JSON object")
        if not self.config.seeds:
            raise ValueError("no seeds given: each seed is one task")
        tasks: _Iterator[OwnTask] = super().__iter__()
        return tasks

    def load(self) -> _Iterator[OwnTask]:
        own = dict(self.config.own)
        toolset = _toolset_of(own)
        arm = self.config.arm_spec()
        flows = tuple(_Flow(str(f["from"]), str(f["field"]), str(f["to"]), str(f["param"]))
                      for f in own["flows"])
        intents = {str(k): str(v) for k, v in dict(own["intents"]).items()}
        for seed in self.config.seeds:
            yield task_from_bundle(
                _generator.generate(toolset, arm, int(seed), intents=intents, flows=flows)
            )


# ---------------------------------------------------------------------------
# the toolset
# ---------------------------------------------------------------------------


class OwnToolsetConfig(_vf.ToolsetConfig):
    """The toolset takes no configuration: the task's data is the whole input."""


class _OwnTool(_Tool):
    """A FastMCP tool that advertises the bundle's schema and is total over any call."""

    async def run(
        self,
        arguments: dict[str, _Any],
        context: _Any = None,
        convert_result: bool = False,
    ) -> _Any:
        result = await self.fn(arguments)
        if convert_result:
            return self.fn_metadata.convert_result(result)
        return result


class OwnToolset(_vf.Toolset[OwnToolsetConfig, _vf.State]):
    """The task's block, served, answered by the simulator."""

    TOOL_PREFIX = None

    def __init__(self, config: OwnToolsetConfig) -> None:
        super().__init__(config)
        self._bundle: _Any = None
        self._state: _sim.State | None = None
        self._lock = _asyncio.Lock()

    async def setup_task(self, task: _Any) -> None:
        self._bundle = bundle_from_data(task)
        self._state = _sim.start(self._bundle)

    def register(self, mcp: _FastMCP) -> None:
        for spec in self._bundle.tools:
            mcp._tool_manager._tools[str(spec["name"])] = self._tool(dict(spec))

    def _tool(self, spec: dict[str, _Any]) -> _OwnTool:
        name = str(spec["name"])
        description = str(spec["description"])

        async def body(arguments: _Any) -> _Any:
            async with self._lock:
                assert self._state is not None
                self._state, answer = _sim.step(self._bundle, self._state, (name, arguments))
            return _CallToolResult(
                content=[_TextContent(type="text", text=answer.text)],
                structuredContent=None if answer.structured is None else dict(answer.structured),
                isError=answer.is_error,
            )

        derived = _Tool.from_function(body, name=name, description=description)
        return _OwnTool(
            fn=body,
            name=name,
            title=None,
            description=description,
            parameters=dict(spec["parameters"]),
            fn_metadata=derived.fn_metadata,
            is_async=True,
            context_kwarg=None,
            annotations=None,
        )


if __name__ == "__main__":
    # 0.3.1 launches a task-scoped tool server as `python -m <the toolset's module>`.
    OwnToolset.run()

