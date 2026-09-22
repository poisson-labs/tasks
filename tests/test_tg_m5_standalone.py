"""TG-M5's model path, layer 1 -- the standalone path: a taskset id that resolves, an `Env`
that makes `eval` run the measured harness with no flag, and a stranger's one-liner -- frozen
as tests.

The invariants this file is built against are MP1 to MP9 of [[Task Generator -- Handoff Model
Path]] (layer 1), the wire round-trip invariant ruled out of the 2026-09-22 live smoke, the
two items TG-M4 handed to the model path (TG-ADR-46: the measured-harness
default and loading the taskset by id), Taylor's 2026-09-21 rulings on the model path (the id
is `poisson-tasks`; the release needs layer 1 only; `turn_limit_hit` reads the stop reason),
and knob R's level axis.  MP10, the bridge to the adapter's verdict, is in
`tests/test_tg_m5_bridge.py`, because `to_episode` imports Proofload and no test here may.
Layer 2 (MP11 to MP18, the pinned GPU stack) is not tested here.

**Frozen 2026-09-22**, on Taylor's approval of the invariant-to-test mapping ([[Task Generator --
Handoff Model Path]], *Session A, layer 1*) and his six rulings of the same day: the mapping stands;
MP10 stays in its own Prove-gated file; Session B may edit the one-line turn-limit read in
`export.py` and `_judge` in `adapter.py`; the Env's second declared pin is the runtime; the
one-liner passes the arm as one JSON value and the taskset config defaults nothing; `test_sf4`
stays untouched and the retrofit branch goes unused.

**No test here needs Proofload, a GPU or a model.**  Where an invariant is about a run, the run
is made through the wheel's own lifecycle (`load_environment`, `serving`, `run_episode`)
against a stub OpenAI-compatible endpoint on loopback that answers with the reference calls.
Those tests need `uv` on `PATH`, because the `null` harness launches its program through
`uv`; the program's four dependencies come from uv's cache after the first run.

Every test reaches the build through the wheel's own loader, by the id: `import_taskset`,
`taskset_class`, `environment_class`, `resolve_env_config`, `load_environment`.  So the file
collects on a tree that exports nothing by the id and fails there for that one reason (the
package root defines no `__all__`), except the tests of the export document's text and of the
export's turn-limit read, which fail for their own stated reasons.

Shapes decided here
-------------------

**1. The id `poisson-tasks` resolves to the package root, and the root exports two names
lazily.**  Ruled: the id is the distribution's name.  At 0.3.1 the wheel maps an id to a
top-level module by its own transformation (`owner/` and `@version` stripped, `-` to `_`,
lower-cased; `utils/loaders.py`, `_import_plugin`), so `poisson-tasks` can only ever mean
`poisson_tasks`, and of the Handoff's three shapes only "the renamed root is the id" is
consistent with the ruling.  The root's `__all__` names one `Taskset` and one `Env`, and a
module `__getattr__` (PEP 562) imports them on first lookup, which is what the loader does
(`getattr(module, name)` per listed name): `import poisson_tasks` therefore imports no
`verifiers` (MP7, the separate-module answer inside the root shape).  The two classes live in
a submodule of their own; the tests never name it or them, so both names are the build's.
*Escape hatch:* an eager re-export; `test_mp7_1` flips and the document gains the sentence.

**2. The `Env` pins two fields, and the module docstring declares them.**  `agent.harness.id`
is `null` (X9, TG-ADR-46), and `agent.runtime.type` is `subprocess`: `AgentConfig.runtime`
defaults to Prime's hosted sandbox (VN-3), a stranger has no account for one, and a run under
it would connect somewhere other than the endpoint the caller named (MP8, A11).  MP4 asks that
every pin be declared, with a reason, in the module docstring; the tests read the declaration
back as lines of the form ``- `dotted.path` = `value` -- reason``, check each is applied, and
check that the plain single-agent config given exactly those pins is the same config, so
nothing undeclared is pinned.  What else may go on the list is open point 7 of the Handoff and
is not settled here.  *Escape hatch:* the line shape; `PIN_LINE` moves.

**3. The taskset the id exports is `export.ExportTaskset` itself or a subclass that adds
nothing to `load`.**  The tests check the class through the loader and compare each loaded
task with `task_from_bundle(generate(arm, seed))`.  The taskset config defaults nothing (ruled
2026-09-22): the one-liner carries the arm, as one JSON value, and the seeds, and the one-liner
test asks that the documented command resolves to a non-empty arm and seed list.

**4. `turn_limit_hit` is `Trace.stop_condition == "max_turns"`.**  Taylor's ruling of
2026-09-21 (question 4 of the model path spec; TG-M4's open point 5), pinned here on the only
reader layer 1 has: the export's `leaky_pass` metric.  A trace the wheel stopped for a token
limit or a context length is truncated but not turn-limited, and with no reply it is
`verifier_error` -- an episode that ended for a reason the verdict's five arguments cannot
see.  Measured in a live run: the wheel stamps `max_turns` at the turn cap and
`agent_completed` on a normal end.  The built export reads `is_truncated`; no frozen TG-M4
test pins that (its row `m46` survives by design), and Session B moves it.

**5. The one-liner is read from the document and dry-run.**  MP9's byte-for-byte clause
needs the live smoke and cannot be closed here; what can be is that the fenced
`eval poisson-tasks` command in `docs/verifiers-export.md` resolves under the wheel's own CLI
with `--dry-run`, and that the config it resolves to loads by the id, runs `null` in a
subprocess with no harness named, pushes nothing, and declares an arm and seeds.
*Escape hatch:* the fenced block's first line; `one_liner()` moves.

**7. The resolved env config survives its own wire format.**  Ruled 2026-09-22 out of the
live smoke, whose whole cost bought this one row: `resolve_env_config(env_config_data(cfg))`
validates and is a fixed point.  It is the only place the config crosses a process boundary,
and `--dry-run` -- which every other config test here goes through -- exits before the serve
pool starts, so nothing else in this file reaches it.  The control is the same round trip on
a config with no arm, whose `task` stays the base `TaskConfig`.
*Escape hatch:* `env_config_data`'s name; `wire()` moves.

**6. A run's egress is measured in the test process.**  The interception server and its
outbound client run in the pytest process, so a guard on `socket.connect` that allows loopback
only holds for the whole run; the harness program and the tool server are child processes on
loopback and are outside the guard, which is recorded and not claimed.

Open, and not settled here (each is in the handoff, for a ruling)
----------------------------------------------------------------

1. **What else the env config may pin** (Handoff open point 7).  Decision 2 pins the
   declaration, not the list.
2. **MP9's byte-for-byte clause** waits on the live smoke ($20 cap, granted).

What this file does not freeze: anything that needs a real model (MP9 proper); the model
targets, the trace-to-`Run` mapping and A8's shape (layer 2, MP11 to MP18); and MP10, which
is `tests/test_tg_m5_bridge.py`'s and needs the extra.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import dataclasses
import importlib
import importlib.metadata
import inspect
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import threading
import types
from collections.abc import Iterable, Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
import verifiers.v1 as vf

from poisson_tasks.engine import apply, init_state
from poisson_tasks.knobs import ArmSpec, arm_id, levels
from poisson_tasks.tasks import FormatSpec, TaskBundle, Turn, generate, scenario_for, verify

REPO = Path(__file__).resolve().parents[1]
THIS_FILE = Path(__file__).resolve()
EXPORT_DOC = REPO / "docs" / "verifiers-export.md"

# --------------------------------------------------------------------------
# literals, each from a ruling, the spec, or a frozen module below this one
# --------------------------------------------------------------------------

TASKSET_ID = "poisson-tasks"  # ruled 2026-09-21: the new name, from the first release
ROOT_MODULE = "poisson_tasks"  # what the wheel's own transformation makes of it
OLD_ID = "task-generator"
DOTTED_ID = "poisson_tasks.export"
MEASURED_HARNESS = "null"  # X9, frozen in TG-M4 as `export.MEASURED_HARNESS`
TURN_LIMIT_STOP = "max_turns"  # ruled 2026-09-21: `turn_limit_hit` is this stop reason
TOKEN_STOPS = ("max_input_tokens", "max_output_tokens", "max_total_tokens", "context_length")
GEN_VERSION = "0"
KEY_VAR = "POISSON_TASKS_TEST_KEY"
STUB_SECRET = "stub-secret"
STUB_MODEL = "stub/model"

# 0's table, as TG-M4's oracle reads it (`State` included).  The Env's module is held to it
# the way X1 holds the export: every `verifiers` name it takes is one the spec verified.
VERIFIED_NAMES = frozenset({
    "Taskset", "Task", "TaskData", "TaskConfig", "TasksetConfig",
    "Toolset", "ToolsetConfig", "SharedToolsetConfig",
    "tool", "reward", "metric", "stop",
    "Trace", "ToolCall", "AssistantMessage", "ToolMessage", "Messages",
    "SamplingConfig", "Env", "SingleAgentEnv", "SingleAgentEnvConfig", "AgentConfig",
    "Episode", "State",
})

D_PLAIN = levels("depth")
R_PLAIN = levels("distractor")
D_CONTROLS = ((1, 8), (2, 5))
R_CONTROLS = ((0, 8), (2, 14))
SEEDS = (404, 55, 2121)


def spec_of(knob: str, level: int, control: int | None = None, strictness: str = "strict") -> ArmSpec:
    return ArmSpec(
        knob=knob, level=level, control=control, strictness=strictness,
        split="eval", generator_version=GEN_VERSION,
    )


D_SPECS = tuple(spec_of("depth", lvl) for lvl in D_PLAIN) + tuple(
    spec_of("depth", lvl, ctl) for lvl, ctl in D_CONTROLS
)
# Knob R's level axis: every level and both controls, never the one `r0`-against-`r8` pair.
R_SPECS = tuple(spec_of("distractor", lvl) for lvl in R_PLAIN) + tuple(
    spec_of("distractor", lvl, ctl) for lvl, ctl in R_CONTROLS
)
ALL_SPECS = D_SPECS + R_SPECS
SPEC_IDS = [arm_id(s) for s in ALL_SPECS]
SPEC_D3 = spec_of("depth", 3)


# --------------------------------------------------------------------------
# helpers: the build, reached by the id through the wheel's own loader
# --------------------------------------------------------------------------


def loaders() -> Any:
    """The wheel's loader module.  Its names are the wheel's, not the spec's 0 table; the
    gap log's PG-19 records them and the 0 row they are owed."""
    return importlib.import_module("verifiers.v1.utils.loaders")


def id_module() -> Any:
    return loaders().import_taskset(TASKSET_ID)


def taskset_cls() -> Any:
    return loaders().taskset_class(TASKSET_ID)


def env_cls() -> Any:
    return loaders().environment_class(TASKSET_ID)


def env_module() -> Any:
    """The module the exported `Env` is defined in.  Never named by these tests."""
    return importlib.import_module(env_cls().__module__)


def export() -> Any:
    return importlib.import_module("poisson_tasks.export")


def source_of(module: Any) -> ast.Module:
    path = Path(inspect.getsourcefile(module) or "")
    return ast.parse(path.read_text(encoding="utf-8"))


def env_config(**over: Any) -> Any:
    """The env config the wheel resolves for the id, the way the CLI and the env server do:
    the taskset id and whatever the caller adds, narrowed to the id's own config type."""
    return vf.resolve_env_config({"taskset": {"id": TASKSET_ID}, **over})


def plain_config(**over: Any) -> Any:
    """The wheel's plain single-agent config for the same taskset: the known-positive
    control, whose harness resolves to `bash` (measured, `probe7.out`)."""
    return vf.SingleAgentEnvConfig.model_validate({"taskset": {"id": TASKSET_ID}, **over})


def harness_of(config: Any) -> Any:
    return config.agent_harnesses()["agent"]


def taskset_of(spec: ArmSpec, seeds: Iterable[int]) -> Any:
    config_type = loaders().taskset_config_type(TASKSET_ID)
    return taskset_cls()(config_type(id=TASKSET_ID, arm=dataclasses.asdict(spec), seeds=list(seeds)))


def wheel_transform(ident: str) -> str:
    """The wheel's own id-to-module rule, restated (`_import_plugin`)."""
    return ident.rsplit("/", 1)[-1].split("@", 1)[0].replace("-", "_").lower()


def flat(value: Any, prefix: str = "") -> dict[str, Any]:
    """A config dump as dotted leaves, lists as leaves."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            out.update(flat(item, f"{prefix}{key}."))
        return out
    return {prefix[:-1]: value}


def dig(data: Any, path: str) -> Any:
    for part in path.split("."):
        data = data[part]
    return data


def set_path(data: dict[str, Any], path: str, value: Any) -> None:
    *parents, leaf = path.split(".")
    for part in parents:
        data = data.setdefault(part, {})
    data[leaf] = value


# ``- `agent.harness.id` = `null` -- the reason``: decision 2's declaration line.
PIN_LINE = re.compile(r"^- `([a-z_][a-z0-9_.]*)` = `([^`]+)` -- (.+?)\s*$", re.M)


def declared_pins() -> dict[str, tuple[str, str]]:
    doc = env_module().__doc__ or ""
    return {path: (value, reason) for path, value, reason in PIN_LINE.findall(doc)}


def fresh(code: str) -> str:
    """Run `code` in a fresh interpreter with this one's environment, and give its stdout."""
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-3000:]
    return done.stdout.strip()


# --------------------------------------------------------------------------
# helpers: the wheel's own CLI, in dry-run
# --------------------------------------------------------------------------

EVAL_MAIN = "import sys; from verifiers.v1.cli.eval.main import main; main(sys.argv[1:])"


def dry_run(*args: str, env: dict[str, str] | None = None) -> dict[str, Any]:
    """`eval <args> --dry-run`: the CLI resolves and validates the whole run config, writes
    it and exits without a model call or a push.  Gives the resolved config."""
    with tempfile.TemporaryDirectory() as tmp:
        done = subprocess.run(
            [sys.executable, "-c", EVAL_MAIN, *args, "--dry-run", "-o", tmp],
            cwd=tmp, env={**os.environ, **(env or {})}, capture_output=True, text=True, timeout=300,
        )
        assert done.returncode == 0, (done.stdout + done.stderr)[-3000:]
        files = list(Path(tmp).glob("*/configs/resolved/eval.json"))
        assert len(files) == 1, files
        return json.loads(files[0].read_text(encoding="utf-8"))


def dry_run_refused(*args: str) -> str:
    """The same, for a command the CLI must refuse: gives what it printed."""
    with tempfile.TemporaryDirectory() as tmp:
        done = subprocess.run(
            [sys.executable, "-c", EVAL_MAIN, *args, "--dry-run", "-o", tmp],
            cwd=tmp, capture_output=True, text=True, timeout=300,
        )
        assert done.returncode != 0, done.stdout[-2000:]
        return done.stdout + done.stderr


def export_doc() -> str:
    return EXPORT_DOC.read_text(encoding="utf-8")


def one_liner() -> str:
    """The fenced `eval poisson-tasks` command in the export document, as one line."""
    for block in re.findall(r"```[^\n]*\n(.*?)```", export_doc(), re.S):
        lines = block.strip().splitlines()
        if lines and f"eval {TASKSET_ID}" in lines[0]:
            return " ".join(line.rstrip("\\").strip() for line in lines)
    raise AssertionError(f"docs/verifiers-export.md has no fenced `eval {TASKSET_ID}` command")


DUMMY_ENV = {"MODEL": STUB_MODEL, "MODEL_BASE_URL": "http://127.0.0.1:9/v1", "MODEL_API_KEY": "k"}


def one_liner_args() -> tuple[list[str], dict[str, str]]:
    """The command's arguments after `uv run eval`, with every `$VAR` it names bound to a
    dummy, and the environment those dummies make."""
    command = one_liner()
    names = set(re.findall(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", command))
    env = {name: DUMMY_ENV.get(name, f"dummy-{name}") for name in names}
    words = shlex.split(os.path.expandvars(command) if not names else _expand(command, env))
    assert words[:3] == ["uv", "run", "eval"], words[:3]
    return words[3:], env


def _expand(command: str, env: dict[str, str]) -> str:
    saved = {name: os.environ.get(name) for name in env}
    os.environ.update(env)
    try:
        return os.path.expandvars(command)
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


# --------------------------------------------------------------------------
# helpers: a stub endpoint, a loopback guard, one episode through the wheel
# --------------------------------------------------------------------------

Script = list[tuple[str, tuple[str, Any] | None]]


def reference_script(bundle: TaskBundle) -> Script:
    return [("tool_calls", call) for call in bundle.reference_calls] + [("stop", None)]


@contextlib.contextmanager
def stub_endpoint(script: Script) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """An OpenAI-compatible chat endpoint on loopback that answers turn `i` with `script[i]`
    (the last entry repeats) and logs every request it sees."""
    log: list[dict[str, Any]] = []
    state = {"turn": 0}

    class Stub(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            log.append({
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "model": body.get("model"),
                "messages": body.get("messages"),
                "tools": [tool["function"]["name"] for tool in body.get("tools") or []],
            })
            kind, call = script[min(state["turn"], len(script) - 1)]
            state["turn"] += 1
            if kind == "tool_calls":
                assert call is not None
                name, arguments = call
                message: dict[str, Any] = {
                    "role": "assistant", "content": None,
                    "tool_calls": [{"id": f"call_{state['turn']}", "type": "function",
                                    "function": {"name": name, "arguments": json.dumps(arguments)}}],
                }
            else:
                message = {"role": "assistant", "content": "Done."}
            out = {
                "id": "chatcmpl-stub", "object": "chat.completion", "created": 0,
                "model": body.get("model"),
                "choices": [{"index": 0, "message": message, "finish_reason": kind}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
            data = json.dumps(out).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = HTTPServer(("127.0.0.1", 0), Stub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", log
    finally:
        server.shutdown()
        server.server_close()


LOOPBACK = {"127.0.0.1", "::1", "localhost"}


@contextlib.contextmanager
def loopback_only() -> Iterator[list[Any]]:
    """Refuse any connection this process opens to a host that is not loopback (decision 6).
    Gives the list of refused addresses, which must stay empty."""
    refused: list[Any] = []
    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex

    def host_of(address: Any) -> Any:
        return address[0] if isinstance(address, tuple) else address

    def connect(self: Any, address: Any) -> Any:
        host = host_of(address)
        if isinstance(host, str) and host not in LOOPBACK:
            refused.append(address)
            raise OSError(f"the test forbids a connection to {address!r}")
        return real_connect(self, address)

    def connect_ex(self: Any, address: Any) -> Any:
        host = host_of(address)
        if isinstance(host, str) and host not in LOOPBACK:
            refused.append(address)
            return 111
        return real_connect_ex(self, address)

    socket.socket.connect = connect  # type: ignore[method-assign]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]
    try:
        yield refused
    finally:
        socket.socket.connect = real_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = real_connect_ex  # type: ignore[method-assign]


@dataclasses.dataclass
class Ran:
    episode: Any
    log: list[dict[str, Any]]
    task: Any
    bundle: TaskBundle
    refused: list[Any]

    @property
    def trace(self) -> Any:
        assert len(self.episode.traces) == 1, self.episode.traces
        return self.episode.traces[0]


def run_one(spec: ArmSpec, seed: int, script: Script | None = None, **over: Any) -> Ran:
    """One episode of `generate(spec, seed)` through the wheel's own lifecycle, resolved by
    the id with nothing named but the taskset, against the stub."""
    bundle = generate(spec, seed)
    saved = os.environ.get(KEY_VAR)
    os.environ[KEY_VAR] = STUB_SECRET
    try:
        with stub_endpoint(script or reference_script(bundle)) as (base_url, log), loopback_only() as refused:
            config = env_config(
                taskset={"id": TASKSET_ID, "arm": dataclasses.asdict(spec), "seeds": [seed]}, **over
            )
            env = vf.load_environment(config)
            task = next(iter(env.taskset.load()))
            ctx = vf.ModelContext(
                model=STUB_MODEL, client=vf.EvalClientConfig(base_url=base_url, api_key_var=KEY_VAR)
            )

            async def go() -> Any:
                async with env.serving():
                    return await env.run_episode(task, ctx)

            episode = asyncio.run(go())
    finally:
        if saved is None:
            os.environ.pop(KEY_VAR, None)
        else:
            os.environ[KEY_VAR] = saved
    return Ran(episode, log, task, bundle, refused)


def prompt_messages(bundle: TaskBundle) -> list[dict[str, Any]]:
    """What the first request's messages must be: the system prompt, then the prompt."""
    if isinstance(bundle.prompt, str):
        return [{"role": "system", "content": bundle.system_prompt}, {"role": "user", "content": bundle.prompt}]
    return [{"role": "system", "content": bundle.system_prompt}, *bundle.prompt]


def same_message(wire: dict[str, Any], expected: dict[str, Any]) -> bool:
    """A seeded assistant message crosses the wire with an explicit `content: null`, which
    the OpenAI shape allows and the bundle leaves out; everything else is byte for byte."""
    wire = {k: v for k, v in wire.items() if not (k == "content" and v is None)}
    expected = {k: v for k, v in expected.items() if not (k == "content" and v is None)}
    return wire == expected


# --------------------------------------------------------------------------
# helpers: synthetic traces (TG-M4's shape), for the export's turn-limit read
# --------------------------------------------------------------------------

NO_MARKERS = FormatSpec(name="test", markers=())


def turns_of(calls: Iterable[tuple[str, Any]], reply: bool) -> tuple[Turn, ...]:
    turns = [Turn(content="", calls=(call,), finish_reason="tool_calls") for call in calls]
    if reply:
        turns.append(Turn(content="Done.", calls=(), finish_reason="stop"))
    return tuple(turns)


def live_observations(bundle: TaskBundle, calls: Iterable[tuple[str, Any]]) -> list[str]:
    state = init_state(scenario_for(bundle.seed, bundle.split), bundle.seq_start)
    names = {str(tool["name"]) for tool in bundle.tools}
    out: list[str] = []
    for name, args in calls:
        if not isinstance(args, dict):
            out.append("error: tool arguments must be a JSON object, got "
                       f"{type(json.loads(json.dumps(args))).__name__}; resend as an object")
        elif name not in names:
            out.append(f"error: unknown tool {name!r}")
        else:
            state, observation = apply(state, (name, args))
            out.append(observation)
    return out


def seeded_nodes(task: Any) -> list[Any]:
    prompt = task.data.prompt
    if isinstance(prompt, str):
        return [vf.MessageNode(parent=None, message=vf.UserMessage(content=prompt), sampled=False)]
    return [
        vf.MessageNode(parent=index - 1 if index else None, message=message, sampled=False)
        for index, message in enumerate(prompt)
    ]


def trace_of(task: Any, bundle: TaskBundle, calls: Iterable[tuple[str, Any]], *,
             reply: bool, stop: str | None) -> Any:
    """A synthetic `vf.Trace` as the `null` harness leaves one, stopped for `stop`."""
    calls = list(calls)
    nodes = seeded_nodes(task)
    for index, ((name, args), observation) in enumerate(zip(calls, live_observations(bundle, calls))):
        call_id = f"sampled-{index}"
        arguments = json.dumps(list(args) if isinstance(args, tuple) else args)
        assistant = vf.AssistantMessage(
            content="", tool_calls=[vf.ToolCall(id=call_id, name=name, arguments=arguments)]
        )
        nodes.append(vf.MessageNode(parent=len(nodes) - 1, message=assistant, sampled=True))
        tool = vf.ToolMessage(tool_call_id=call_id, content=observation, name=name)
        nodes.append(vf.MessageNode(parent=len(nodes) - 1, message=tool, sampled=False))
    if reply:
        nodes.append(vf.MessageNode(parent=len(nodes) - 1, message=vf.AssistantMessage(content="Done."), sampled=True))
    return vf.Trace(
        task=vf.TraceTask(type=type(task).__name__, data=task.data, key=task.key, hash=task.hash),
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        nodes=nodes,
        stop_condition=stop,
    )


def scored(task: Any, trace: Any) -> Any:
    asyncio.run(task.score(trace, None))
    return trace


def leaky_of(task: Any, bundle: TaskBundle, calls: Iterable[tuple[str, Any]], *, reply: bool, stop: str | None) -> float:
    trace = scored(task, trace_of(task, bundle, calls, reply=reply, stop=stop))
    value = trace.metrics["leaky_pass"]
    assert value is not None
    return float(value)


def strict_of(task: Any, bundle: TaskBundle, calls: Iterable[tuple[str, Any]], *, reply: bool, stop: str | None) -> float:
    trace = scored(task, trace_of(task, bundle, calls, reply=reply, stop=stop))
    return float(trace.rewards["strict"].score)


# --------------------------------------------------------------------------
# helpers: `ast` walkers, TG-M4's
# --------------------------------------------------------------------------


def imported_modules(tree: ast.AST) -> set[str]:
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


PROOFLOAD_SIDE = ("proofload", "poisson_tasks.adapter")


def needs_proofload(modules: set[str]) -> set[str]:
    return {m for m in modules if any(m == side or m.startswith(side + ".") for side in PROOFLOAD_SIDE)}


def layer_closure() -> dict[str, ast.Module]:
    """Every module of the package the id module and the Env's module import, transitively,
    by source: the layer MP6 speaks of."""
    seen: dict[str, ast.Module] = {}
    queue = [id_module().__name__, env_module().__name__]
    while queue:
        name = queue.pop()
        if name in seen or not (name == ROOT_MODULE or name.startswith(ROOT_MODULE + ".")):
            continue
        tree = source_of(importlib.import_module(name))
        seen[name] = tree
        for imported in imported_modules(tree):
            if imported == ROOT_MODULE or imported.startswith(ROOT_MODULE + "."):
                queue.append(imported)
    return seen


def unverified_verifiers_names(tree: ast.Module) -> set[str]:
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


def public_names(module: Any) -> set[str]:
    """The public names of a module that are not submodules of it and not the `annotations`
    future import."""
    return {
        name for name, value in vars(module).items()
        if not name.startswith("_") and name != "annotations" and not isinstance(value, types.ModuleType)
    }


def fake_taskset_module(name: str, all_names: list[str], **attrs: Any) -> Any:
    module = types.ModuleType(name)
    module.__all__ = list(all_names)  # type: ignore[attr-defined]
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


# --------------------------------------------------------------------------
# SF - this file, and the Env's module, held to the standing rules
# --------------------------------------------------------------------------


def test_sf1_this_file_imports_no_proofload_and_no_adapter():
    """Ruled 2026-09-21: Tasks is standalone, and no test here may need Prove."""
    tree = ast.parse(THIS_FILE.read_text(encoding="utf-8"))
    assert needs_proofload(imported_modules(tree)) == set()


def test_sf2_the_envs_module_takes_only_verified_names_from_verifiers():
    """X1's rule, applied to the module the id's `Env` lives in: a `verifiers` name it takes
    is one 0 verified.  The root takes none at all (MP7)."""
    assert unverified_verifiers_names(source_of(env_module())) == set()
    assert unverified_verifiers_names(source_of(id_module())) == set()
    assert not any(
        name == "verifiers" or name.startswith("verifiers.")
        for name in imported_modules(source_of(id_module()))
    )


def test_sf3_the_walker_flags_each_way_an_unverified_name_gets_in():
    cases = {
        "import verifiers.v1 as vf\nx = vf.NotVerified\n": {"NotVerified"},
        "from verifiers.v1 import NotVerified\n": {"NotVerified"},
        "import verifiers.v1.utils.loaders\n": {"import verifiers.v1.utils.loaders"},
        "import verifiers.v1 as vf\nx = getattr(vf, 'Taskset')\n": {"getattr on the verifiers alias"},
        "import verifiers.v1 as vf\nx = vf.Taskset\n": set(),
    }
    for source, expected in cases.items():
        assert unverified_verifiers_names(ast.parse(source)) == expected, source


# --------------------------------------------------------------------------
# MP1 - the id resolves
# --------------------------------------------------------------------------


def test_mp1_1_the_id_is_the_distribution_name_and_resolves_to_the_root():
    """MP1: one string, the distribution's name, matching the module under the wheel's own
    transformation.  The hub forms the wheel strips resolve to the same module."""
    assert importlib.metadata.distribution(TASKSET_ID).metadata["Name"] == TASKSET_ID
    module = id_module()
    assert module.__name__ == ROOT_MODULE == wheel_transform(TASKSET_ID)
    for form in (TASKSET_ID, f"poisson-labs/{TASKSET_ID}", f"{TASKSET_ID}@0.0.1", TASKSET_ID.upper()):
        assert loaders().import_taskset(form) is module, form


def test_mp1_2_the_id_resolves_to_the_exports_taskset_and_adds_nothing_to_load():
    cls = taskset_cls()
    assert issubclass(cls, export().ExportTaskset)
    assert cls.load is export().ExportTaskset.load
    assert cls.INFINITE is False
    assert issubclass(loaders().taskset_config_type(TASKSET_ID), export().ExportTasksetConfig)


@pytest.mark.parametrize("spec", ALL_SPECS, ids=SPEC_IDS)
def test_mp1_3_a_task_loaded_by_the_id_is_the_generated_bundle(spec):
    """MP1: "that class builds a task equal to `task_from_bundle(generate(arm, seed))`"."""
    tasks = list(taskset_of(spec, SEEDS).load())
    assert len(tasks) == len(SEEDS)
    for task, seed in zip(tasks, SEEDS):
        bundle = generate(spec, seed)
        assert type(task) is export().ExportTask
        assert task.key == bundle.task_id
        assert export().bundle_from_data(task.data) == bundle
        assert task.data == export().task_from_bundle(bundle).data


def test_mp1_4_a_dotted_id_and_the_old_id_are_refused():
    """MP1's control: the wheel refuses both, and the refusal is read, not assumed.  A dotted
    id fails inside the wheel's own namespace probe (`verifiers.v1.tasksets.<id>`) before it
    is looked up bare, so its message names that path and not the id (measured, `probe7.out`);
    the old id fails as a plain missing module and its message names it."""
    with pytest.raises(ModuleNotFoundError) as dotted:
        loaders().import_taskset(DOTTED_ID)
    assert "verifiers.v1.tasksets.poisson_tasks" in str(dotted.value)
    with pytest.raises(ModuleNotFoundError) as old:
        loaders().import_taskset(OLD_ID)
    assert OLD_ID in str(old.value)


def test_mp1_5_the_cli_refuses_the_same_two_ids():
    assert OLD_ID in dry_run_refused(OLD_ID, "--no-push")
    assert "poisson_tasks" in dry_run_refused(DOTTED_ID, "--no-push")


# --------------------------------------------------------------------------
# MP2 - one id, one taskset, one Env, no harness
# --------------------------------------------------------------------------


def test_mp2_1_all_is_exactly_one_taskset_and_one_env_and_no_harness():
    module = id_module()
    names = list(module.__all__)
    assert len(names) == 2, names
    objects = [getattr(module, name) for name in names]
    assert all(isinstance(obj, type) for obj in objects)
    assert sum(issubclass(obj, vf.Taskset) for obj in objects) == 1
    assert sum(issubclass(obj, vf.Env) for obj in objects) == 1
    assert not any(issubclass(obj, vf.Harness) for obj in objects)
    assert taskset_cls() in objects and env_cls() in objects


def test_mp2_2_the_taskset_bundles_no_harness_so_the_default_is_the_envs_pin():
    """`default_harness_id` reads a bundled `Harness` and finds none: the taskset's own
    default stays `bash`, and it is the exported `Env`'s config that makes a run `null`."""
    assert loaders().default_harness_id(TASKSET_ID) == "bash"
    with pytest.raises(TypeError):
        loaders().harness_class(TASKSET_ID)


def test_mp2_3_nothing_public_leaks_past_all_at_the_root():
    module = id_module()
    for name in module.__all__:
        getattr(module, name)  # the lazy names become attributes; they are listed
    assert public_names(module) <= set(module.__all__), public_names(module) - set(module.__all__)


def test_mp2_4_nothing_public_leaks_past_all_in_the_envs_module():
    module = env_module()
    assert hasattr(module, "__all__")
    assert public_names(module) == set(module.__all__)
    assert env_cls().__name__ in module.__all__


def test_mp2_5_two_of_either_raise_inside_the_wheel_and_an_unlisted_env_is_invisible():
    """Why MP2 is an invariant and not a style (VN-8), measured on fakes."""
    taskset = taskset_cls()
    env = env_cls()
    other_env = type("OtherEnv", (env,), {})
    other_taskset = type("OtherTaskset", (taskset,), {})
    fake_taskset_module("mp2_two_envs", ["A", "B", "C"], A=taskset, B=env, C=other_env)
    with pytest.raises(ValueError):
        loaders().environment_class("mp2_two_envs")
    fake_taskset_module("mp2_two_tasksets", ["A", "B", "C"], A=taskset, B=other_taskset, C=env)
    with pytest.raises(ValueError):
        loaders().taskset_class("mp2_two_tasksets")
    fake_taskset_module("mp2_hidden_env", ["A"], A=taskset, B=env)
    assert loaders().environment_class("mp2_hidden_env") is vf.SingleAgentEnv
    assert harness_of(vf.resolve_env_config({"taskset": {"id": "mp2_hidden_env"}})).id == "bash"


# --------------------------------------------------------------------------
# MP3 - the default harness is the measured one
# --------------------------------------------------------------------------


def test_mp3_1_no_flag_resolves_to_the_measured_harness():
    config = env_config()
    harness = harness_of(config)
    assert harness.id == export().MEASURED_HARNESS == MEASURED_HARNESS
    assert type(loaders().load_harness(harness)).__name__ == "NullHarness"
    assert isinstance(config, vf.SingleAgentEnvConfig)
    assert type(config) is not vf.SingleAgentEnvConfig


def test_mp3_2_the_plain_single_agent_config_resolves_to_bash():
    """The known-positive control (measured, `probe7.out`): without the exported `Env`, the
    same taskset runs `bash`."""
    assert harness_of(plain_config()).id == "bash"


def test_mp3_3_the_cli_with_nothing_named_but_the_id_resolves_null_in_a_subprocess():
    config = dry_run(TASKSET_ID, "--no-push")
    env = config["env"]
    assert env["taskset"]["id"] == TASKSET_ID
    assert env["id"] == ""  # the taskset's own env; no `--env.id` is needed
    assert env["agent"]["harness"]["id"] == MEASURED_HARNESS
    assert env["agent"]["runtime"]["type"] == "subprocess"


@pytest.mark.parametrize("spec", ALL_SPECS, ids=SPEC_IDS)
def test_mp3_4_the_measured_harness_runs_the_reference_by_the_id_alone(spec):
    """The invariant at run time, over every arm: resolved by the id with no harness named,
    the wheel's own lifecycle runs `null` in a subprocess against the endpoint the caller
    named, hands the model the bundle's prompt and its block bare and in slot order, and the
    export scores the reference 1.0.  A control's seeded history reaches the endpoint
    verbatim, and every request the run makes reaches the stub."""
    ran = run_one(spec, SEEDS[0])
    episode, trace, bundle = ran.episode, ran.trace, ran.bundle
    assert episode.ok and not episode.errors, [str(e) for e in episode.errors]
    assert trace.agent.config.harness.id == MEASURED_HARNESS
    assert trace.agent.runtime.type == "subprocess"
    assert trace.stop_condition == "agent_completed"
    assert trace.rewards["strict"].score == 1.0
    assert trace.metrics["leaky_pass"] == 1.0
    assert trace.num_turns == len(bundle.reference_calls) + 1
    # what the model saw, request by request
    assert len(ran.log) == len(trace.calls) == len(bundle.reference_calls) + 1
    block = [str(tool["name"]) for tool in bundle.tools]
    for request in ran.log:
        assert request["path"].endswith("/chat/completions")
        assert request["model"] == STUB_MODEL
        assert request["authorization"] == f"Bearer {STUB_SECRET}"
        assert request["tools"] == block
    first = ran.log[0]["messages"]
    expected = prompt_messages(bundle)
    assert len(first) == len(expected)
    assert all(same_message(w, e) for w, e in zip(first, expected)), (first[:3], expected[:3])
    # the live observations are the reference observations, numbered from `seq_start`
    live = [m.content for m in trace.tool_messages][-len(bundle.reference_calls):]
    assert live == list(bundle.reference_observations)
    assert ran.refused == []


# --------------------------------------------------------------------------
# MP4 - the Env pins the harness and declares everything else it pins
# --------------------------------------------------------------------------


def test_mp4_1_every_pin_is_declared_and_nothing_undeclared_is_pinned():
    pins = declared_pins()
    assert pins, "the Env's module declares no pins"
    assert pins["agent.harness.id"][0] == MEASURED_HARNESS
    pinned = env_config().model_dump(mode="json")
    for path, (value, _reason) in pins.items():
        assert str(dig(pinned, path)) == value, path
    data: dict[str, Any] = {"taskset": {"id": TASKSET_ID}}
    for path, (value, _reason) in pins.items():
        set_path(data, path, value)
    assert flat(pinned) == flat(vf.SingleAgentEnvConfig.model_validate(data).model_dump(mode="json"))


def test_mp4_2_each_declared_pin_carries_a_reason():
    for path, (_value, reason) in declared_pins().items():
        assert len(reason.split()) >= 8, path


def test_mp4_3_the_pins_show_in_the_saved_config():
    """Why MP4 matters: a pin is in the saved run config, not only in source."""
    env = dry_run(TASKSET_ID, "--no-push")["env"]
    for path, (value, _reason) in declared_pins().items():
        assert str(dig(env, path)) == value, path


# --------------------------------------------------------------------------
# MP5 - a flag still wins
# --------------------------------------------------------------------------


def test_mp5_1_a_named_harness_wins_over_the_pin_and_the_other_pin_stays():
    config = env_config(agent={"harness": {"id": "bash"}})
    assert harness_of(config).id == "bash"
    assert type(config) is type(env_config())
    assert config.agent.runtime.type == "subprocess"


def test_mp5_2_a_named_runtime_wins_over_the_pin_and_the_other_pin_stays():
    config = env_config(agent={"runtime": {"type": "prime"}})
    assert config.agent.runtime.type == "prime"
    assert harness_of(config).id == MEASURED_HARNESS


def test_mp5_3_at_the_cli_the_pin_is_a_default_and_not_a_lock():
    """Measured, not assumed: 0.3.1 deep-merges a role's flags over the declared instance."""
    env = dry_run(TASKSET_ID, "--env.agent.harness.id", "bash", "--no-push")["env"]
    assert env["agent"]["harness"]["id"] == "bash"


def test_mp5_4_the_docs_name_the_override_and_say_it_leaves_the_pin_ledger():
    doc = export_doc()
    assert "--env.agent.harness.id" in doc
    assert "outside the pin ledger" in doc


# --------------------------------------------------------------------------
# MP6 - Prove stays optional
# --------------------------------------------------------------------------


def test_mp6_1_the_layer_imports_no_proofload_and_no_adapter():
    """The id module, the Env's module, and every package module they import, by an `ast`
    walk that reads `import_module` strings too."""
    closure = layer_closure()
    assert ROOT_MODULE in closure and env_module().__name__ in closure
    for name, tree in closure.items():
        assert needs_proofload(imported_modules(tree)) == set(), name


def test_mp6_2_the_walker_sees_each_shape_of_import():
    cases = {
        "import proofload\n": {"proofload"},
        "from proofload import Episode\n": {"proofload"},
        "import importlib\nimportlib.import_module('poisson_tasks.adapter')\n": {"poisson_tasks.adapter"},
        "__import__('proofload.store')\n": {"proofload.store"},
        "import poisson_tasks.export\n": set(),
    }
    for source, expected in cases.items():
        assert needs_proofload(imported_modules(ast.parse(source))) == expected, source


# --------------------------------------------------------------------------
# MP7 - the root import is pinned: the separate-module shape
# --------------------------------------------------------------------------


def test_mp7_1_importing_the_package_or_the_generator_imports_no_verifiers():
    out = fresh(
        "import sys, poisson_tasks, poisson_tasks.tasks, poisson_tasks.knobs, poisson_tasks.engine;"
        " print('verifiers' in sys.modules, poisson_tasks.__all__)"
    )
    assert out.startswith("False "), out


def test_mp7_2_looking_the_exported_names_up_is_what_imports_verifiers():
    out = fresh(
        "import sys, poisson_tasks;"
        " names = [getattr(poisson_tasks, n).__name__ for n in poisson_tasks.__all__];"
        " print('verifiers' in sys.modules, len(names))"
    )
    assert out == "True 2", out


# --------------------------------------------------------------------------
# MP8 - nothing is pushed
# --------------------------------------------------------------------------


def test_mp8_1_push_is_the_runs_and_the_env_cannot_turn_it_off():
    """Measured: `push` is a field of the run config and on by default, and an env config
    that carries a `push` of its own is not read (the plain config refuses the extra field;
    the id's own config keeps it as an attribute the run never looks at).  So the document
    names `--no-push`, and the one-liner has it."""
    eval_config = importlib.import_module("verifiers.v1.configs.cli.eval").EvalConfig
    assert eval_config(env=env_config()).push is True
    pushing = type("Pushing", (type(env_config()),), {"__annotations__": {"push": bool}, "push": False})
    assert eval_config(env=pushing(taskset={"id": TASKSET_ID})).push is True
    with pytest.raises(Exception, match="push"):
        eval_config(env=vf.SingleAgentEnvConfig.model_validate({"taskset": {"id": TASKSET_ID}, "push": False}))
    assert dry_run(TASKSET_ID)["push"] is True
    assert dry_run(TASKSET_ID, "--no-push")["push"] is False
    assert "--no-push" in one_liner()


def test_mp8_2_the_runtime_is_local_and_the_plain_one_is_not():
    runtimes = importlib.import_module("verifiers.v1.runtimes")
    assert isinstance(env_config().agent.runtime, vf.SubprocessConfig)
    assert runtimes.runtime_is_local(env_config().agent.runtime) is True
    assert isinstance(plain_config().agent.runtime, vf.PrimeConfig)
    assert runtimes.runtime_is_local(plain_config().agent.runtime) is False


def test_mp8_3_no_connection_at_import_or_at_task_build():
    """In a fresh interpreter with every `connect` refused: resolve by the id, build the
    taskset and its tasks, and build the env (which loads the harness)."""
    code = f"""
import socket, dataclasses, sys
def refuse(self, address): raise AssertionError(f"connection to {{address!r}}")
socket.socket.connect = refuse; socket.socket.connect_ex = refuse; socket.create_connection = refuse
import verifiers.v1 as vf
from verifiers.v1.utils import loaders
from poisson_tasks.knobs import ArmSpec
spec = ArmSpec(knob="depth", level=3, control=None, strictness="strict", split="eval", generator_version="0")
cls = loaders.taskset_class({TASKSET_ID!r}); env_cls = loaders.environment_class({TASKSET_ID!r})
config = vf.resolve_env_config({{"taskset": {{"id": {TASKSET_ID!r}, "arm": dataclasses.asdict(spec), "seeds": [404, 55]}}}})
env = vf.load_environment(config)
tasks = list(env.taskset.load())
print(type(env).__name__ == env_cls.__name__, len(tasks), tasks[0].key == tasks[0].data.task_id)
"""
    assert fresh(code) == "True 2 True"


# --------------------------------------------------------------------------
# MP9 - the documented one-liner is the tested one (the half that needs no model)
# --------------------------------------------------------------------------


def test_mp9_1_the_documented_one_liner_resolves_and_pins_the_run():
    args, env = one_liner_args()
    config = dry_run(*args, env=env)
    assert config["env"]["taskset"]["id"] == TASKSET_ID
    assert config["env"]["id"] == ""
    assert config["env"]["agent"]["harness"]["id"] == MEASURED_HARNESS
    assert config["env"]["agent"]["runtime"]["type"] == "subprocess"
    assert config["push"] is False
    assert config["env"]["taskset"]["arm"], "the one-liner resolves to no arm"
    assert config["env"]["taskset"]["seeds"], "the one-liner resolves to no seeds"
    assert config["client"]["base_url"] == env.get("MODEL_BASE_URL", config["client"]["base_url"])


def test_mp9_2_the_one_liner_names_no_harness_and_no_env():
    """The one-liner exercises the default; naming `null` on it would hide MP3."""
    args, _env = one_liner_args()
    assert not any(arg.startswith("--env.agent.harness") for arg in args), args
    assert not any(arg.startswith("--env.id") for arg in args), args
    assert args[0] == TASKSET_ID


def test_mp9_3_the_one_liner_resolves_to_tasks_the_generator_would_make():
    args, env = one_liner_args()
    taskset = dry_run(*args, env=env)["env"]["taskset"]
    spec = ArmSpec(**taskset["arm"])
    tasks = list(taskset_of(spec, taskset["seeds"]).load())
    assert [task.key for task in tasks] == [generate(spec, seed).task_id for seed in taskset["seeds"]]


# --------------------------------------------------------------------------
# W - the resolved env config survives its own wire format (ruled 2026-09-22)
# --------------------------------------------------------------------------


def wire(config: Any) -> dict[str, Any]:
    """The env config as the serve pool ships it to the env server process.

    `serve/pool.py`'s `env_config_data` is a `model_dump(mode="json")`, and `serve_env` on
    the far side rebuilds it with `resolve_env_config`.  That round trip happens in exactly
    one place, and `--dry-run` -- which every other config test here uses -- writes the
    resolved config and exits before the serve pool starts, so nothing else reaches it."""
    return dict(importlib.import_module("verifiers.v1.serve.pool").env_config_data(config))


def test_w1_the_resolved_env_config_survives_its_own_wire_format():
    """The invariant the 2026-09-22 live smoke bought, ruled the same day: a config the
    wheel resolved must validate again from its own dump, and be a fixed point under it.

    `TasksetConfig.task` is `SerializeAsAny[TaskConfig]`, so the dump is duck-typed and
    carries whatever subclass the field holds -- but the annotation is still the base
    `TaskConfig`, which forbids extras.  A dict from the dump is therefore validated
    narrow while it was written wide, and the env server dies on a config the CLI itself
    produced, after the run has started and with nothing said at the top level.  The dump's
    width is asserted first, against the base `TaskConfig`'s own fields: without a dump
    wider than the annotation there is nothing for the narrow validation to refuse, and the
    round trip would pass for the wrong reason."""
    config = env_config(taskset={"id": TASKSET_ID, "arm": dataclasses.asdict(SPEC_D3), "seeds": [404, 55, 2121]})
    data = wire(config)
    assert set(data["taskset"]["task"]) > set(vf.TaskConfig().model_dump(mode="json")), (
        "the dump carries no more than the base `TaskConfig`'s own fields, so the narrow "
        "validation below cannot fail and this test pins nothing"
    )

    again = vf.resolve_env_config(data)

    assert wire(again) == data, "the round trip validates but is not a fixed point"
    assert type(again.taskset.task) is type(config.taskset.task)
    assert again.taskset.task.strictness == config.taskset.task.strictness
    assert again.taskset.task.arm_id == config.taskset.task.arm_id != ""
    assert again.agent.harness.id == MEASURED_HARNESS
    assert again.agent.runtime.type == "subprocess"


def test_w2_a_config_with_no_arm_round_trips_the_known_positive_control():
    """The control: the same round trip on a config whose `task` is the base `TaskConfig`,
    because no arm was given and the taskset config derives nothing.  It passes on the tree
    that fails `test_w1`, which is what locates the failure in the derived subclass rather
    than in the wheel's dump-and-load."""
    config = env_config()
    data = wire(config)
    again = vf.resolve_env_config(data)
    assert wire(again) == data


# --------------------------------------------------------------------------
# TL - `turn_limit_hit` reads the stop reason (ruled 2026-09-21)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("spec", ALL_SPECS, ids=SPEC_IDS)
def test_tl1_a_max_turns_stop_without_a_reply_is_a_turn_limit(spec):
    """The reference calls, no reply, stopped at `max_turns`: the target is at its goal, so
    `leaky_pass` is what `verify` says with the flag set, and `strict` is 0."""
    bundle = generate(spec, SEEDS[0])
    task = export().task_from_bundle(bundle)
    calls = list(bundle.reference_calls)
    expected = verify(bundle, turns_of(calls, False), False, True, NO_MARKERS)
    assert expected.strict_label == "turn_limit" and expected.leaky_pass is True
    assert leaky_of(task, bundle, calls, reply=False, stop=TURN_LIMIT_STOP) == 1.0
    assert strict_of(task, bundle, calls, reply=False, stop=TURN_LIMIT_STOP) == 0.0


@pytest.mark.parametrize("stop", TOKEN_STOPS)
def test_tl2_a_token_or_context_stop_is_truncated_but_not_a_turn_limit(stop):
    """The discriminating row: the same nodes, stopped for a token limit.  `is_truncated` is
    true for both; only `stop_condition` tells them apart, and the ruling reads it."""
    bundle = generate(SPEC_D3, SEEDS[0])
    task = export().task_from_bundle(bundle)
    calls = list(bundle.reference_calls)
    assert trace_of(task, bundle, calls, reply=False, stop=stop).is_truncated is True
    assert trace_of(task, bundle, calls, reply=False, stop=TURN_LIMIT_STOP).is_truncated is True
    assert leaky_of(task, bundle, calls, reply=False, stop=TURN_LIMIT_STOP) == 1.0
    assert leaky_of(task, bundle, calls, reply=False, stop=stop) == 0.0
    expected = verify(bundle, turns_of(calls, False), False, False, NO_MARKERS)
    assert expected.label == "verifier_error" and expected.leaky_pass is False


@pytest.mark.parametrize("stop", [None, "error", "agent_completed"])
def test_tl3_a_stop_that_is_neither_is_not_a_turn_limit_under_either_reading(stop):
    bundle = generate(SPEC_D3, SEEDS[0])
    task = export().task_from_bundle(bundle)
    calls = list(bundle.reference_calls)
    assert trace_of(task, bundle, calls, reply=False, stop=stop).is_truncated is False
    assert leaky_of(task, bundle, calls, reply=False, stop=stop) == 0.0


def test_tl4_the_wheel_stamps_max_turns_at_the_cap_and_agent_completed_otherwise():
    """The field the ruling reads, as a live run writes it: a stub that always calls a tool
    under `max_turns = 1` stops for `max_turns`; the reference stops `agent_completed`."""
    bundle = generate(spec_of("depth", 1), SEEDS[0])
    capped = run_one(spec_of("depth", 1), SEEDS[0], [("tool_calls", bundle.reference_calls[0])], agent={"max_turns": 1})
    assert capped.trace.stop_condition == TURN_LIMIT_STOP
    assert capped.trace.is_truncated is True
    assert capped.trace.num_turns == 1 and len(capped.log) == 1
    assert capped.trace.rewards["strict"].score == 0.0
    finished = run_one(spec_of("depth", 1), SEEDS[1])
    assert finished.trace.stop_condition == "agent_completed"
    assert finished.trace.is_truncated is False


# --------------------------------------------------------------------------
# DOC - the export document, layer 1's sentences
# --------------------------------------------------------------------------


def test_doc1_the_docs_name_the_id():
    assert f"`{TASKSET_ID}`" in export_doc()


def test_doc2_the_two_not_yet_paragraphs_are_gone():
    doc = export_doc()
    assert "not yet loadable" not in doc
    assert "until that is settled here" not in doc
