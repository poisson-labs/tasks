"""An arguments episode run live through the `null` harness and the launched tool server, on a fake
endpoint, frozen as a test.

The argument check answers a missing,
wrong or invented value `bad_args` in the engine's layout, changes nothing and advances the counter,
and `verify`, the tool server and the reference agree, by replay on a fake endpoint.

Shapes decided here
-------------------

**1. The episode** is `arguments:a6`, whose request states four of the six values: the first stage
call with a stated value missing, the first stage call with a value in a parameter the request did
not state (invented), the right first stage call, the second stage call with a
stated value in another case, the right second stage call, and a reply.  The fake endpoint plays it
one call per turn, as `tests/test_k3_live.py`'s does, through the driver's own `run_arm`.

**2. Agreement** is three readings of one run: the tool messages the launched server sent are the
lines the engine gives for the right calls with only its two arguments and for each bad call as a
call it refuses itself, numbered 1 to 5 with no gap; `records_from_run` reads the episode as
`passed`, strict and leaky, which it does only when its replay of the calls agrees with every tool
message and `verify`'s verdict agrees with the recorded reward; and `verify` on the same calls
gives `passed` with no format clause.  A planted change to any of the five tool messages is
`replay_mismatch`.

**3. This is also The standing decision for a knob that gains tasks**: when a run's records are
read, the calls that reached the tool server are replayed against the engine and a disagreement is
`replay_mismatch`, which scores nothing.  For this knob the server answers in front of the engine,
so the replay must apply the same check, or it disagrees with the clean run above; and a replay
check that did not cover the knob would read the planted runs as `passed`.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import calibration as cal
from poisson_tasks.engine import replay
from poisson_tasks.tasks import scenario_for
from tests.helpers import needs_uv, run_module
from tests.k3_support import CARD_SEEDS, seq, status, verdict_of
from tests.k6_support import arguments, more, other_case, stage_tools, stated, stripped

SEED = CARD_SEEDS[7]


class _Scripted(BaseHTTPRequestHandler):
    """An OpenAI-compatible chat endpoint that plays `script`, one call per turn, each call's
    arguments as the raw string given, then replies."""

    script: list[tuple[str, str]] = []

    def do_POST(self) -> None:  # noqa: N802 - the base class's name
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        step = sum(1 for m in body.get("messages") or [] if m.get("role") == "assistant")
        message: dict[str, Any] = {"role": "assistant", "content": "Done."}
        finish = "stop"
        if step < len(type(self).script):
            name, arguments_ = type(self).script[step]
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call_k6_{step}",
                        "type": "function",
                        "function": {"name": name, "arguments": arguments_},
                    }
                ],
            }
            finish = "tool_calls"
        reply = {
            "id": f"chatcmpl-k6-{step}",
            "object": "chat.completion",
            "created": 0,
            "model": body.get("model"),
            "choices": [{"index": 0, "finish_reason": finish, "message": message}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 5, "total_tokens": 105},
        }
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
    return [
        str(node.message.content)
        for node in episode.traces[0].nodes
        if isinstance(node.message, vf.ToolMessage)
    ]


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
def test_the_server_verify_and_the_replay_agree_on_a_run_with_bad_calls(
    scripted_endpoint: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import verifiers.v1 as vf

    bundle = arguments(6, SEED)
    (first, first_args), (second, second_args) = (
        (str(name), dict(args)) for name, args in bundle.reference_calls
    )
    values = stated(bundle)
    keys = list(values)
    assert len(keys) == 4
    unstated = [k for k in more(stage_tools(bundle)[0]) if k not in values]
    calls: list[tuple[str, Any]] = [
        (first, {k: v for k, v in first_args.items() if k != keys[-1]}),
        (first, {**first_args, unstated[0]: "harbor"}),
        (first, first_args),
        (second, {**second_args, keys[0]: other_case(values[keys[0]])}),
        (second, second_args),
    ]
    _Scripted.script = [(name, json.dumps(args)) for name, args in calls]
    monkeypatch.setenv("K6_KEY", "EMPTY")
    driver = run_module()
    spec = driver.spec_for("arguments:a6")
    client = vf.EvalClientConfig(base_url=scripted_endpoint, api_key_var="K6_KEY")
    with driver.design(driver.Design(seeds=(SEED,), n=1, k_values=(1,))):
        outcome = cal.run_arm(spec, output_dir=tmp_path, model="scripted", client=client)

    sent = tool_messages(outcome.run_dir)
    assert [status(line) for line in sent] == ["bad_args", "bad_args", "ok", "bad_args", "ok"]
    assert [seq(line) for line in sent] == [1, 2, 3, 4, 5]
    engine_calls = [(first, {}), (first, {}), stripped(calls[2]), (second, {}), stripped(calls[4])]
    _state, expected = replay(scenario_for(SEED, "eval"), engine_calls, bundle.seq_start)
    assert sent == expected

    (record,) = cal.records_from_run(outcome.run_dir, model="scripted")
    assert (record.label, record.strict, record.leaky) == ("passed", True, True)
    verdict = verdict_of(bundle, calls)
    assert (verdict.label, verdict.format_clause) == ("passed", None)

    traces = outcome.run_dir / cal.TRACES_FILE
    original = traces.read_bytes()
    for index in range(len(calls)):
        planted(outcome.run_dir, index)
        (changed,) = cal.records_from_run(outcome.run_dir, model="scripted")
        assert (changed.label, changed.strict, changed.leaky) == (
            "replay_mismatch",
            False,
            False,
        ), index
        traces.write_bytes(original)
