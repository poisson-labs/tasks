"""The verifiers export (export.py): bundles packaged as a verifiers v1 taskset -- data, task,
toolset and rewards -- and its tests.

The invariants this file is built against are X1-X9, the clauses of the export's written
interface that X1-X9 do not restate (`validate`, the toolset's `setup_task`, `register` and
its tool bodies), and knob R's level axis, which the export's and the model path's
requirements say these tests inherit.  The requirements are not edited here.  Where they
name a thing and give it no shape, this docstring gives it one, with the reason and an
escape hatch.  **Where they are ambiguous, or disagree with themselves or with the pinned
wheel, nothing here settles it**: the test pins only what every reading shares, and the
open point is listed under *Open, and not settled here*.

**No test here needs Proofload.**  The task generator is standalone and Proofload is an
optional extra, so this file imports neither `proofload` nor `poisson_tasks.adapter`
(`test_pv2`), and the module it tests may import neither (`test_mp6_1` in
`tests/test_tg_m5_standalone.py`, whose walk covers the export module).
`verifiers==0.3.1` is a plain dependency and the tests drive the installed wheel.

Every test reaches the module through `importlib`, inside `export()`, so the file collects
on a tree that has no `poisson_tasks.export` and its tests fail there for that one reason.

Shapes decided here
-------------------

**1. The module is `poisson_tasks.export`, with ten public names.**  `ExportTasksetConfig`,
`ExportTaskConfig`, `ExportTaskData`, `ExportTask`, `ExportTaskset`, `DomainToolsetConfig`,
`DomainToolset`, `task_from_bundle`, `bundle_from_data` and `MEASURED_HARNESS`.  The
written interface names five classes and spells none, and a name not on the verified-names
list is a placeholder that may be renamed one for one.  The two functions are the two
directions X2 cannot be tested without, and `task_from_bundle` is also the model path's
step that builds the export task.  Every imported name is underscore-aliased, as in `knobs.py`,
`tasks.py` and `adapter.py`, so SF2 holds.  *Escape hatch:* rename any of the ten; SF1 and
the `export()` helper move.

**2. `ExportTasksetConfig(arm=..., seeds=[...])`.**  `arm` takes the six `ArmSpec` fields as
a mapping (`dataclasses.asdict(spec)`), `seeds` is the declared list, and the `task` config
is derived from the arm when the caller does not give one: its `arm_id` is knobs.py's
`arm_id(spec)` and its `strictness` the arm's.  A declared list that repeats a seed is
refused with a `ValueError`, somewhere between building the config and the end of
`load()`: X7 (unique keys) and X8 (`len(list(load()))` equals the list's
length) cannot both hold for it, so the refusal is forced and only its place is open.
*Escape hatch:* the field names live in `taskset_config()`.

**3. The task data carries the whole bundle, not only the eight fields listed.**  See
*Open* item 1: this is forced by X2, X4, X6 and X7 under every reading, and the tests reach
the data only through `bundle_from_data`, `model_dump_json` and four fields the list does name
(`prompt`, `system_prompt`, `tools`, `seq_start`).

**4. X2 is measured three ways.**  `bundle_from_data(task.data) == bundle` (dataclass
equality, the strongest statement and the one a consumer needs: a rebuilt bundle whose
state rows came back as lists is refused by `verify` as a defective bundle); the same after
the data has crossed the JSON wire, because `model_dump_json` then `model_validate_json` is
how 0.3.1 hands a launched toolset its task; and equality of a canonical hash, the
requirement's own word, under the task layer's canonical form restated in this file.
*Escape hatch:* if "hashes equal" is read as the ceiling, `test_x2_1` and `test_x2_2` relax
to `test_x2_3`'s form.

**5. A D control's seeded prompt is converted, because the wheel refuses it as written.**
The task layer froze the seeded history in the OpenAI chat shape (`tool_calls[i].function.name`),
and `verifiers==0.3.1`'s `vf.ToolCall` is flat (`name`, `arguments`), so
`vf.TaskData(prompt=bundle.prompt)` raises a validation error (measured).  The task data's
`prompt` is therefore `vf.Messages`, and `bundle_from_data` restores the OpenAI shape
exactly.  X2 is what pins both halves; every X2 test runs over both D controls.

**6. A synthetic trace is built as the `null` harness would have left it.**  One sampled
assistant message per call, then its tool message.  A call whose arguments are not a JSON
object, or whose name is outside the block, never reaches the tool server under `null` at
0.3.1: the harness answers it with an `error: ...` string that carries no `seq`, and the
engine's counter does not move.  Every other call gets the live engine's observation.  The
helper `live_observations` reproduces that.  The trace's seeded (prompt-supplied) messages
are nodes with `sampled=False`, which is the wheel's own provenance signal.

**7. X4's expected value is the task layer's `verify`, called by the test on turns built
straight from the calls.**  The module under test is never the source of its own expectation.
`leaky_pass` is held to `verify`'s `leaky_pass` on every trace that ends with a reply, and
on a reference trace (X6).

**8. The diagnostic metrics are named `mutation_count`, `sampled_calls` and `turns`.**
`mutation_count` is `len(Verdict.mutations)`, the only public count tasks.py offers;
`sampled_calls` is the number of tool calls on sampled assistant messages; `turns` is
`Trace.num_turns`.  *Escape hatch:* `METRICS` and `test_x6_2`.

**9. `validate` re-checks G4 and `task_from_bundle` does not.**  G4 is "under both
strictnesses, `verify` on `reference_calls` returns `passed`", so a bundle whose reference
does collateral damage fails it even when the bundle's own strictness is leaky.  A task can be
built from a bundle that fails G4 (generation already refuses one; `validate` is where the
export says so).  *Escape hatch:* `test_val2`, `test_val3`.

**10. "Launching the toolset" is tested twice.**  In process, over every arm: construct,
`setup_task`, `register` on a `FastMCP`, `list_tools` -- which is 0.3.1's own start order.
And once for real: `verifiers.v1.mcp.serve` starts the toolset's module as a child process,
which fetches its task over the `/task` channel the way a rollout's server does, and the
tools are listed over MCP (`test_x3_5`).  That needs the module to run as `__main__`.

**11. The tool bodies are total.**  A tool body calls `apply`, and the engine's `apply`
is total and advances `seq` on every call (E5).  FastMCP validates arguments against the
function's signature before the body runs unless the module prevents it, and a call refused
there never reaches `apply`: the live counter then trails the task layer's replay by one and
every later observation differs, which the adapter's replay check (A8) would label
`replay_mismatch`.
So a call that fails its own schema must come back as the engine's observation
(`test_ts2`).

**12. The harness declaration is a constant and a document.**  `MEASURED_HARNESS == "null"`,
and `docs/verifiers-export.md` states the three things X9 lists.  The run-time default --
`eval` on this taskset runs `null` with no harness named -- is the taskset's own `Env`,
tested in `tests/test_tg_m5_standalone.py` (MP3).

Open, and not settled here
--------------------------

1. **The written list of task-data fields is eight of the bundle's twenty-one**, and X2, X4, X6,
   X7 and `validate` between them need the rest (`task_id` covers every other field;
   `verify` needs `seed` and `split`; X6 needs `reference_calls`).  The tests need only that
   the round trip holds.  **Not pinned:** whether altered task data yields an altered
   bundle, which is what would tell "carries the bundle" from "carries `(arm, seed)` and
   regenerates".
2. **X4's order key is missing for a call the harness refused.**  Its tool message has no
   `seq` (decision 6).  Such a call mutates nothing wherever it is placed, so the verdict
   does not depend on the answer; the tests need only that the reward returns 0.0 and does
   not raise.  **Not pinned:** where such a call sorts.
3. **Whether a `TasksetConfig.system_prompt` override is refused.**  It rewrites N3's pinned
   system prompt while the key stays the `task_id`.  **Not pinned.**
4. **A `task` config that disagrees with the arm** (a leaky task config on a strict arm).
   Nothing reads the task config's strictness for a reward.  **Not pinned.**

Three points that were open here are settled by the standalone path and tested in
`tests/test_tg_m5_standalone.py`: the run-time default harness (a taskset's default is
`bash` unless its own `Env` says otherwise, and this one's pins `null`: MP3); the taskset
id (`poisson-tasks`, which the wheel resolves to the package root: MP1); and how
`turn_limit_hit` is read off a `vf.Trace` (`stop_condition == "max_turns"`, not
`is_truncated`, which is also true for a token limit or a length-finished reply: `test_tl1`
to `test_tl3`).

What this file does not test: anything that needs a model, an interception server or a
harness run (`Env.run_episode`, the `null` harness's own program, `eval`); the adapter's
model path and its replay check A8; and X8's "`shuffle` is never on the measurement path"
beyond the module's own source, because the measurement path is the adapter's.
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import hashlib
import importlib
import importlib.metadata
import inspect
import json
import threading
from collections.abc import Iterable
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
import verifiers.v1 as vf
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.fastmcp import FastMCP

from poisson_tasks.engine import apply, init_state, replay
from poisson_tasks.knobs import ArmSpec, arm_id, levels
from poisson_tasks.tasks import FormatSpec, TaskBundle, Turn, generate, scenario_for, verify

REPO = Path(__file__).resolve().parents[1]
THIS_FILE = Path(__file__).resolve()
EXPORT_DOC = REPO / "docs" / "verifiers-export.md"

# --------------------------------------------------------------------------
# literals, each from a written requirement or from a module below this one
# --------------------------------------------------------------------------

GEN_VERSION = "0"
PINNED_VERIFIERS = "0.3.1"  # the one verifiers release the export is pinned to

PUBLIC = (
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
)

# The verified-names table, name by name.  `State` is the one addition: the export's design
# names `vf.State`, the table's rows name it only as the `StateT` parameter, and a `vf.Task`
# subclass that gives its config type has to give its state type first.
VERIFIED_NAMES = frozenset({
    "Taskset", "Task", "TaskData", "TaskConfig", "TasksetConfig",
    "Toolset", "ToolsetConfig", "SharedToolsetConfig",
    "tool", "reward", "metric", "stop",
    "Trace", "ToolCall", "AssistantMessage", "ToolMessage", "Messages",
    "SamplingConfig", "Env", "SingleAgentEnv", "SingleAgentEnvConfig", "AgentConfig",
    "Episode", "State",
})

METRICS = ("leaky_pass", "mutation_count", "sampled_calls", "turns")
REWARDS = ("strict",)

D_PLAIN = levels("depth")
R_PLAIN = levels("distractor")
D_CONTROLS = ((1, 8), (2, 5))
R_CONTROLS = ((0, 8), (2, 14))

# Seeds: the three the task layer's own tests build a knob R contrast at, the two ends of the 32-bit
# space, and two more.  Every arm below is generated at every one of them.
SEEDS = (0, 55, 404, 2121, 77_777, 2**32 - 1)


def spec_of(knob: str, level: int, control: int | None = None, strictness: str = "strict") -> ArmSpec:
    return ArmSpec(
        knob=knob,
        level=level,
        control=control,
        strictness=strictness,
        split="eval",
        generator_version=GEN_VERSION,
    )


D_SPECS = tuple(spec_of("depth", lvl) for lvl in D_PLAIN) + tuple(
    spec_of("depth", lvl, ctl) for lvl, ctl in D_CONTROLS
)
# Knob R's level axis: every level of `levels("distractor")` and both R controls,
# never the one `r0`-against-`r8` pair the task layer's tests build.
R_SPECS = tuple(spec_of("distractor", lvl) for lvl in R_PLAIN) + tuple(
    spec_of("distractor", lvl, ctl) for lvl, ctl in R_CONTROLS
)
ALL_SPECS = D_SPECS + R_SPECS
D_CONTROL_SPECS = tuple(s for s in D_SPECS if s.control is not None)


def spec_ids(specs: Iterable[ArmSpec]) -> list[str]:
    return [arm_id(s) for s in specs]


def leaky(spec: ArmSpec) -> ArmSpec:
    return dataclasses.replace(spec, strictness="leaky")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def export() -> Any:
    """The module under test, imported lazily so this file collects without it."""
    return importlib.import_module("poisson_tasks.export")


def export_source() -> ast.Module:
    path = Path(inspect.getsourcefile(export()) or "")
    return ast.parse(path.read_text(encoding="utf-8"))


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def taskset_config(spec: ArmSpec, seeds: Iterable[int]) -> Any:
    return export().ExportTasksetConfig(arm=dataclasses.asdict(spec), seeds=list(seeds))


def taskset(spec: ArmSpec, seeds: Iterable[int]) -> Any:
    return export().ExportTaskset(taskset_config(spec, seeds))


def task_of(bundle: TaskBundle) -> Any:
    return export().task_from_bundle(bundle)


def canon(value: Any) -> Any:
    """The task layer's canonical form, written again: dataclasses by field, mappings by sorted key,
    sequences in order.  A tuple and a list are the same thing here, which is what makes
    `test_x2_3` the requirement's "hashes equal" and `test_x2_1` the stronger statement."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: canon(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): canon(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [canon(item) for item in value]
    return value


def canonical_hash(bundle: TaskBundle) -> str:
    body = json.dumps(canon(bundle), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


NO_MARKERS = FormatSpec(name="test", markers=())


def turns_of(calls: Iterable[tuple[str, Any]], reply: bool) -> tuple[Turn, ...]:
    turns = [Turn(content="", calls=(call,), finish_reason="tool_calls") for call in calls]
    if reply:
        turns.append(Turn(content="Done.", calls=(), finish_reason="stop"))
    return tuple(turns)


def expected_verdict(bundle: TaskBundle, calls: Iterable[tuple[str, Any]], reply: bool) -> Any:
    """The task layer's own verdict, on turns built straight from the calls (decision 7)."""
    return verify(
        bundle, turns_of(calls, reply), ended_with_reply=reply, turn_limit_hit=not reply,
        fmt=NO_MARKERS,
    )


def block_names(bundle: TaskBundle) -> set[str]:
    return {str(tool["name"]) for tool in bundle.tools}


def live_observations(bundle: TaskBundle, calls: Iterable[tuple[str, Any]]) -> list[str]:
    """What each call's tool message holds under the `null` harness at 0.3.1 (decision 6).

    The two `error:` strings are the harness's own, from `harnesses/null/program.py`.  A
    call the harness refuses never reaches the server, so the engine's counter stays put.
    """
    state = init_state(scenario_for(bundle.seed, bundle.split), bundle.seq_start)
    names = block_names(bundle)
    out: list[str] = []
    for name, args in calls:
        if not isinstance(args, dict):
            out.append(
                "error: tool arguments must be a JSON object, got "
                f"{type(json.loads(json.dumps(args))).__name__}; resend as an object"
            )
        elif name not in names:
            out.append(f"error: unknown tool {name!r}")
        else:
            state, observation = apply(state, (name, args))
            out.append(observation)
    return out


def seeded_nodes(task: Any) -> list[Any]:
    """The prompt as the trace holds it: every message prompt-supplied, `sampled=False`."""
    prompt = task.data.prompt
    if isinstance(prompt, str):
        return [vf.MessageNode(parent=None, message=vf.UserMessage(content=prompt), sampled=False)]
    nodes = []
    for index, message in enumerate(prompt):
        nodes.append(vf.MessageNode(parent=index - 1 if index else None, message=message, sampled=False))
    return nodes


def trace_of(
    task: Any,
    bundle: TaskBundle,
    calls: Iterable[tuple[str, Any]],
    *,
    reply: bool = True,
    sampled: bool = True,
    ids: Iterable[str] | None = None,
) -> Any:
    """A synthetic `vf.Trace`: the seeded prompt, then one assistant message per call with
    its tool message, then a reply.  `sampled=False` marks the calls prompt-supplied
    instead, for `test_x4_6`.  A trace with no reply stopped at `max_turns`."""
    calls = list(calls)
    observations = live_observations(bundle, calls)
    call_ids = list(ids) if ids is not None else [f"sampled-{i}" for i in range(len(calls))]
    nodes = seeded_nodes(task)
    for (name, args), observation, call_id in zip(calls, observations, call_ids, strict=True):
        arguments = json.dumps(list(args) if isinstance(args, tuple) else args)
        assistant = vf.AssistantMessage(
            content="", tool_calls=[vf.ToolCall(id=call_id, name=name, arguments=arguments)]
        )
        nodes.append(vf.MessageNode(parent=len(nodes) - 1, message=assistant, sampled=sampled))
        tool = vf.ToolMessage(tool_call_id=call_id, content=observation, name=name)
        nodes.append(vf.MessageNode(parent=len(nodes) - 1, message=tool, sampled=False))
    if reply:
        done = vf.AssistantMessage(content="Done.")
        nodes.append(vf.MessageNode(parent=len(nodes) - 1, message=done, sampled=True))
    return vf.Trace(
        task=vf.TraceTask(type=type(task).__name__, data=task.data, key=task.key, hash=task.hash),
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        nodes=nodes,
        stop_condition=None if reply else "max_turns",
    )


def scored(task: Any, trace: Any) -> Any:
    """Score offline: `runtime=None`, the way X5 says a trace is scored."""
    run(task.score(trace, None))
    return trace


def reward_of(trace: Any, name: str) -> float:
    entry = trace.rewards[name]
    assert entry is not None, f"reward {name!r} was seeded and never recorded"
    return float(entry.score)


def metric_of(trace: Any, name: str) -> float:
    value = trace.metrics[name]
    assert value is not None, f"metric {name!r} was seeded and never recorded"
    return float(value)


def started_toolset(task: Any) -> tuple[Any, FastMCP]:
    """0.3.1's start order, in process: construct, `setup_task`, then `register`."""
    (toolset,) = type(task).toolsets(task.config)
    mcp = FastMCP(toolset.server_name)

    async def start() -> None:
        await toolset.setup()
        await toolset.setup_task(task.data)

    run(start())
    toolset.register(mcp)
    return toolset, mcp


def text_of(result: Any) -> str:
    """The text of a `FastMCP.call_tool` result, whichever of its shapes came back."""
    if isinstance(result, tuple):
        result = result[0]
    blocks = list(result)
    assert len(blocks) == 1, blocks
    return str(blocks[0].text)


def call_live(mcp: FastMCP, calls: Iterable[tuple[str, Any]]) -> list[str]:
    async def go() -> list[str]:
        return [text_of(await mcp.call_tool(name, args)) for name, args in calls]

    return run(go())


def seq_of(observation: str) -> int:
    return int(observation.split()[0])


def imported_modules(tree: ast.Module) -> set[str]:
    """Every module a source file imports, by an `ast` walk: `import a.b`, `from a.b import
    c`, and a string handed to `import_module` or `__import__`."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
        elif isinstance(node, ast.Call):
            callee = node.func
            name = callee.attr if isinstance(callee, ast.Attribute) else getattr(callee, "id", "")
            if name in {"import_module", "__import__"} and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    found.add(first.value)
    return found


def unverified_verifiers_names(tree: ast.Module) -> set[str]:
    """X1's walker.  The rule, in prose: the module may take names from `verifiers` only as
    attributes of `verifiers.v1` -- `import verifiers.v1 as x` then `x.Name`, or `from
    verifiers.v1 import Name` -- and every such `Name` is in the verified-names table.  Any other
    `verifiers` module, a star import, a bare `import verifiers`, and a `getattr` on the
    alias are each reported, since each would let an unverified name through unseen."""
    bad: set[str] = set()
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "verifiers.v1" and alias.asname:
                    aliases.add(alias.asname)
                elif alias.name == "verifiers" or alias.name.startswith("verifiers."):
                    bad.add(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "verifiers.v1":
                for alias in node.names:
                    if alias.name not in VERIFIED_NAMES:
                        bad.add(alias.name)
            elif node.module == "verifiers":
                for alias in node.names:
                    if alias.name == "v1":
                        aliases.add(alias.asname or "v1")
                    else:
                        bad.add(f"from verifiers import {alias.name}")
            elif node.module.startswith("verifiers."):
                bad.add(f"from {node.module} import ...")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in aliases and node.attr not in VERIFIED_NAMES:
                bad.add(node.attr)
        elif isinstance(node, ast.Call) and getattr(node.func, "id", "") == "getattr" and node.args:
            first = node.args[0]
            if isinstance(first, ast.Name) and first.id in aliases:
                bad.add("getattr on the verifiers alias")
    for name in imported_modules(tree):
        if (name == "verifiers" or name.startswith("verifiers.")) and name != "verifiers.v1":
            bad.add(f"import {name}")
    return bad


# --------------------------------------------------------------------------
# SF - the surface
# --------------------------------------------------------------------------


def test_sf1_all_is_exactly_the_ten_names_in_order():
    assert tuple(export().__all__) == PUBLIC


def test_sf2_no_public_symbol_beyond_all():
    """Every import is underscore-aliased, as in the four modules below this one."""
    public = {name for name in vars(export()) if not name.startswith("_")}
    assert public - {"annotations"} == set(PUBLIC)


def test_sf3_each_class_is_the_verifiers_type_2_4_names():
    """The written interface, class by class, each base checked on its own."""
    m = export()
    assert issubclass(m.ExportTasksetConfig, vf.TasksetConfig)
    assert issubclass(m.ExportTaskConfig, vf.TaskConfig)
    assert issubclass(m.ExportTaskData, vf.TaskData)
    assert issubclass(m.ExportTask, vf.Task)
    assert issubclass(m.ExportTaskset, vf.Taskset)
    assert issubclass(m.DomainToolsetConfig, vf.ToolsetConfig)
    assert issubclass(m.DomainToolset, vf.Toolset)


def test_sf4_the_generic_parameters_resolve_to_the_modules_own_types():
    """The wheel reads a task's data and config types, and a taskset's task type, off the
    generic parameters; a subclass that leaves them bare gets the base types back, and then
    0.3.1 rebuilds a task's data as a plain `vf.TaskData` and drops every bundle field."""
    m = export()
    assert m.ExportTask.data_type() is m.ExportTaskData
    assert m.ExportTask.config_type() is m.ExportTaskConfig
    assert m.ExportTaskset.task_type() is m.ExportTask


def test_sf5_a_task_config_needs_no_argument():
    """0.3.1: "every field needs a default because constructing a task without a config
    builds the declared config type"."""
    config = export().ExportTaskConfig()
    assert config.strictness in {"strict", "leaky"}
    assert isinstance(config.arm_id, str)


# --------------------------------------------------------------------------
# PV - Proofload stays optional
# --------------------------------------------------------------------------

PROOFLOAD_SIDE = ("proofload", "poisson_tasks.adapter")


def needs_proofload(modules: set[str]) -> set[str]:
    return {
        name for name in modules
        if any(name == banned or name.startswith(banned + ".") for banned in PROOFLOAD_SIDE)
    }


def test_pv2_this_file_imports_no_proofload_and_no_adapter():
    """The same walk over this file, so no test here can need the extra.  It reads this
    file only."""
    tree = ast.parse(THIS_FILE.read_text(encoding="utf-8"))
    assert needs_proofload(imported_modules(tree)) == set()


def test_pv3_the_walker_sees_each_shape_of_import():
    """The known positive for PV2, MP6.1's walk and X1.3's import half."""
    shapes = {
        "import proofload": {"proofload"},
        "from proofload import Episode": {"proofload"},
        "from proofload.store import x": {"proofload.store"},
        "import importlib\nimportlib.import_module('proofload')": {"proofload"},
        "__import__('poisson_tasks.adapter')": {"poisson_tasks.adapter"},
        "from poisson_tasks.adapter import to_episode": {"poisson_tasks.adapter"},
    }
    for source, expected in shapes.items():
        assert needs_proofload(imported_modules(ast.parse(source))) == expected, source
    assert needs_proofload(imported_modules(ast.parse("import poisson_tasks.tasks"))) == set()


# --------------------------------------------------------------------------
# X1 - verified names only
# --------------------------------------------------------------------------


def test_x1_1_the_installed_wheel_is_the_pinned_one():
    """The pinned release, and X1's "a CI test imports each one from the pinned 0.3.1
    wheel": every verified name is an attribute of `verifiers.v1` and is in its `__all__`.
    It reads the environment, not the module."""
    assert importlib.metadata.version("verifiers") == PINNED_VERIFIERS
    assert {name for name in VERIFIED_NAMES if not hasattr(vf, name)} == set()
    assert VERIFIED_NAMES - set(vf.__all__) == set()


def test_x1_3_the_export_takes_only_verified_names_from_verifiers():
    assert unverified_verifiers_names(export_source()) == set()


def test_x1_4_the_walker_flags_each_way_an_unverified_name_gets_in():
    """The known positive for X1.3."""
    flagged = {
        "import verifiers.v1 as vf\nvf.MessageNode": {"MessageNode"},
        "from verifiers.v1 import TraceTask": {"TraceTask"},
        "from verifiers.v1.mcp import serve": {"from verifiers.v1.mcp import ...", "import verifiers.v1.mcp"},
        "import verifiers": {"import verifiers"},
        "import verifiers.v1 as vf\ngetattr(vf, 'Rollout')": {"getattr on the verifiers alias"},
        "from verifiers import v1 as q\nq.Judge": {"Judge", "import verifiers"},
    }
    for source, expected in flagged.items():
        assert unverified_verifiers_names(ast.parse(source)) == expected, source
    clean = "import verifiers.v1 as _vf\nclass T(_vf.Task[_vf.TaskData, _vf.State, _vf.TaskConfig]): ..."
    assert unverified_verifiers_names(ast.parse(clean)) == set()


# --------------------------------------------------------------------------
# X2 - round trip
# --------------------------------------------------------------------------


@pytest.mark.parametrize("spec", ALL_SPECS, ids=spec_ids(ALL_SPECS))
def test_x2_1_task_data_rebuilds_the_generated_bundle(spec):
    """The bundle holds tuples, a records value, a `PinRecord`
    of nested tuples, a clause-2 control whose arguments are a tuple, and (for a D control)
    a seeded prompt in a shape the wheel refuses."""
    for seed in SEEDS:
        for arm in (spec, leaky(spec)):
            bundle = generate(arm, seed)
            assert export().bundle_from_data(task_of(bundle).data) == bundle


@pytest.mark.parametrize("spec", ALL_SPECS, ids=spec_ids(ALL_SPECS))
def test_x2_2_the_round_trip_survives_the_json_wire(spec):
    """0.3.1 hands a launched tool server its task as `model_dump_json`, rebuilt with
    `model_validate_json` on the data's own class.  JSON has no tuple."""
    for seed in SEEDS:
        bundle = generate(spec, seed)
        data = task_of(bundle).data
        rebuilt = type(data).model_validate_json(data.model_dump_json())
        assert export().bundle_from_data(rebuilt) == bundle


@pytest.mark.parametrize("spec", ALL_SPECS, ids=spec_ids(ALL_SPECS))
def test_x2_3_the_rebuilt_bundle_hashes_equal(spec):
    """X2 in its own words.  Weaker than X2.1 by exactly the tuple-or-list question."""
    for seed in SEEDS:
        bundle = generate(spec, seed)
        rebuilt = export().bundle_from_data(task_of(bundle).data)
        assert canonical_hash(rebuilt) == canonical_hash(bundle)
        assert rebuilt.task_id == bundle.task_id


@pytest.mark.parametrize("spec", ALL_SPECS, ids=spec_ids(ALL_SPECS))
def test_x2_5_the_data_carries_the_fields_2_4_names_as_the_bundle_has_them(spec):
    bundle = generate(spec, 2121)
    data = task_of(bundle).data
    assert data.system_prompt == bundle.system_prompt
    assert data.seq_start == bundle.seq_start
    assert [tool["name"] for tool in data.tools] == [tool["name"] for tool in bundle.tools]
    if isinstance(bundle.prompt, str):
        assert data.prompt == bundle.prompt


@pytest.mark.parametrize("spec", D_CONTROL_SPECS, ids=spec_ids(D_CONTROL_SPECS))
def test_x2_6_a_seeded_prompt_is_verifiers_messages(spec):
    """Decision 5.  The bundle's seeded history is the OpenAI chat shape; the wheel's
    `vf.Messages` is not, and refuses it."""
    bundle = generate(spec, 5151)
    assert not isinstance(bundle.prompt, str)
    prompt = task_of(bundle).data.prompt
    assert [type(m) for m in prompt][:3] == [vf.UserMessage, vf.AssistantMessage, vf.ToolMessage]
    assert len(prompt) == len(bundle.prompt)
    for theirs, ours in zip(bundle.prompt, prompt, strict=True):
        if theirs["role"] == "assistant":
            (call,) = theirs["tool_calls"]
            (flat,) = ours.tool_calls
            assert (flat.id, flat.name, flat.arguments) == (
                call["id"], call["function"]["name"], call["function"]["arguments"],
            )
        elif theirs["role"] == "tool":
            assert (ours.tool_call_id, ours.content) == (theirs["tool_call_id"], theirs["content"])
        else:
            assert ours.content == theirs["content"]


# --------------------------------------------------------------------------
# X3 - the advertised block equals the bundle's block
# --------------------------------------------------------------------------


def listed(mcp: FastMCP) -> list[Any]:
    return list(run(mcp.list_tools()))


@pytest.mark.parametrize("spec", ALL_SPECS, ids=spec_ids(ALL_SPECS))
def test_x3_1_the_names_are_the_bundles_in_slot_order(spec):
    """The tool order is fixed per seed, and the last line checks the seeds do not all share one order, or order would be pinned by nothing."""
    orders = set()
    for seed in SEEDS:
        bundle = generate(spec, seed)
        _toolset, mcp = started_toolset(task_of(bundle))
        names = [tool.name for tool in listed(mcp)]
        assert names == [tool["name"] for tool in bundle.tools]
        orders.add(tuple(names))
    assert len(orders) > 1


@pytest.mark.parametrize("spec", ALL_SPECS, ids=spec_ids(ALL_SPECS))
def test_x3_2_the_descriptions_are_the_bundles(spec):
    for seed in SEEDS[:3]:
        bundle = generate(spec, seed)
        _toolset, mcp = started_toolset(task_of(bundle))
        assert [t.description for t in listed(mcp)] == [t["description"] for t in bundle.tools]


@pytest.mark.parametrize("spec", ALL_SPECS, ids=spec_ids(ALL_SPECS))
def test_x3_3_the_parameter_schemas_are_the_bundles_exactly(spec):
    """"Exactly": FastMCP derives a schema of its own from a function's signature, with a
    `title` on every property and no `additionalProperties`, and that is not the bundle's."""
    for seed in SEEDS[:3]:
        bundle = generate(spec, seed)
        _toolset, mcp = started_toolset(task_of(bundle))
        assert [t.inputSchema for t in listed(mcp)] == [t["parameters"] for t in bundle.tools]


def test_x3_4_the_toolset_advertises_bare_names():
    """Tool names get a `<server>_` prefix unless `TOOL_PREFIX = None`."""
    m = export()
    assert m.DomainToolset.TOOL_PREFIX is None
    assert m.DomainToolset(m.DomainToolsetConfig()).server_name == ""


class _TaskChannel(BaseHTTPRequestHandler):
    payload = b""

    def do_GET(self) -> None:  # noqa: N802 - the base class's name
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(type(self).payload)

    def log_message(self, *args: Any) -> None:
        return None


@pytest.mark.parametrize("spec", (spec_of("depth", 3, None), spec_of("depth", 2, 5), spec_of("distractor", 14)),
                         ids=("depth:d3", "depth:d2+h5", "distractor:r14@k16"))
def test_x3_5_a_real_launch_advertises_the_block_and_runs_the_reference(spec):
    """Decision 10.  The wheel's own `serve` starts the toolset's module as a child
    process; the child fetches its task over `/task`, as a rollout's server does, and is
    then asked for its tools and for the reference calls over MCP.  A D control is one of
    the three because its counter starts past 1, and `r14` because its block keeps no read
    tool."""
    from verifiers.v1.mcp import serve  # the wheel's launch path; not a name the module may use

    bundle = generate(spec, 404)
    task = task_of(bundle)
    data = task.data
    handler = type("Channel", (_TaskChannel,), {})
    handler.payload = json.dumps({
        "cls": f"{type(data).__module__}:{type(data).__qualname__}",
        "task": data.model_dump_json(),
    }).encode("utf-8")
    httpd = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    (toolset,) = type(task).toolsets(task.config)

    async def go() -> tuple[list[Any], list[str]]:
        async with serve(toolset, state_secret="secret", state_base=base) as url:
            async with streamablehttp_client(url) as (reader, writer, _):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    tools = list((await session.list_tools()).tools)
                    observations = []
                    for name, args in bundle.reference_calls:
                        result = await session.call_tool(name, args)
                        observations.append(result.content[0].text)
                    return tools, observations

    try:
        tools, observations = run(go())
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert [t.name for t in tools] == [t["name"] for t in bundle.tools]
    assert [t.description for t in tools] == [t["description"] for t in bundle.tools]
    assert [t.inputSchema for t in tools] == [t["parameters"] for t in bundle.tools]
    assert observations == list(bundle.reference_observations)


# --------------------------------------------------------------------------
# TS - the toolset's behaviour, from the written interface
# --------------------------------------------------------------------------


@pytest.mark.parametrize("spec", ALL_SPECS, ids=spec_ids(ALL_SPECS))
def test_ts1_the_live_tools_return_the_reference_observations(spec):
    """"`setup_task(task)` builds the engine state from the task data", `seq_start`
    included: a D control's first live observation is numbered `H - dL + 1`, not 1."""
    for seed in SEEDS[:3]:
        bundle = generate(spec, seed)
        _toolset, mcp = started_toolset(task_of(bundle))
        live = call_live(mcp, bundle.reference_calls)
        assert live == list(bundle.reference_observations)
        assert seq_of(live[0]) == bundle.seq_start


@pytest.mark.parametrize("spec", ALL_SPECS, ids=spec_ids(ALL_SPECS))
def test_ts2_a_call_that_fails_its_schema_still_reaches_the_engine(spec):
    """Decision 11.  Every control whose calls the `null` harness would pass on -- each one
    names a tool in the block with a JSON object -- is run live and compared with the engine's
    `replay`, byte for byte.  `malformed_call_clause_4` is the one that bites: its arguments
    miss a required parameter, and the engine's answer is a numbered `bad_args` line."""
    bundle = generate(spec, 55)
    scenario = scenario_for(bundle.seed, bundle.split)
    names = block_names(bundle)
    ran = 0
    for _label, calls in sorted(bundle.negative_controls.items()):
        if not all(isinstance(args, dict) and name in names for name, args in calls):
            continue
        _toolset, mcp = started_toolset(task_of(bundle))
        _state, expected = replay(scenario, list(calls), bundle.seq_start)
        assert call_live(mcp, calls) == expected
        ran += 1
    assert ran >= 3
    extra = [(bundle.reference_calls[0][0], {**bundle.reference_calls[0][1], "unasked": 7})]
    wrong_type = [(bundle.reference_calls[0][0], {key: 3 for key in bundle.reference_calls[0][1]})]
    for calls in (extra, wrong_type, extra + list(bundle.reference_calls)):
        _toolset, mcp = started_toolset(task_of(bundle))
        _state, expected = replay(scenario, list(calls), bundle.seq_start)
        assert call_live(mcp, calls) == expected


@pytest.mark.parametrize("spec", ALL_SPECS, ids=spec_ids(ALL_SPECS))
def test_ts6_every_advertised_tool_is_the_engines_tool_of_that_name(spec):
    """Each tool in the block, called once under its own name, answers as the engine's `replay`
    does.  The reference and the controls only ever call the target class's stage tools, so
    nothing else here reaches a read tool or a distractor twin -- and knob R's block is made
    of those, more of them at every level.  The arguments are the first reference call's
    where the parameter names match (the target's record id and the entry code), so a
    stage-1 twin *succeeds* on its own class's record, and a body that routed it to the
    required tool would return another class's token."""
    bundle = generate(spec, 2121)
    known = dict(bundle.reference_calls[0][1])
    calls = [
        (str(tool["name"]), {name: known.get(name, "x") for name in tool["parameters"]["properties"]})
        for tool in bundle.tools
    ]
    assert len(calls) == len(bundle.tools) > 0
    _toolset, mcp = started_toolset(task_of(bundle))
    _state, expected = replay(scenario_for(bundle.seed, bundle.split), calls, bundle.seq_start)
    assert call_live(mcp, calls) == expected


def test_ts3_concurrent_calls_are_numbered_without_a_gap_or_a_repeat(monkeypatch):
    """"Tool bodies call `apply` under an in-process lock" (E5: no gap and no repeat).

    Numbering alone cannot show the lock: as built, nothing in a body awaits between
    reading the engine state and writing it back, so 24 calls gathered on one loop never
    interleave there, with the lock or without it.  `apply` is synchronous and cannot be
    made to yield from outside, so the engine step the module calls is wrapped instead,
    and each call records whether an `asyncio.Lock` the toolset owns is held while it
    runs.  A body that calls `apply` outside the lock fails here; one that holds it keeps
    the numbering right even if an `await` is added inside."""
    bundle = generate(spec_of("depth", 3), 404)
    toolset, mcp = started_toolset(task_of(bundle))
    name, args = bundle.reference_calls[0]
    locks = [value for value in vars(toolset).values() if isinstance(value, asyncio.Lock)]
    held: list[bool] = []
    engine_apply = export()._apply

    def watched(state: Any, call: Any) -> Any:
        held.append(any(lock.locked() for lock in locks))
        return engine_apply(state, call)

    monkeypatch.setattr(export(), "_apply", watched)

    async def go() -> list[str]:
        results = await asyncio.gather(*(mcp.call_tool(name, args) for _ in range(24)))
        return [text_of(result) for result in results]

    seqs = sorted(seq_of(observation) for observation in run(go()))
    assert seqs == list(range(bundle.seq_start, bundle.seq_start + 24))
    assert held == [True] * 24, held


def test_ts4_each_rollout_gets_its_own_engine_state():
    """`toolsets(config)` is "tool servers launched per rollout": task-scoped.  Two
    toolsets for one task must not share a record or a counter."""
    bundle = generate(spec_of("depth", 2), 2121)
    task = task_of(bundle)
    (first,) = type(task).toolsets(task.config)
    (second,) = type(task).toolsets(task.config)
    assert first is not second
    assert isinstance(first, export().DomainToolset)
    _a, mcp_a = started_toolset(task)
    assert call_live(mcp_a, bundle.reference_calls) == list(bundle.reference_observations)
    _b, mcp_b = started_toolset(task)
    assert call_live(mcp_b, bundle.reference_calls) == list(bundle.reference_observations)


def test_ts5_the_engine_state_is_not_in_vf_state():
    """The engine state lives in the server instance, because `vf.State` sync is
    last-write-wins.  After live calls the toolset's `vf.State` is still the empty
    base type."""
    bundle = generate(spec_of("depth", 2), 2121)
    toolset, mcp = started_toolset(task_of(bundle))
    call_live(mcp, bundle.reference_calls)
    assert type(toolset.state) is vf.State


# --------------------------------------------------------------------------
# X4 - the reward equals the task layer's verifier
# --------------------------------------------------------------------------


@pytest.mark.parametrize("spec", ALL_SPECS, ids=spec_ids(ALL_SPECS))
def test_x4_1_strict_is_one_exactly_when_verify_says_passed(spec):
    """Every generated control and the reference, under both strictnesses, at three seeds.
    `turn_limit` runs with no reply, as the task layer runs it.  The
    expectation is the task layer's `verify` on turns the module never sees."""
    ones = zeros = 0
    for seed in SEEDS[:3]:
        for arm in (spec, leaky(spec)):
            bundle = generate(arm, seed)
            task = task_of(bundle)
            runs = [("reference", bundle.reference_calls)] + sorted(bundle.negative_controls.items())
            for label, calls in runs:
                reply = label != "turn_limit"
                expected = expected_verdict(bundle, calls, reply).strict_label == "passed"
                trace = scored(task, trace_of(task, bundle, calls, reply=reply))
                assert reward_of(trace, "strict") == (1.0 if expected else 0.0), (arm_id(arm), seed, label)
                ones += expected
                zeros += not expected
    assert ones and zeros


@pytest.mark.parametrize("spec", ALL_SPECS, ids=spec_ids(ALL_SPECS))
def test_x4_2_leaky_pass_is_verifys_on_every_trace_that_ends_with_a_reply(spec):
    """The no-reply trace is left out: how `leaky_pass` reads a trace that stops without a
    reply is the turn-limit read, tested in `tests/test_tg_m5_standalone.py` (`test_tl1` to
    `test_tl3`).  The last lines are G7 seen from here: some control is accepted by leaky
    and rejected by strict, or the two signals would be pinned by nothing that tells them
    apart."""
    separated = 0
    for seed in SEEDS[:3]:
        bundle = generate(spec, seed)
        task = task_of(bundle)
        for label, calls in sorted(bundle.negative_controls.items()):
            if label == "turn_limit":
                continue
            verdict = expected_verdict(bundle, calls, reply=True)
            trace = scored(task, trace_of(task, bundle, calls))
            assert metric_of(trace, "leaky_pass") == (1.0 if verdict.leaky_pass else 0.0), label
            separated += verdict.leaky_pass and verdict.strict_label != "passed"
    assert separated


@pytest.mark.parametrize("spec", (spec_of("depth", 3), spec_of("depth", 8), spec_of("distractor", 4)),
                         ids=("depth:d3", "depth:d8", "distractor:r4@k16"))
def test_x4_3_the_calls_are_ordered_by_the_seq_in_their_tool_messages(spec):
    """One assistant turn carrying the whole reference **in reverse**, each call's tool
    message holding the observation it got when the calls ran in the right order.  Read in
    `seq` order the chain completes; read in list order every call but the last is refused,
    since a record at stage `i` accepts only the stage `i + 1` tool."""
    bundle = generate(spec, 404)
    task = task_of(bundle)
    calls = list(bundle.reference_calls)
    assert len(calls) >= 2
    ids = [f"k{i}" for i in range(len(calls))]
    backwards = list(reversed(list(zip(ids, calls, bundle.reference_observations, strict=True))))
    nodes = seeded_nodes(task)
    turn = vf.AssistantMessage(content="", tool_calls=[
        vf.ToolCall(id=call_id, name=name, arguments=json.dumps(args))
        for call_id, (name, args), _obs in backwards
    ])
    nodes.append(vf.MessageNode(parent=len(nodes) - 1, message=turn, sampled=True))
    for call_id, (name, _args), observation in backwards:
        message = vf.ToolMessage(tool_call_id=call_id, content=observation, name=name)
        nodes.append(vf.MessageNode(parent=len(nodes) - 1, message=message, sampled=False))
    nodes.append(vf.MessageNode(parent=len(nodes) - 1, message=vf.AssistantMessage(content="Done."), sampled=True))
    trace = vf.Trace(
        task=vf.TraceTask(type="ExportTask", data=task.data, key=task.key, hash=task.hash),
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        nodes=nodes,
    )
    in_list_order = expected_verdict(bundle, [call for _id, call, _obs in backwards], reply=True)
    assert in_list_order.strict_label != "passed"  # the fixture can tell the two orders apart
    assert reward_of(scored(task, trace), "strict") == 1.0


@pytest.mark.parametrize("spec", D_CONTROL_SPECS, ids=spec_ids(D_CONTROL_SPECS))
def test_x4_4_a_controls_seeded_calls_are_not_the_models(spec):
    """"Pre-seeded control-arm messages are excluded by construction."  The seeded calls are
    reads and mutate nothing, so `strict` alone cannot see them counted; `sampled_calls`
    can."""
    for seed in SEEDS[:3]:
        bundle = generate(spec, seed)
        task = task_of(bundle)
        trace = scored(task, trace_of(task, bundle, bundle.reference_calls))
        assert len(trace.tool_messages) > len(bundle.reference_calls)  # the seeded ones are there
        assert reward_of(trace, "strict") == 1.0
        assert metric_of(trace, "sampled_calls") == float(len(bundle.reference_calls))
        assert metric_of(trace, "turns") == float(len(bundle.reference_calls) + 1)


@pytest.mark.parametrize("spec", D_CONTROL_SPECS, ids=spec_ids(D_CONTROL_SPECS))
def test_x4_5_a_sampled_call_is_matched_to_its_own_tool_message(spec):
    """The seeded history's call ids are `call_0`, `call_1`, ...  A model's ids can collide
    with them, and a sampled call's tool message is the one that follows it, never a seeded
    one that shares its id: matched to the seeded observation, the reference chain would be
    ordered by the seeded `seq`s."""
    bundle = generate(spec, 404)
    task = task_of(bundle)
    calls = list(bundle.reference_calls)
    ids = [f"call_{i}" for i in reversed(range(len(calls)))]
    trace = scored(task, trace_of(task, bundle, calls, ids=ids))
    assert reward_of(trace, "strict") == 1.0
    assert metric_of(trace, "sampled_calls") == float(len(calls))


@pytest.mark.parametrize("spec", ALL_SPECS, ids=spec_ids(ALL_SPECS))
def test_x4_6_prompt_supplied_stage_calls_earn_nothing(spec):
    """`Trace.assistant_messages` is sampled-only.  A trace whose whole reference solution
    was *supplied in the prompt*, with the model sampling only the reply, did no work: a
    build that reads every assistant message in the trace scores it 1.0."""
    bundle = generate(spec, 77_777)
    task = task_of(bundle)
    trace = scored(task, trace_of(task, bundle, bundle.reference_calls, sampled=False))
    assert reward_of(trace, "strict") == 0.0
    assert metric_of(trace, "sampled_calls") == 0.0


def test_x4_8_strict_is_the_one_reward_and_weighs_one():
    """`@vf.reward strict` (weight 1.0), and `leaky_pass` a metric: the leaky verdict
    is descriptive, so it must not reach `Trace.reward`."""
    bundle = generate(spec_of("depth", 5), 404)
    task = task_of(bundle)
    (overshoot,) = [calls for label, calls in bundle.negative_controls.items() if label == "overshoot"]
    trace = scored(task, trace_of(task, bundle, overshoot))
    assert tuple(sorted(trace.rewards)) == REWARDS
    assert trace.rewards["strict"].weight == 1.0
    assert metric_of(trace, "leaky_pass") == 1.0
    assert trace.reward == 0.0


# --------------------------------------------------------------------------
# X5 - offline scoring
# --------------------------------------------------------------------------


def test_x5_1_no_reward_or_metric_takes_a_runtime():
    """X5 to the letter: not a defaulted `runtime` either."""
    task = task_of(generate(spec_of("depth", 1), 0))
    hooks = [
        getattr(task, name) for klass in type(task).__mro__ for name, fn in vars(klass).items()
        if callable(fn) and (hasattr(fn, "reward") or hasattr(fn, "metric"))
    ]
    assert {hook.__name__ for hook in hooks} == set(REWARDS) | set(METRICS)
    for hook in hooks:
        assert "runtime" not in inspect.signature(hook).parameters, hook.__name__


def test_x5_2_every_signal_is_recorded_with_no_runtime():
    """The wheel skips a runtime-dependent signal when it scores with `runtime=None`, and
    a skipped signal is absent from the trace."""
    bundle = generate(spec_of("distractor", 8), 55)
    task = task_of(bundle)
    trace = scored(task, trace_of(task, bundle, bundle.reference_calls))
    assert tuple(sorted(trace.rewards)) == REWARDS
    assert tuple(sorted(trace.metrics)) == METRICS
    assert all(value is not None for value in trace.metrics.values())


# --------------------------------------------------------------------------
# X6 - the reference trace scores 1.0
# --------------------------------------------------------------------------


@pytest.mark.parametrize("spec", ALL_SPECS, ids=spec_ids(ALL_SPECS))
def test_x6_1_the_reference_trace_scores_one_on_both_signals(spec):
    for seed in SEEDS:
        for arm in (spec, leaky(spec)):
            bundle = generate(arm, seed)
            task = task_of(bundle)
            trace = scored(task, trace_of(task, bundle, bundle.reference_calls))
            assert reward_of(trace, "strict") == 1.0, (arm_id(arm), seed)
            assert metric_of(trace, "leaky_pass") == 1.0, (arm_id(arm), seed)


@pytest.mark.parametrize("spec", ALL_SPECS, ids=spec_ids(ALL_SPECS))
def test_x6_2_the_diagnostics_on_a_reference_trace(spec):
    """Decision 8.  `mutation_count`'s expectation is the task layer's, never a number
    written here."""
    bundle = generate(spec, 2121)
    task = task_of(bundle)
    trace = scored(task, trace_of(task, bundle, bundle.reference_calls))
    verdict = expected_verdict(bundle, bundle.reference_calls, reply=True)
    assert metric_of(trace, "sampled_calls") == float(len(bundle.reference_calls))
    assert metric_of(trace, "turns") == float(len(bundle.reference_calls) + 1)
    assert metric_of(trace, "mutation_count") == float(len(verdict.mutations))
    assert len(verdict.mutations) > 0


# --------------------------------------------------------------------------
# X7 - keys
# --------------------------------------------------------------------------


def test_x7_3_keys_are_stable_across_loads_and_across_processes():
    """"Stable across runs": a second load gives the same keys, and each key is the
    generator's `task_id`.  That `task_id` itself is the same in two fresh interpreters
    under different `PYTHONHASHSEED`s is the task layer's `test_g1_2`."""
    spec = spec_of("depth", 3, None)
    seeds = [0, 55, 404, 2121]
    here = [task.key for task in taskset(spec, seeds).load()]
    assert here == [task.key for task in taskset(spec, seeds).load()]
    assert here == [generate(spec, seed).task_id for seed in seeds]


# --------------------------------------------------------------------------
# X8 - bounded
# --------------------------------------------------------------------------


@pytest.mark.parametrize("seeds", ([],), ids=("none",))
def test_x8_2_load_yields_one_task_per_declared_seed(seeds):
    """The empty list: no other test loads one, and `load` yields nothing for it (a
    default seed would make it one task).  Longer lists are `test_x8_3`'s."""
    assert len(list(taskset(spec_of("depth", 2), seeds).load())) == len(seeds)


@pytest.mark.parametrize("spec", ALL_SPECS, ids=spec_ids(ALL_SPECS))
def test_x8_3_each_loaded_task_is_generate_at_its_seed_in_declared_order(spec):
    """"`load()` yields one task per declared seed via `generate`", in the order declared:
    nothing reorders the measurement's tasks."""
    seeds = [2121, 0, 404, 55]
    tasks = list(taskset(spec, seeds).load())
    assert all(isinstance(task, export().ExportTask) for task in tasks)
    rebuilt = [export().bundle_from_data(task.data) for task in tasks]
    assert rebuilt == [generate(spec, seed) for seed in seeds]


def test_x8_4_a_repeated_seed_is_refused():
    """Decision 2: X7 and X8 cannot both hold for a list that repeats a seed.  The first
    line is the control: the same arm and the same length with no repeat loads, so the
    repeat is the only thing the refusal can be about.  No word of the message is matched:
    a pydantic error quotes its whole input, `seeds` included, whatever the clause said."""
    assert len(list(taskset(spec_of("depth", 2), [5, 9, 7]).load())) == 3
    with pytest.raises(ValueError):
        list(taskset(spec_of("depth", 2), [5, 9, 5]).load())


@pytest.mark.parametrize("spec", (spec_of("depth", 3, 8, "leaky"), spec_of("distractor", 2, 14)),
                         ids=("depth:d3+h8-leaky", "distractor:r2+len(r14)@k16"))
def test_x8_5_the_task_config_carries_the_arms_id_and_strictness(spec):
    """`task` is a `vf.TaskConfig` subclass carrying the strictness and the arm id."""
    config = taskset_config(spec, [1])
    assert isinstance(config.task, export().ExportTaskConfig)
    assert (config.task.arm_id, config.task.strictness) == (arm_id(spec), spec.strictness)
    (task,) = list(export().ExportTaskset(config).load())
    assert (task.config.arm_id, task.config.strictness) == (arm_id(spec), spec.strictness)
    built = task_of(generate(spec, 1))
    assert (built.config.arm_id, built.config.strictness) == (arm_id(spec), spec.strictness)


def test_x8_6_the_export_never_shuffles():
    """X8's last clause, as far as this module's source can show it.  The rule, in prose:
    the module calls nothing named `shuffle` and imports no `random`."""
    tree = export_source()
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(tree) if isinstance(node, ast.Call)
    }
    assert "shuffle" not in called
    assert not {name for name in imported_modules(tree) if name.split(".")[0] == "random"}


def test_x8_7_a_long_seed_list_loads_in_the_order_declared():
    """X8's order past `test_x8_3`'s four seeds: twelve, in no sorted order and with no
    symmetry, so a load that reorders a long list -- reversed, sorted or shuffled -- yields
    the tasks in another order."""
    seeds = [907, 3, 2121, 55, 0, 404, 77_777, 18, 6, 5151, 2**32 - 1, 42]
    tasks = list(taskset(spec_of("depth", 2), seeds).load())
    assert [task.data.seed for task in tasks] == seeds


# --------------------------------------------------------------------------
# VAL - validate is G4
# --------------------------------------------------------------------------


@pytest.mark.parametrize("spec", ALL_SPECS, ids=spec_ids(ALL_SPECS))
def test_val1_a_generated_task_validates(spec):
    """0.3.1's signature: a coroutine, `-> bool`.  `runtime` is unused, so `None` will do."""
    assert inspect.iscoroutinefunction(export().ExportTask.validate)
    for arm in (spec, leaky(spec)):
        assert run(task_of(generate(arm, 404)).validate(None)) is True


@pytest.mark.parametrize("spec", ALL_SPECS, ids=spec_ids(ALL_SPECS))
def test_val2_a_reference_that_falls_short_does_not_validate(spec):
    bundle = generate(spec, 404)
    broken = dataclasses.replace(bundle, reference_calls=bundle.negative_controls["wrong_state"])
    assert run(task_of(broken).validate(None)) is False


@pytest.mark.parametrize("spec", ALL_SPECS, ids=spec_ids(ALL_SPECS))
def test_val3_g4_is_both_strictnesses_whatever_the_arm_declares(spec):
    """Decision 9.  Under a leaky arm, a reference that does collateral damage is labelled
    `passed`, and G4 still fails: strict does not pass it."""
    bundle = generate(leaky(spec), 404)
    damage = bundle.negative_controls["collateral_mutation"]
    verdict = expected_verdict(dataclasses.replace(bundle, reference_calls=damage), damage, reply=True)
    assert (verdict.label, verdict.strict_label) == ("passed", "collateral_mutation")
    broken = dataclasses.replace(bundle, reference_calls=damage)
    assert run(task_of(broken).validate(None)) is False


# --------------------------------------------------------------------------
# X9 - the harness declaration
# --------------------------------------------------------------------------


def export_doc() -> str:
    assert export().MEASURED_HARNESS  # the docs belong to the export: no module, no docs
    return EXPORT_DOC.read_text(encoding="utf-8")


def test_x9_2_the_docs_name_the_measured_harness():
    """The sentence that names it, not any backticked `null` in the document."""
    assert "The measured harness is `null`." in " ".join(export_doc().split())


def test_x9_3_the_docs_say_another_harness_is_outside_the_pin_ledger():
    """Why another harness is outside the pin ledger (it changes the system prompt), and
    the flag that names one over the environment's pin (MP5)."""
    text = " ".join(export_doc().split())
    assert "outside the pin ledger" in text
    assert "system prompt" in text
    assert "--env.agent.harness.id" in text
