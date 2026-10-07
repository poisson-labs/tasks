"""What the faults knob's test files share: the arms and seeds they read, the base task they
compare with, the tool server run in this process, and an episode written as a run's trace.

The test files are `tests/test_k3_*.py`; each says in its own docstring what it pins and what it
decided.  Nothing here asserts anything.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

import verifiers.v1 as vf
from mcp.server.fastmcp import FastMCP
from verifiers.v1.cli.output import append_trace

from poisson_tasks import calibration as cal
from poisson_tasks import export
from poisson_tasks.arms import arm_from_id
from poisson_tasks.engine import EngineSpec, apply, init_state
from poisson_tasks.tasks import FormatSpec, TaskBundle, Turn, generate, scenario_for, verify
from tests.helpers import seeded_nodes

SPEC = EngineSpec.load()
LEVELS = (0, 1, 2, 4)
CONTROL = "faults:f0+len(f4)"
B_ARM = "distractor:r0@k16"
CARD_SEEDS: tuple[int, ...] = cal.seed_list()
FMT = FormatSpec(name="reference", markers=())

# Spec §6.3's sentence, as the spec prints it.
SENTENCE = (
    "A call can come back `unavailable`: nothing changed, and the same call can be made again."
)
UNAVAILABLE = "unavailable"

# The `null` harness's own answers to a call it does not forward, from verifiers 0.3.1's
# `harnesses/null/program.py`.  Only their opening matters to anything here.
REFUSED = "error: "


def arm(level: int) -> str:
    return f"faults:f{level}"


@lru_cache(maxsize=4096)
def made(arm_id: str, seed: int, split: str = "eval") -> TaskBundle:
    return generate(arm_from_id(arm_id, split=split), seed)


def faults(level: int, seed: int, split: str = "eval") -> TaskBundle:
    return made(arm(level), seed, split)


def base(seed: int, split: str = "eval") -> TaskBundle:
    """B, the base task the faults knob measures departures from: `distractor:r0@k16`."""
    return made(B_ARM, seed, split)


def names(bundle: Any) -> tuple[str, ...]:
    return tuple(str(tool["name"]) for tool in bundle.tools)


def status(observation: str) -> str:
    fields = observation.split()
    return fields[1] if len(fields) > 1 and fields[0].isdigit() else ""


def seq(observation: str) -> int:
    return int(observation.split()[0])


def right(bundle: Any) -> tuple[tuple[str, Any], tuple[str, Any]]:
    """The two right calls, the first stage's and the second's, as B's reference makes them."""
    first, second = base(bundle.seed, bundle.split).reference_calls
    return (first[0], dict(first[1])), (second[0], dict(second[1]))


def a_read(bundle: Any) -> tuple[str, dict[str, str]]:
    """A read in the block that the engine answers `ok`: a call to the wrong tool, harmless."""
    scenario = scenario_for(bundle.seed, bundle.split)
    state = init_state(scenario, 1)
    for name in names(bundle):
        if name not in SPEC.read_tools:
            continue
        for item in scenario.visible_items:
            for page in sorted(SPEC.page_keys):
                args = {SPEC.parameter_names["item"]: item, SPEC.parameter_names["page"]: page}
                if apply(state, (name, args))[1].split()[1] == "ok":
                    return name, args
    raise AssertionError("no read in the block answers ok")


def turns_of(calls: Sequence[tuple[str, Any]], reply: bool = True) -> tuple[Turn, ...]:
    turns = [Turn(content="", calls=(call,), finish_reason="tool_calls") for call in calls]
    if reply:
        turns.append(Turn(content="Done.", calls=(), finish_reason="stop"))
    return tuple(turns)


def verdict_of(
    bundle: Any, calls: Sequence[tuple[str, Any]], *, reply: bool = True, limit: bool = False
) -> Any:
    return verify(bundle, turns_of(calls, reply), reply, limit, FMT)


# --------------------------------------------------------------------------
# the tool server, in this process
# --------------------------------------------------------------------------


def run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


def started(bundle: Any) -> FastMCP:
    """The export's tool server for one task, set up as a launched one is."""
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


def forwarded(bundle: Any, name: Any, args: Any) -> bool:
    """Whether the `null` harness hands a call to the tool server: its arguments are a JSON object
    and its name is one the block shows (`harnesses/null/program.py`)."""
    return isinstance(args, dict) and name in names(bundle)


def answers(bundle: Any, calls: Sequence[tuple[str, Any]]) -> list[str]:
    """What each call's tool message holds: the tool server's answer for a call the harness
    forwards, in one server for the episode, and the harness's own refusal otherwise."""
    mcp = started(bundle)
    out: list[str] = []
    for name, args in calls:
        if forwarded(bundle, name, args):
            out.append(call(mcp, name, args))
        else:
            out.append(f"{REFUSED}the harness answered this call itself")
    return out


# --------------------------------------------------------------------------
# an episode as a run's trace
# --------------------------------------------------------------------------


def trace_of(
    bundle: Any, calls: Sequence[tuple[str, Any]], contents: Sequence[str], *, reply: bool = True
) -> Any:
    """A `vf.Trace` in verifiers 0.3.1's shape: the task's own prompt, one sampled assistant
    message per call with its tool message holding `contents[i]`, then a reply, scored offline by
    the task itself."""
    task = export.task_from_bundle(bundle)
    nodes = seeded_nodes(task)
    for index, ((name, args), content) in enumerate(zip(calls, contents, strict=True)):
        arguments = args if isinstance(args, str) else json.dumps(args)
        message = vf.AssistantMessage(
            content=None,
            tool_calls=[vf.ToolCall(id=f"call_k3_{index}", name=name, arguments=arguments)],
        )
        nodes.append(vf.MessageNode(parent=len(nodes) - 1, message=message, sampled=True))
        answer = vf.ToolMessage(tool_call_id=f"call_k3_{index}", content=content)
        nodes.append(vf.MessageNode(parent=len(nodes) - 1, message=answer, sampled=False))
    if reply:
        done = vf.AssistantMessage(content="Done.")
        nodes.append(vf.MessageNode(parent=len(nodes) - 1, message=done, sampled=True))
    trace = vf.Trace(
        task=vf.TraceTask(type=type(task).__name__, data=task.data, key=task.key, hash=task.hash),
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        nodes=nodes,
        ok=True,
        is_completed=True,
    )
    run(task.score(trace, None))
    return trace


def run_dir_of(tmp_path: Path, *traces: Any) -> Path:
    """Each trace as one episode of a run directory, written by the wheel's own writer."""
    out = tmp_path / f"run{len(list(tmp_path.glob('run*')))}"
    out.mkdir()
    lock = asyncio.Lock()
    for trace in traces:
        run(append_trace(out, trace, lock))
    return out


def records_of(tmp_path: Path, *traces: Any) -> list[cal.EpisodeRecord]:
    return cal.records_from_run(run_dir_of(tmp_path, *traces), model="m")


def episode(tmp_path: Path, bundle: Any, calls: Sequence[tuple[str, Any]]) -> Any:
    """One episode whose tool messages are the tool server's answers, read back as its record."""
    (record,) = records_of(tmp_path, trace_of(bundle, calls, answers(bundle, calls)))
    return record


# The two names K3 adds, read by name: no skeleton declares them, so on a tree without K3 a test
# that reads one fails because it is missing.
GAVE_UP = "gave_up_after_fault"
APPLY_PLANNED = "apply_planned"


def gave_up(record: Any) -> Any:
    """The record's `gave_up_after_fault`."""
    return vars(record)[GAVE_UP]


def record_with(**fields: Any) -> cal.EpisodeRecord:
    """An `EpisodeRecord` built from its fields by name, `gave_up_after_fault` among them."""
    return cal.EpisodeRecord(**fields)


def written(record: Any) -> dict[str, Any]:
    """A record's written line, as a mapping."""
    loaded: dict[str, Any] = json.loads(cal.EpisodeRecord.to_json(record))
    return loaded
