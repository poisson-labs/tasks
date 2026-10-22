"""A faults episode run live through the `null` harness and the launched tool server, frozen as a
test.

The invariants: a planned failure is
consumed only by a call that reaches the tool server; the harness's forwarding rule is measured
here and pinned; the episode replays, in `verify` and in `records_from_run`'s replay check, to the
observations the server sent; and a planted change to any of them is `replay_mismatch`.

Shapes decided here
-------------------

**1. The harness's rule, as verifiers 0.3.1's `null` harness applies it** (`harnesses/null/
program.py`): a call whose arguments do not parse as JSON, parse to anything but an object, or name
a tool outside the advertised block is answered by the harness with an `error: ...` line and never
reaches the server; a call with empty arguments reaches it as `{}`.  The fake endpoint plays one of
each, the first two against the first stage tool, and the tool messages show which reached the
server: those carry a `seq`.

**2. The episode** is `faults:f2`, whose first call to each right tool is planned to fail: two calls
to the first stage tool the harness refuses, a tool outside the block, a read with empty arguments,
the right first stage call (its planned failure), a read, the right second stage call (its planned
failure) and the same call again (`not_ready`: the first stage never moved), and a reply.  `verify`
gives `malformed_call` (format clause 2 is the lowest that fired, and the episode fell short),
leaky false, and the record says the episode gave up after a fault.  A build that let a refused call
take the first stage's planned failure would answer the right first stage call `ok` and the second
stage's retry `ok`, and the episode would pass.

**3. The episode's design is the driver's**, as `tests/test_k2_server.py`'s: one task, one
attempt, `calibration.run_arm` with the fake endpoint as its client.
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
from tests.helpers import needs_uv, run_module
from tests.k3_support import (
    CARD_SEEDS,
    REFUSED,
    SPEC,
    UNAVAILABLE,
    a_read,
    faults,
    gave_up,
    names,
    right,
    seq,
    status,
)

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
            name, arguments = type(self).script[step]
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call_k3_{step}",
                        "type": "function",
                        "function": {"name": name, "arguments": arguments},
                    }
                ],
            }
            finish = "tool_calls"
        reply = {
            "id": f"chatcmpl-k3-{step}",
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
def test_only_a_call_the_harness_forwards_takes_a_planned_failure_and_the_run_replays(
    scripted_endpoint: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import verifiers.v1 as vf

    bundle = faults(2, SEED)
    (first, first_args), (second, second_args) = right(bundle)
    outside = next(name for name in SPEC.stage_tools if name not in names(bundle))
    read, read_args = a_read(bundle)
    _Scripted.script = [
        (first, "{" + json.dumps(first_args)),
        (first, "[]"),
        (outside, json.dumps(first_args)),
        (read, ""),
        (first, json.dumps(first_args)),
        (read, json.dumps(read_args)),
        (second, json.dumps(second_args)),
        (second, json.dumps(second_args)),
    ]
    monkeypatch.setenv("K3_KEY", "EMPTY")
    driver = run_module()
    spec = driver.spec_for("faults:f2")
    client = vf.EvalClientConfig(base_url=scripted_endpoint, api_key_var="K3_KEY")
    with driver.design(driver.Design(seeds=(SEED,), n=1, k_values=(1,))):
        outcome = cal.run_arm(spec, output_dir=tmp_path, model="scripted", client=client)

    sent = tool_messages(outcome.run_dir)
    assert len(sent) == 8, sent
    assert all(line.startswith(REFUSED) for line in sent[:3]), sent[:3]
    reached = sent[3:]
    assert [status(line) for line in reached] == [
        "bad_args",
        UNAVAILABLE,
        "ok",
        UNAVAILABLE,
        "not_ready",
    ]
    assert [seq(line) for line in reached] == [1, 2, 3, 4, 5]

    (record,) = cal.records_from_run(outcome.run_dir, model="scripted")
    assert (record.label, record.strict, record.leaky) == ("malformed_call", False, False)
    assert gave_up(record) is True

    traces = outcome.run_dir / cal.TRACES_FILE
    original = traces.read_bytes()
    for index in range(3, 8):
        planted(outcome.run_dir, index)
        (changed,) = cal.records_from_run(outcome.run_dir, model="scripted")
        assert (changed.label, changed.strict, changed.leaky) == (
            "replay_mismatch",
            False,
            False,
        ), index
        traces.write_bytes(original)
