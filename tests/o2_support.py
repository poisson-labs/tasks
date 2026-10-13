"""Helpers the O2 test files share: the fixture sets read into the normal form, the flows the
tests declare on the acme set, arms on a user's own tools, the episode builders, and a scripted
model that plays an own-tools task's reference calls.

Every O2 module is reached through `importlib`, so each test file collects on a tree that lacks
one and each test fails there for that one reason.  Test files import this as
`tests.o2_support`, the way `pyproject.toml`'s `pythonpath` lets them.

**The fixture sets** are O1's, unchanged: the acme-support set in its MCP, OpenAI (Chat
Completions), OpenAPI 3.0 and OpenAPI 3.1 shapes, the Swagger Petstore document and the
Everything reference server's `tools/list`.  The OpenAI acme file states no effects (the
format has none), so the tests declare its three reads the way `tasks.toml`'s `read = [...]`
would, through `own.apply_effects`.
"""

from __future__ import annotations

import contextlib
import importlib
import json
import threading
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from poisson_tasks import own
from poisson_tasks.arms import arm_from_id
from poisson_tasks.tasks import FormatSpec, Turn
from tests.o1_support import FIXTURES, fixture

REPO = Path(__file__).resolve().parents[1]
FMT = FormatSpec(name="reference", markers=())

# The letter each knob's arm id writes before its level (`similarity:s2`, `history:t600`).
LETTER = {
    "similarity": "s", "faults": "f", "history": "t", "block": "k",
    "arguments": "a", "spread": "p", "depth": "d", "shape": "w",
}
# The knobs of spec §6.1 that have levels, in the table's order (cost and time has none).
KNOBS = ("similarity", "faults", "history", "block", "arguments", "spread", "depth", "shape")
ACME_READS = ("get_order", "search_orders", "list_channels")


def generator() -> Any:
    return importlib.import_module("poisson_tasks.own.generator")


def simulator() -> Any:
    return importlib.import_module("poisson_tasks.own.simulator")


def verdict() -> Any:
    return importlib.import_module("poisson_tasks.own.verdict")


def recipes() -> Any:
    return importlib.import_module("poisson_tasks.own.recipes")


def export() -> Any:
    return importlib.import_module("poisson_tasks.own.export")


def card() -> Any:
    return importlib.import_module("poisson_tasks.own.card")


def config() -> Any:
    return importlib.import_module("poisson_tasks.config")


def runs() -> Any:
    return importlib.import_module("poisson_tasks.runs")


def calibration() -> Any:
    return importlib.import_module("poisson_tasks.calibration")


# --------------------------------------------------------------------------
# the fixture sets
# --------------------------------------------------------------------------

ACME_FILES = {
    "mcp": "acme-mcp-tools-list.json",
    "openai": "acme-openai-chat.json",
    "openapi-3.0": "acme-openapi-3.0.json",
    "openapi-3.1": "acme-openapi-3.1.yaml",
}


def acme(shape: str = "mcp", name: str = "acme-support") -> own.OwnToolSet:
    """The acme-support set in one of its shapes; the OpenAI shape with its reads declared."""
    toolset = own.read_tools(fixture(ACME_FILES[shape]), name=name).toolset
    if shape == "openai":
        toolset = own.apply_effects(toolset, read=ACME_READS)
    return toolset


def petstore() -> own.OwnToolSet:
    return own.read_tools(fixture("petstore-openapi-3.0.json"), name="petstore").toolset


def everything() -> own.OwnToolSet:
    return own.read_tools(fixture("mcp-everything-tools-list.json"), name="everything").toolset


def fixture_sets() -> dict[str, own.OwnToolSet]:
    """Every fixture set the tests generate on, by a short label."""
    return {
        "acme-mcp": acme("mcp"),
        "acme-openai": acme("openai"),
        "acme-openapi-3.0": acme("openapi-3.0"),
        "acme-openapi-3.1": acme("openapi-3.1"),
        "petstore": petstore(),
        "everything": everything(),
    }


def acme_flows(shape: str = "mcp") -> tuple[Any, ...]:
    """The flows the tests declare on the acme set, as `tasks.toml`'s `[[own.flow]]` would.

    Where the set has output schemas: a `search_orders` result's `orders[].order_id` goes into
    `get_order`, whose `order_id` goes into `refund_order`, a chain of three calls.  The OpenAI
    shape has no output schemas, so each answer holds only `id`: `get_order`'s `id` goes into
    `refund_order`, a chain of two."""
    flow = generator().Flow
    if shape == "openai":
        return (flow("get_order", "id", "refund_order", "order_id"),)
    return (
        flow("search_orders", "orders[].order_id", "get_order", "order_id"),
        flow("get_order", "order_id", "refund_order", "order_id"),
    )


def flows_for(label: str) -> tuple[Any, ...]:
    if label.startswith("acme-openai"):
        return acme_flows("openai")
    if label.startswith("acme"):
        return acme_flows("mcp")
    return ()


# --------------------------------------------------------------------------
# arms and episodes
# --------------------------------------------------------------------------


def arm(knob: str, level: int, *, strictness: str = "strict", split: str = "eval") -> Any:
    """The arm on a user's own tools: the knob's id at `level`, generator `own-1`."""
    return arm_from_id(
        f"{knob}:{LETTER[knob]}{level}", strictness=strictness, split=split,
        generator_version=generator().GENERATOR_VERSION,
    )


def every_arm(toolset: own.OwnToolSet, flows: Sequence[Any] = ()) -> list[Any]:
    """Every arm the set reaches, knob by knob and level by level."""
    out = []
    for knob in KNOBS:
        for level in generator().knob_levels(toolset, knob, flows=flows):
            out.append(arm(knob, level))
    return out


def make(toolset: own.OwnToolSet, knob: str, level: int, seed: int = 7, **kwargs: Any) -> Any:
    flows = kwargs.pop("flows", ())
    return generator().generate(toolset, arm(knob, level, **kwargs), seed, flows=flows)


def turns_of(calls: Sequence[tuple[str, Any]], reply: bool = True) -> tuple[Turn, ...]:
    """One turn per call, then a reply when `reply`."""
    turns = [Turn(content="", calls=(call,), finish_reason="tool_calls") for call in calls]
    if reply:
        turns.append(Turn(content="Done.", calls=(), finish_reason="stop"))
    return tuple(turns)


def judge(bundle: Any, calls: Sequence[tuple[str, Any]], *, reply: bool = True,
          turn_limit: bool = False) -> Any:
    """The own verdict on an episode that made `calls`, one per turn."""
    return verdict().verify(bundle, turns_of(calls, reply), reply, turn_limit, FMT)


def label_of(control: str) -> str:
    """The label a negative control is named for: `malformed_call_clause_3` is `malformed_call`,
    `collateral_mutation_lookalike` is `collateral_mutation`."""
    for label in ("malformed_call", "collateral_mutation", "wrong_state", "turn_limit"):
        if control.startswith(label):
            return label
    raise AssertionError(f"a negative control named for no label: {control}")


def names(bundle: Any) -> list[str]:
    return [str(tool["name"]) for tool in bundle.tools]


def answers(bundle: Any, calls: Sequence[tuple[str, Any]]) -> list[Any]:
    """The simulator's answer to each call, in order, from the task's start."""
    sim = simulator()
    state = sim.start(bundle)
    out = []
    for call in calls:
        state, answer = sim.step(bundle, state, call)
        out.append(answer)
    return out


# --------------------------------------------------------------------------
# a small set built in a test
# --------------------------------------------------------------------------


def write_tool(name: str, properties: Mapping[str, Any], required: Sequence[str] = (),
               *, description: str = "Changes one thing.", output: Any = None) -> dict[str, Any]:
    tool: dict[str, Any] = {
        "name": name, "description": description,
        "inputSchema": {"type": "object", "properties": dict(properties),
                        **({"required": list(required)} if required else {})},
        "annotations": {"readOnlyHint": False},
    }
    if output is not None:
        tool["outputSchema"] = output
    return tool


def read_tool(name: str, properties: Mapping[str, Any], required: Sequence[str] = (),
              *, description: str = "Looks one thing up.", output: Any = None) -> dict[str, Any]:
    tool = write_tool(name, properties, required, description=description, output=output)
    tool["annotations"] = {"readOnlyHint": True}
    return tool


def mcp_set(*tools: dict[str, Any], name: str = "built") -> own.OwnToolSet:
    data = json.dumps({"tools": list(tools)}).encode("utf-8")
    return own.read_tools(data, name=name).toolset


def wide_set(count: int) -> own.OwnToolSet:
    """A set of `count` tools: one write with a checkable argument and `count - 1` reads, each
    under its own name."""
    tools = [write_tool("set_flag", {"flag": {"type": "string", "enum": ["on", "off"]}}, ["flag"])]
    tools += [read_tool(f"look_{index:03d}", {"key": {"type": "string", "maxLength": 12}}, ["key"])
              for index in range(count - 1)]
    return mcp_set(*tools, name=f"wide-{count}")


# --------------------------------------------------------------------------
# a scripted model that plays an own-tools task's reference
# --------------------------------------------------------------------------

CALL_ID_PREFIX = "call_o2_"


@dataclass
class ReferenceModel:
    """An OpenAI-compatible chat endpoint on loopback that plays each registered task's
    reference calls, one per turn, then replies.

    A task is found by its request, the first user message of the conversation; a step is the
    number of assistant messages the model itself made (ids starting `CALL_ID_PREFIX`), so a
    history arm's seeded calls are not counted.  `script` overrides the reference for a request:
    each step is a list of `(name, arguments JSON)` calls made in one assistant message."""

    tasks: dict[str, list[tuple[str, Any]]] = field(default_factory=dict)
    script: dict[str, list[list[tuple[str, str]]]] = field(default_factory=dict)
    base_url: str = ""
    requests: list[dict[str, Any]] = field(default_factory=list)

    def register(self, bundle: Any) -> None:
        self.tasks[str(bundle.request)] = [(str(n), a) for n, a in bundle.reference_calls]

    def steps(self, request: str) -> list[list[tuple[str, str]]]:
        if request in self.script:
            return self.script[request]
        return [[(name, json.dumps(args))] for name, args in self.tasks[request]]


@contextlib.contextmanager
def reference_model() -> Iterator[ReferenceModel]:
    model = ReferenceModel()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - the base class's name
            body = json.dumps({"object": "list", "data": [{"id": "scripted", "object": "model"}]})
            self._send(body.encode())

        def do_POST(self) -> None:  # noqa: N802 - the base class's name
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            model.requests.append(body)
            messages = body.get("messages") or []
            request = next(str(m.get("content")) for m in messages if m.get("role") == "user")
            made = sum(
                1 for m in messages if m.get("role") == "assistant"
                and any(str(c.get("id", "")).startswith(CALL_ID_PREFIX)
                        for c in m.get("tool_calls") or [])
            )
            steps = model.steps(request)
            message: dict[str, Any] = {"role": "assistant", "content": "Done."}
            finish = "stop"
            if made < len(steps):
                message = {"role": "assistant", "content": None, "tool_calls": [
                    {"id": f"{CALL_ID_PREFIX}{made}_{index}", "type": "function",
                     "function": {"name": name, "arguments": arguments}}
                    for index, (name, arguments) in enumerate(steps[made])
                ]}
                finish = "tool_calls"
            reply = {
                "id": f"chatcmpl-o2-{made}", "object": "chat.completion", "created": 0,
                "model": body.get("model"),
                "choices": [{"index": 0, "finish_reason": finish, "message": message}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 5, "total_tokens": 105},
            }
            self._send(json.dumps(reply).encode())

        def _send(self, data: bytes) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args: Any) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    model.base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    try:
        yield model
    finally:
        server.shutdown()
        server.server_close()


def copy_fixture(name: str, folder: Path, as_name: str | None = None) -> Path:
    target = folder / (as_name or name)
    target.write_bytes((FIXTURES / name).read_bytes())
    return target
