"""TG-M4, the verifiers export: a generated bundle packaged as a verifiers v1 taskset.

The spec is §2.4 -- X1 to X9, the Interface clauses X1 to X9 do not restate (`validate`
and the toolset), and knob R's level axis.  Ten public names, in `__all__`'s order:

| name | what it is |
|---|---|
| `ExportTasksetConfig` | the arm spec and the declared seed list |
| `ExportTaskConfig` | the arm's strictness and id, every field defaulted |
| `ExportTaskData` | the whole bundle, as the wire carries it |
| `ExportTask` | `key`, one reward, four metrics, `toolsets`, `validate` |
| `ExportTaskset` | finite; one task per declared seed, in declared order |
| `DomainToolsetConfig`, `DomainToolset` | the task's tool block, served |
| `task_from_bundle`, `bundle_from_data` | the two directions of X2 |
| `MEASURED_HARNESS` | `"null"` (X9) |

Four things about `verifiers==0.3.1` shape this file and are not obvious from §2.4.  Each
was measured; the evidence is in the vault, under the TG-M4 sessions.

**The bundle's seeded history is not `vf.Messages`.**  TG-M3 froze a D control's prompt in
the OpenAI chat shape (`tool_calls[i].function.name`), and 0.3.1's `vf.ToolCall` is flat
(`name`, `arguments`), so the wheel refuses the prompt as written.  The task data therefore
carries the wheel's shape and `bundle_from_data` restores the OpenAI one; X2 is what holds
both halves honest.  (A note at G13 is owed in the spec.)

**The task data crosses a JSON wire.**  A launched tool server is handed its task as
`model_dump_json`, rebuilt with `model_validate_json` on the data's own class, found by
`module:qualname` -- so every field has to survive JSON, and JSON has no tuple.  The
restoring is in `bundle_from_data` and `_deep_tuple`, not in the field types alone.

**A tool body has to be total.**  FastMCP validates a call's arguments against the
function's signature before the body runs, and a call refused there never reaches `apply`;
the live counter would then trail TG-M1's `replay` by one and every later observation would
differ.  `_EngineTool` hands the raw argument dict to the engine instead, so a bad call
comes back as the engine's own numbered line (§2.4's "tool bodies call `apply`", E5).

**The advertised schema is the bundle's, byte for byte.**  `ToolManager.add_tool` derives a
schema from a function's signature (a `title` per property, no `additionalProperties`),
which is not the bundle's, and it is the manager's only public entry point; `register`
therefore builds the `Tool` itself and puts it in the manager (X3).

Two readings the spec leaves open are not settled here, and the tests do not pin them: where
a call the harness refused sorts (its tool message carries no `seq`, and it mutates nothing
wherever it lands), and how `turn_limit_hit` is read off a trace -- `is_truncated` is the
name §0 verifies, and it is also true for a token limit.
"""

from __future__ import annotations

import asyncio as _asyncio
import dataclasses as _dc
import json as _json
from collections.abc import Iterator as _Iterator
from typing import Any as _Any

import verifiers.v1 as _vf
from mcp.server.fastmcp import FastMCP as _FastMCP
from mcp.server.fastmcp.tools import Tool as _Tool
from pydantic import Field as _Field
from pydantic import model_validator as _model_validator

from poisson_tasks.engine import apply as _apply
from poisson_tasks.engine import init_state as _init_state
from poisson_tasks.knobs import ArmSpec as _ArmSpec
from poisson_tasks.knobs import PinRecord as _PinRecord
from poisson_tasks.knobs import arm_id as _arm_id
from poisson_tasks.tasks import FormatSpec as _FormatSpec
from poisson_tasks.tasks import TaskBundle as _TaskBundle
from poisson_tasks.tasks import Turn as _Turn
from poisson_tasks.tasks import Verdict as _Verdict
from poisson_tasks.tasks import VerifierSpec as _VerifierSpec
from poisson_tasks.tasks import generate as _generate
from poisson_tasks.tasks import scenario_for as _scenario_for
from poisson_tasks.tasks import verify as _verify

__all__ = [
    "ExportTasksetConfig",
    "ExportTaskConfig",
    "ExportTaskData",
    "ExportTask",
    "ExportTaskset",
    "DomainToolsetConfig",
    "DomainToolset",
    "task_from_bundle",
    "bundle_from_data",
    "MEASURED_HARNESS",
]

MEASURED_HARNESS = "null"
"""X9: the harness every pinned measurement was made under.  `docs/verifiers-export.md`
says what a run under another one costs."""

# The reward's own format spec.  The pass predicate is decided before the format check
# (TG-M3's decision 4) and the taskset does not know the serving pin's parser, so the
# export scores with no markers and leaves `malformed_call` to the adapter's own `verify`.
_EXPORT_FORMAT = _FormatSpec(name="export", markers=())


# ---------------------------------------------------------------------------
# configs
# ---------------------------------------------------------------------------


class ExportTaskConfig(_vf.TaskConfig):
    """§2.4: "the strictness and the arm id".

    Every field is defaulted because 0.3.1 builds the declared config type with no
    arguments when a task is constructed without one.
    """

    strictness: str = "strict"
    arm_id: str = ""


class ExportTasksetConfig(_vf.TasksetConfig):
    """§2.4: "the arm spec plus the declared seed list, which is finite in v0".

    `arm` is the six `ArmSpec` fields as a mapping rather than the dataclass, so the
    config stays a plain pydantic model on the wire and under `--env.taskset.arm.*`.
    The `task` config is derived from the arm when the caller gives none: it carries
    exactly what §2.4 says it carries, and the arm already determines both fields.

    A declared list that repeats a seed is refused.  The refusal is forced, not chosen:
    X7 makes keys unique within a taskset, X8 makes `len(list(load()))` the list's
    length, and a repeated seed is a repeated `task_id` -- so both cannot hold for it.
    Only the *place* was open, and the earliest one is here.
    """

    arm: dict[str, _Any] = _Field(default_factory=dict)
    seeds: list[int] = _Field(default_factory=list)

    @_model_validator(mode="before")
    @classmethod
    def _refuse_a_repeat_and_derive_the_task_config(cls, data: _Any) -> _Any:
        if not isinstance(data, dict):
            return data
        seeds = data.get("seeds") or []
        if isinstance(seeds, list) and len(set(seeds)) != len(seeds):
            repeated = sorted({seed for seed in seeds if seeds.count(seed) > 1})
            raise ValueError(
                f"the declared seed list holds {len(seeds)} entries and "
                f"{len(set(seeds))} distinct seeds; each of {repeated} appears more "
                "than once, and one seed is one task"
            )
        arm = data.get("arm")
        if isinstance(arm, dict) and arm and data.get("task") is None:
            spec = _ArmSpec(**arm)
            data["task"] = ExportTaskConfig(
                strictness=spec.strictness, arm_id=_arm_id(spec)
            )
        return data

    def arm_spec(self) -> _ArmSpec:
        """The declared arm, as TG-M2's dataclass."""
        if not self.arm:
            raise ValueError(
                "this taskset config declares no arm: pass "
                "`arm=dataclasses.asdict(spec)` for the ArmSpec the seeds belong to"
            )
        return _ArmSpec(**self.arm)


# ---------------------------------------------------------------------------
# the task data, and the two directions of X2
# ---------------------------------------------------------------------------


class ExportTaskData(_vf.TaskData):
    """The whole bundle.

    §2.4 lists eight of the bundle's twenty-one fields, and X2, X4, X6, X7 and `validate`
    between them need the rest: `task_id` is a content hash over every other field, so a
    round trip that dropped one would not hash equal; `verify` derives the scenario from
    `seed` and `split`; X6 and `validate` score `reference_calls`.  The list reads as
    illustrative under every reading, and a correction to §2.4 is owed in the vault.

    `prompt`, `system_prompt`, `idx` and the rest of `vf.TaskData` come from the base.
    Nothing here is a tuple: the wire is JSON, and `bundle_from_data` restores the
    bundle's tuples on the way back.
    """

    task_id: str = ""
    arm_id: str = ""
    seed: int = 0
    split: str = ""
    scenario_hash: str = ""
    tools: list[dict[str, _Any]] = _Field(default_factory=list)
    seq_start: int = 1
    template_id: str = ""
    prompt_slots: list[list[str]] = _Field(default_factory=list)
    initial_state: list[list[_Any]] = _Field(default_factory=list)
    expected_final_state: list[list[_Any]] = _Field(default_factory=list)
    goal: list[_Any] = _Field(default_factory=list)
    reference_calls: list[list[_Any]] = _Field(default_factory=list)
    reference_observations: list[str] = _Field(default_factory=list)
    negative_controls: dict[str, list[list[_Any]]] = _Field(default_factory=dict)
    strictness: str = "strict"
    pin_arm_id: str = ""
    pin_values: dict[str, _Any] = _Field(default_factory=dict)
    pin_unmeasured: dict[str, str] = _Field(default_factory=dict)
    engine_hash: str = ""
    generator_hash: str = ""


def _deep_tuple(value: _Any) -> _Any:
    """Every list back to a tuple, all the way down.

    The bundle's own list is the tool schema's `required`, which never passes through
    here: the tools are carried as the mappings they are and rebuilt with `dict`.
    """
    if isinstance(value, (list, tuple)):
        return tuple(_deep_tuple(item) for item in value)
    return value


def _call_pair(pair: _Any) -> tuple[str, _Any]:
    """One `(name, arguments)` call, with the arguments as the engine wants them.

    A call's arguments are usually a JSON object and come back as a `dict`.  Clause 2 of
    the format check needs arguments that are *not* an object, and TG-M3 generates a
    control whose arguments are a tuple; JSON has no tuple, so that one arrives as a
    list and is restored here.
    """
    name, arguments = pair
    return (str(name), _deep_tuple(arguments) if isinstance(arguments, list) else arguments)


def _to_wire_message(message: dict[str, _Any]) -> dict[str, _Any]:
    """One seeded message, from TG-M3's OpenAI chat shape into the wheel's.

    Only an assistant message differs: 0.3.1's `vf.ToolCall` is flat, where OpenAI nests
    the name and the arguments under `function`.  An assistant message in the seeded
    history carries tool calls and no content, and the wheel's model leaves `content`
    unset rather than null, which is what makes the trip back exact.
    """
    if message["role"] != "assistant":
        return dict(message)
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "id": call["id"],
                "type": call["type"],
                "name": call["function"]["name"],
                "arguments": call["function"]["arguments"],
            }
            for call in message["tool_calls"]
        ],
    }


def _from_wire_message(message: _Any) -> dict[str, _Any]:
    """The other direction: one `vf` message back into TG-M3's chat shape."""
    if isinstance(message, _vf.AssistantMessage):
        return {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": call.id,
                    "type": call.type,
                    "function": {"name": call.name, "arguments": call.arguments},
                }
                for call in message.tool_calls or []
            ],
        }
    if isinstance(message, _vf.ToolMessage):
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": message.content,
        }
    return {"role": message.role, "content": message.content}


def _data_from_bundle(bundle: _TaskBundle) -> ExportTaskData:
    """X2's forward direction, field for field."""
    prompt: _Any = (
        bundle.prompt
        if isinstance(bundle.prompt, str)
        else [_to_wire_message(message) for message in bundle.prompt]
    )
    return ExportTaskData(
        prompt=prompt,
        system_prompt=bundle.system_prompt,
        task_id=bundle.task_id,
        arm_id=bundle.arm_id,
        seed=bundle.seed,
        split=bundle.split,
        scenario_hash=bundle.scenario_hash,
        tools=[dict(tool) for tool in bundle.tools],
        seq_start=bundle.seq_start,
        template_id=bundle.template_id,
        prompt_slots=[list(slot) for slot in bundle.prompt_slots],
        initial_state=[list(row) for row in bundle.initial_state],
        expected_final_state=[list(row) for row in bundle.expected_final_state],
        goal=list(bundle.goal),
        reference_calls=[list(call) for call in bundle.reference_calls],
        reference_observations=list(bundle.reference_observations),
        negative_controls={
            label: [list(call) for call in calls]
            for label, calls in bundle.negative_controls.items()
        },
        strictness=bundle.verifier.strictness,
        pin_arm_id=bundle.pins.arm_id,
        pin_values=dict(bundle.pins.values),
        pin_unmeasured=dict(bundle.pins.unmeasured),
        engine_hash=bundle.engine_hash,
        generator_hash=bundle.generator_hash,
    )


def bundle_from_data(data: ExportTaskData) -> _TaskBundle:
    """X2's other direction: "task data re-serialised to a bundle".

    The result is equal to the generated bundle, not merely equal under a canonical hash
    -- and the difference is load-bearing.  A rebuilt bundle whose state rows came back
    as lists is refused by TG-M3's `verify` as a defective bundle (`verifier_error`), so
    a consumer that rebuilds one needs the stronger statement.  Every tuple the bundle
    holds is restored here, the pin record's nested ones included; the tool schemas'
    `required` lists stay lists, because that is what the bundle has.
    """
    prompt: _Any = (
        data.prompt
        if isinstance(data.prompt, str)
        else tuple(_from_wire_message(message) for message in data.prompt or [])
    )
    return _TaskBundle(
        task_id=data.task_id,
        arm_id=data.arm_id,
        seed=data.seed,
        split=data.split,
        scenario_hash=data.scenario_hash,
        system_prompt=data.system_prompt or "",
        prompt=prompt,
        tools=tuple(dict(tool) for tool in data.tools),
        seq_start=data.seq_start,
        template_id=data.template_id,
        prompt_slots=tuple(_deep_tuple(slot) for slot in data.prompt_slots),
        initial_state=tuple(_deep_tuple(row) for row in data.initial_state),
        expected_final_state=tuple(_deep_tuple(row) for row in data.expected_final_state),
        goal=_deep_tuple(data.goal),
        reference_calls=tuple(_call_pair(call) for call in data.reference_calls),
        reference_observations=tuple(data.reference_observations),
        negative_controls={
            label: tuple(_call_pair(call) for call in calls)
            for label, calls in data.negative_controls.items()
        },
        verifier=_VerifierSpec(strictness=data.strictness),
        pins=_PinRecord(
            arm_id=data.pin_arm_id,
            values={key: _deep_tuple(value) for key, value in data.pin_values.items()},
            unmeasured=dict(data.pin_unmeasured),
        ),
        engine_hash=data.engine_hash,
        generator_hash=data.generator_hash,
    )


# ---------------------------------------------------------------------------
# the verdict: X4's ordering, then TG-M3's own verifier
# ---------------------------------------------------------------------------


def _seq_of(content: _Any) -> int | None:
    """The `seq` a tool message's observation opens with, or `None`.

    `None` is not an error: under the `null` harness a call whose arguments are not a
    JSON object, or whose name is outside the advertised block, never reaches the tool
    server.  The harness answers it itself with an `error: ...` line that carries no
    number, and the engine's counter does not move.
    """
    if not isinstance(content, str):
        return None
    head = content.split(" ", 1)[0]
    return int(head) if head.isdigit() else None


def _sampled_calls(trace: _Any) -> list[tuple[int | None, tuple[str, _Any]]]:
    """Every sampled tool call with the `seq` of the tool message that follows it.

    `Trace.assistant_messages` is sampled-only, so a control arm's pre-seeded messages
    are excluded by construction (X4) -- but the *tool* messages are not, and the seeded
    history's call ids are `call_0`, `call_1`, ..., which a model's ids can collide with.
    Walking the nodes and consuming each tool message once matches a call to the message
    that follows it rather than to the first one that shares its id.
    """
    open_calls: list[tuple[str, _Any]] = []
    open_ids: list[str] = []
    found: dict[int, int | None] = {}
    for node in trace.nodes:
        message = node.message
        if node.sampled and isinstance(message, _vf.AssistantMessage):
            for call in message.tool_calls or []:
                try:
                    arguments: _Any = _json.loads(call.arguments or "{}")
                except ValueError:
                    arguments = call.arguments
                open_ids.append(call.id)
                open_calls.append((call.name, _deep_tuple(arguments)
                                   if isinstance(arguments, list) else arguments))
        elif isinstance(message, _vf.ToolMessage):
            for index, call_id in enumerate(open_ids):
                if call_id == message.tool_call_id and index not in found:
                    found[index] = _seq_of(message.content)
                    break
    return [(found.get(index), call) for index, call in enumerate(open_calls)]


def _ordered_turns(trace: _Any) -> tuple[tuple[_Turn, ...], bool]:
    """The sampled calls as TG-M3's turns, ordered by X4's key, and whether the episode
    ended with a reply.

    X4 orders the calls "by the `seq` in the matching `Trace.tool_messages` content".  A
    call the harness refused has no such `seq`; it mutates nothing wherever it sorts, so
    it is kept in the position it was sampled in and nothing is pinned on the choice.
    """
    sampled = trace.assistant_messages
    rows = _sampled_calls(trace)
    keys: list[float] = []
    last = -1.0
    for seq, _call in rows:
        key = float(seq) if seq is not None else last + 0.5
        last = max(last, key)
        keys.append(key)
    order = sorted(range(len(rows)), key=lambda index: (keys[index], index))
    turns = [
        _Turn(content="", calls=(rows[index][1],), finish_reason="tool_calls")
        for index in order
    ]
    ended_with_reply = bool(sampled) and not sampled[-1].tool_calls
    if ended_with_reply:
        turns.append(
            _Turn(content=sampled[-1].content or "", calls=(), finish_reason="stop")
        )
    return tuple(turns), ended_with_reply


def _verdict(data: ExportTaskData, trace: _Any) -> _Verdict:
    """TG-M3's verdict on the trace.  The reward is never its own expectation (X4)."""
    turns, ended_with_reply = _ordered_turns(trace)
    return _verify(
        bundle_from_data(data),
        turns,
        ended_with_reply,
        bool(trace.is_truncated),
        _EXPORT_FORMAT,
    )


# ---------------------------------------------------------------------------
# the task
# ---------------------------------------------------------------------------


class ExportTask(_vf.Task[ExportTaskData, _vf.State, ExportTaskConfig]):
    """§2.4's task: one reward, four metrics, the domain toolset and G4.

    The generic parameters are not decoration.  0.3.1 reads a task's data and config
    types off them, and a subclass that leaves them bare gets `vf.TaskData` back -- and
    then rebuilds a launched server's task as a plain `vf.TaskData`, silently dropping
    every bundle field.
    """

    @property
    def key(self) -> str:
        """X7: `key` = `task_id`.

        The wheel's default is a content hash of the wire data, which moves with `idx`
        and with a `TasksetConfig.system_prompt` override; `task_id` is the generator's
        own durable identifier and is what the pin ledger and the adapter both quote.
        """
        return str(self.data.task_id)

    @_vf.reward(weight=1.0)
    async def strict(self, task: ExportTaskData, trace: _vf.Trace) -> float:
        """X4: 1.0 exactly when TG-M3's `verify` gives strict `passed`.

        The one reward, weighing 1.0.  The leaky verdict is descriptive (TG-ADR-08) and
        must not reach `Trace.reward`, which is why `leaky_pass` below is a metric.
        """
        return 1.0 if _verdict(task, trace).strict_label == "passed" else 0.0

    @_vf.metric
    async def leaky_pass(self, task: ExportTaskData, trace: _vf.Trace) -> float:
        """The leaky predicate, reported beside the strict one and never summed in."""
        return 1.0 if _verdict(task, trace).leaky_pass else 0.0

    @_vf.metric
    async def mutation_count(self, task: ExportTaskData, trace: _vf.Trace) -> float:
        """§2.4's "mutation count": `len(Verdict.mutations)`, TG-M3's own count.

        It counts `(class, id, field)` triples, three to a successful transition, and it
        still reports the audit field, because it is diagnostic and not the predicate
        (TG-ADR-40).
        """
        return float(len(_verdict(task, trace).mutations))

    @_vf.metric
    async def sampled_calls(self, trace: _vf.Trace) -> float:
        """§2.4's "sampled calls": tool calls on sampled assistant messages only."""
        return float(sum(len(message.tool_calls or []) for message in trace.assistant_messages))

    @_vf.metric
    async def turns(self, trace: _vf.Trace) -> float:
        """§2.4's "turns": the trace's own count of sampled nodes."""
        return float(trace.num_turns)

    @classmethod
    def toolsets(cls, config: ExportTaskConfig) -> list[_vf.Toolset]:
        """§2.4: "the domain toolset, which is task-scoped (per rollout)".

        A new toolset on every call: two rollouts of one task must not share a record or
        a counter.  A classmethod, so a consumer can size placement before any task
        instance exists.
        """
        return [DomainToolset(DomainToolsetConfig())]

    async def validate(self, runtime: _Any) -> bool:
        """G4: under *both* strictnesses, `verify` on `reference_calls` gives `passed`.

        Both, whatever the arm declares.  Under a leaky arm a reference that does
        collateral damage is labelled `passed` and still fails G4, because strict does
        not pass it -- and a leaky arm's tasks are compared with a strict arm's.

        `runtime` is unused, so this scores offline with `None`; 0.3.1's signature is a
        coroutine returning `bool`.
        """
        bundle = bundle_from_data(self.data)
        turns = tuple(
            _Turn(content="", calls=(call,), finish_reason="tool_calls")
            for call in bundle.reference_calls
        ) + (_Turn(content="", calls=(), finish_reason="stop"),)
        for strictness in ("strict", "leaky"):
            probe = _dc.replace(bundle, verifier=_VerifierSpec(strictness=strictness))
            verdict = _verify(probe, turns, True, False, _EXPORT_FORMAT)
            if verdict.label != "passed" or verdict.strict_label != "passed":
                return False
        return True


def task_from_bundle(bundle: _TaskBundle) -> ExportTask:
    """One generated bundle as one task.  §2.5's model target calls this at its step 3.

    It does not re-check G4: generation already refuses a bundle that fails it, and
    `validate` is where the export says so.
    """
    return ExportTask(
        _data_from_bundle(bundle),
        ExportTaskConfig(strictness=bundle.verifier.strictness, arm_id=bundle.arm_id),
    )


# ---------------------------------------------------------------------------
# the taskset
# ---------------------------------------------------------------------------


class ExportTaskset(_vf.Taskset[ExportTask, ExportTasksetConfig]):
    """§2.4: finite, one task per declared seed, via `generate`.

    In the order declared, and in no other: nothing here reorders a measurement's tasks,
    and the module calls nothing named `shuffle` (X8).  `Taskset.shuffle` is an
    inherited view this class cannot remove, and `eval --shuffle` is the user's flag;
    what the measurement path iterates is TG-M5's concern, not this class's.
    """

    INFINITE = False

    def load(self) -> _Iterator[ExportTask]:
        arm = self.config.arm_spec()
        for seed in self.config.seeds:
            yield task_from_bundle(_generate(arm, seed))


# ---------------------------------------------------------------------------
# the toolset
# ---------------------------------------------------------------------------


class DomainToolsetConfig(_vf.ToolsetConfig):
    """The toolset takes no configuration: the task's data is the whole input, and it
    arrives through `setup_task`.  `ToolsetConfig`'s own `runtime` defaults to the
    subprocess one, so the server launches locally with nothing declared."""


class _EngineTool(_Tool):
    """A FastMCP tool that advertises the bundle's schema and is total over any call.

    `Tool.run` validates the arguments against the function's signature first, and a
    call refused there never reaches the body.  TG-M1's `apply` is total and advances
    `seq` on every call, errors included (E5), so a call that fails its own schema has
    to come back as the engine's numbered line and not as a FastMCP error: otherwise the
    live counter trails `replay` by one and every later observation differs, which
    TG-M5's replay check would read as an instrument failure.
    """

    async def run(
        self,
        arguments: dict[str, _Any],
        context: _Any = None,
        convert_result: bool = False,
    ) -> _Any:
        observation = await self.fn(arguments)
        if convert_result:
            return self.fn_metadata.convert_result(observation)
        return observation


class DomainToolset(_vf.Toolset[DomainToolsetConfig, _vf.State]):
    """§2.4's toolset: the task's block, served over MCP, backed by TG-M1's engine.

    `TOOL_PREFIX = None` advertises the names bare -- the block's names are the
    bundle's, and a `<server>_` prefix would rewrite the prompt's tool list.

    The engine state lives on this instance and not in `vf.State` (TG-ADR-07): the
    wheel's state sync is last-write-wins around every call, and a chain of transitions
    does not compose under that.  Declaring a `State` subclass would also switch the
    sync on.
    """

    TOOL_PREFIX = None

    def __init__(self, config: DomainToolsetConfig) -> None:
        super().__init__(config)
        self._block: tuple[dict[str, _Any], ...] = ()
        self._engine_state: _Any = None
        self._lock = _asyncio.Lock()

    async def setup_task(self, task: _Any) -> None:
        """§2.4: "builds the engine state from the task data".

        `seq_start` included: a depth control's counter starts past 1, because its
        seeded history already spent the turns it stands in for.
        """
        self._block = tuple(dict(tool) for tool in task.tools)
        self._engine_state = _init_state(
            _scenario_for(task.seed, task.split), task.seq_start
        )

    def register(self, mcp: _FastMCP) -> None:
        """§2.4: the task's block, in slot order, "because `setup_task` runs first".

        Not the base implementation: that discovers `@vf.tool`-decorated methods, and
        the block's names are not known until the task is.  Not `add_tool` either: it
        derives a schema from the body's signature, and X3 wants the bundle's exactly.
        """
        for spec in self._block:
            mcp._tool_manager._tools[str(spec["name"])] = self._tool(spec)

    def _tool(self, spec: dict[str, _Any]) -> _EngineTool:
        """One advertised tool, with the bundle's name, description and schema."""
        name = str(spec["name"])
        description = str(spec["description"])

        async def body(arguments: _Any) -> str:
            # The lock is §2.4's "under an in-process lock": `apply` is pure, and the
            # counter lives in the state this coroutine reads and then writes, so two
            # calls that interleave between the two would take the same `seq` (E5).
            async with self._lock:
                state = self._engine_state
                after, observation = _apply(state, (name, arguments))
                self._engine_state = after
                return observation

        derived = _Tool.from_function(body, name=name, description=description)
        return _EngineTool(
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
    # 0.3.1 launches a task-scoped tool server as `python -m <the toolset's module>`; the
    # child then fetches its task over the `/task` channel and registers the block.
    DomainToolset.run()
