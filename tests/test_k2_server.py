"""The similarity knob on the export path: the tool server, a live episode, and the replay check,
frozen as tests.

The tool server advertises the
bundle's block byte for byte (X3) and applies a call by its shown name to the engine tool that name
stands for.  An episode driven by a fake model endpoint through the real `null` harness and the
launched tool server replays, in `verify`, to the observations the server sent; and
`records_from_run` compares the two for a similarity arm, labelling a disagreement
`replay_mismatch`, an instrument failure.

Shapes decided here
-------------------

**1. The replay check's rule is the adapter's A8** (`tests/test_tg_m5_bridge.py`, shape 1): every
sampled call whose tool message is not the harness's own `error: ...` line reached the server;
those calls, translated through the display map, are replayed through the engine, and each
observation must equal its tool message byte for byte.  A call the harness refused (here, a call by
an engine name the knob hides) is not replayed.

**2. A `replay_mismatch` record is scored as nothing**: strict and leaky both false, as every
instrument label's record is (`EpisodeRecord` refuses a leaky instrument record).

**3. Which arms the check runs on.**  The design names faults and similarity.  This file pins it for
similarity; whether depth and distractor arms are checked too is left to the build, since on a
genuine run the check finds nothing there either.

**4. The episode.**  One similarity task at `s3`, one attempt, through `calibration.run_arm` with
the fake endpoint as its client.  The fake plays the first right call, the first-stage lookalike in
the lowest slot, a first-stage lookalike by its hidden engine name, the second right call, and a
reply: so the server applies a lookalike, the harness refuses a hidden name, and the chain still
completes.  The verdict is `malformed_call` (the hidden name is outside the block, format clause 3,
and the lookalike's side effect keeps the episode short of `passed`), with leaky passing.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP

from poisson_tasks import calibration as cal
from poisson_tasks import export
from poisson_tasks.engine import replay
from poisson_tasks.tasks import scenario_for
from tests.helpers import needs_uv, run_module
from tests.k2_support import CARD_SEEDS, engines, lookalike_slots, names, sim, stage_of

SEED = CARD_SEEDS[11]


def run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


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


def engine_replay(bundle: Any, calls: list[tuple[str, Any]]) -> list[str]:
    """What the engine answers to `calls`, each under the engine name its shown name stands for."""
    behind = dict(zip(names(bundle), engines(bundle), strict=True))
    _state, observations = replay(
        scenario_for(bundle.seed, bundle.split),
        [(behind[name], args) for name, args in calls], bundle.seq_start)
    return list(observations)


def first_lookalikes(bundle: Any) -> list[tuple[str, str]]:
    behind = engines(bundle)
    return [(names(bundle)[s], behind[s]) for s in lookalike_slots(bundle)
            if stage_of(behind[s]) == 0]


@pytest.mark.parametrize("level", [0, 3])
def test_the_server_advertises_the_shown_block_and_applies_each_name_to_its_engine_tool(
    level: int,
) -> None:
    """X3 on similarity: names in slot order, descriptions and parameter schemas are the bundle's
    exactly, and no hidden engine name is advertised.  The reference calls by their shown names
    answer the reference observations; a lookalike by its shown name answers what its engine
    tool answers."""
    bundle = sim(level, SEED)
    mcp = started(bundle)
    listed = run(mcp.list_tools())
    assert [t.name for t in listed] == list(names(bundle))
    assert [t.description for t in listed] == [t["description"] for t in bundle.tools]
    assert [t.inputSchema for t in listed] == [t["parameters"] for t in bundle.tools]
    ref = list(bundle.reference_calls)
    assert [call(mcp, name, args) for name, args in ref] == list(bundle.reference_observations)
    shown, _engine = first_lookalikes(bundle)[0]
    calls = ref + [(shown, dict(ref[0][1]))]
    assert call(mcp, shown, dict(ref[0][1])) == engine_replay(bundle, calls)[-1]
    assert engine_replay(bundle, calls)[-1].split()[1] == "ok"


# --------------------------------------------------------------------------
# a live episode, and the replay check
# --------------------------------------------------------------------------


class _Scripted(BaseHTTPRequestHandler):
    """An OpenAI-compatible chat endpoint that plays `script`, one call per turn, then replies."""

    script: list[tuple[str, dict[str, Any]]] = []

    def do_POST(self) -> None:  # noqa: N802 - the base class's name
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        step = sum(1 for m in body.get("messages") or [] if m.get("role") == "assistant")
        message: dict[str, Any] = {"role": "assistant", "content": "Done."}
        finish = "stop"
        if step < len(type(self).script):
            name, arguments = type(self).script[step]
            message = {"role": "assistant", "content": None, "tool_calls": [{
                "id": f"call_k2_{step}", "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)}}]}
            finish = "tool_calls"
        reply = {"id": f"chatcmpl-k2-{step}", "object": "chat.completion", "created": 0,
                 "model": body.get("model"),
                 "choices": [{"index": 0, "finish_reason": finish, "message": message}],
                 "usage": {"prompt_tokens": 100, "completion_tokens": 5, "total_tokens": 105}}
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: Any) -> None:
        return None


@pytest.fixture
def scripted_endpoint() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Scripted)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    server.shutdown()
    server.server_close()


def tool_messages(run_dir: Path) -> list[str]:
    import verifiers.v1 as vf
    from verifiers.v1.cli.output import read_episodes

    (episode,) = read_episodes(run_dir, vf.Trace)
    return [str(node.message.content) for node in episode.traces[0].nodes
            if isinstance(node.message, vf.ToolMessage)]


def planted(run_dir: Path, index: int) -> None:
    """The `index`-th tool message of the one episode, its last character changed."""
    path = run_dir / cal.TRACES_FILE
    (line,) = path.read_text(encoding="utf-8").splitlines()
    row = json.loads(line)
    seen = 0
    for trace in row["traces"]:
        for node in trace["nodes"]:
            message = node.get("message") or {}
            if message.get("role") == "tool":
                if seen == index:
                    text = message["content"]
                    message["content"] = text[:-1] + ("0" if text[-1] != "0" else "1")
                seen += 1
    assert seen > index
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


@needs_uv
def test_a_live_episode_replays_to_what_the_server_sent_and_a_planted_change_is_caught(
    scripted_endpoint: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import verifiers.v1 as vf

    bundle = sim(3, SEED)
    ref = list(bundle.reference_calls)
    (lowest, _engine), (_shown, hidden) = first_lookalikes(bundle)[:2]
    _Scripted.script = [ref[0], (lowest, dict(ref[0][1])), (hidden, dict(ref[0][1])), ref[1]]
    monkeypatch.setenv("K2_KEY", "EMPTY")
    driver = run_module()
    spec = driver.spec_for("similarity:s3")
    client = vf.EvalClientConfig(base_url=scripted_endpoint, api_key_var="K2_KEY")
    with driver.design(driver.Design(seeds=(SEED,), n=1, k_values=(1,))):
        outcome = cal.run_arm(spec, output_dir=tmp_path, model="scripted", client=client)

    sent = tool_messages(outcome.run_dir)
    assert len(sent) == 4, sent
    assert sent[2].startswith("error: ") and hidden in sent[2], sent[2]
    reached = [ref[0], (lowest, dict(ref[0][1])), ref[1]]
    assert [sent[0], sent[1], sent[3]] == engine_replay(bundle, reached)

    (record,) = cal.records_from_run(outcome.run_dir, model="scripted")
    assert (record.label, record.strict, record.leaky) == ("malformed_call", False, True)

    traces = outcome.run_dir / cal.TRACES_FILE
    original = traces.read_bytes()
    for index in (0, 1, 3):
        planted(outcome.run_dir, index)
        (changed,) = cal.records_from_run(outcome.run_dir, model="scripted")
        assert (changed.label, changed.strict, changed.leaky) == (
            "replay_mismatch", False, False), index
        traces.write_bytes(original)
