"""An information-spread episode that batches its four named reads into one turn, run live through
the `null` harness and the launched tool server on a fake endpoint, frozen as a test.

The standing decision for a knob that gains tasks: when a run's records are read, the calls that
reached the tool server are replayed and a disagreement is `replay_mismatch`, which scores nothing;
the tool server, `verify` and the run's replay agree, checked on a scripted endpoint.  The design: a
model that batches the four reads in one turn needs four model calls at every level.

Shapes decided here
-------------------

**1. The episode** is `spread:p2`, the level at which two answers carry a part and two read
`none`: the fake endpoint answers the first request with one assistant message holding the four
named reads, in the order the request lists them, then one message per stage call of the
reference, then replies.  The harness hands the calls to the server in order (verifiers 0.3.1's
`null` harness).  The run is the driver's own `run_arm`, one task, one attempt.

**2. Agreement** is three readings of one run: the tool messages the launched server sent are, for
each named read, the payload the reference holds for it, and for each stage call the engine's own
answer, numbered on from the task's `seq_start` (B's, 1); `records_from_run` reads the episode as `passed`, strict and leaky;
`verify` on the same turns gives `passed` with no format clause.  A planted change to any of the six
tool messages is `replay_mismatch`, which a replay check that did not cover spread would read as
`passed`, and which a replay that answered the named reads as the engine does would read for the
unplanted episode too.

**3. Batching is visible**: the record counts four model calls and six tool calls, and the card's
cell built from it carries a mean of four model calls and six tool calls with strict pass@1 of 1,
none stopped short.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import calibration as cal
from poisson_tasks.engine import replay
from poisson_tasks.tasks import FormatSpec, Turn, scenario_for, verify
from tests.helpers import needs_uv, run_module
from tests.k3_support import CARD_SEEDS, SPEC, seq, status
from tests.k8_support import answers, key, listed, payload, spread

SEED = CARD_SEEDS[7]
MODEL = "scripted"


class _Scripted(BaseHTTPRequestHandler):
    """An OpenAI-compatible chat endpoint that plays `script`, one assistant message per step,
    each holding the calls given, then replies."""

    script: list[list[tuple[str, str]]] = []

    def do_POST(self) -> None:  # noqa: N802 - the base class's name
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        step = sum(1 for m in body.get("messages") or [] if m.get("role") == "assistant")
        message: dict[str, Any] = {"role": "assistant", "content": "Done."}
        finish = "stop"
        if step < len(type(self).script):
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call_k8_{step}_{index}",
                        "type": "function",
                        "function": {"name": name, "arguments": arguments},
                    }
                    for index, (name, arguments) in enumerate(type(self).script[step])
                ],
            }
            finish = "tool_calls"
        reply = {
            "id": f"chatcmpl-k8-{step}",
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


def provenance() -> cal.Provenance:
    """A card's provenance for the one scripted model, as the `test_k0_*` card tests write one."""
    seeds = list(range(1000, 1000 + cal.S))
    return cal.Provenance(
        package_version="0.1.0",
        engine_hash="e" * 64,
        generator_hash="g" * 64,
        vocabulary_hash="v" * 64,
        verifiers_version="0.3.1",
        harness_id="null",
        models=[{"id": MODEL, "revision": MODEL, "endpoint_host": "h"}],
        decoding=dict(cal.DECODING),
        seed_list=seeds,
        seed_list_hash=hashlib.sha256(json.dumps(seeds).encode("utf-8")).hexdigest(),
        S=cal.S,
        n=1,
        k_values=[1],
        bootstrap_resamples=200,
        bootstrap_seed=20260922,
        delta_star=0.15,
        saturation_high=0.95,
        saturation_low=0.05,
        instrument_threshold=1.0,
        rate_read_date="2026-09-30",
        serving={MODEL: {"kind": "hosted", "endpoint_host": "h"}},
        budget=dict(cal.DEFAULT_BUDGET),
    )


@needs_uv
def test_p2s_four_reads_in_one_turn_pass_and_the_server_verify_and_the_replay_agree(
    scripted_endpoint: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import verifiers.v1 as vf

    bundle = spread(2, SEED)
    reads = listed(bundle)
    stages = [(str(n), dict(a)) for n, a in bundle.reference_calls if n in SPEC.stage_tools]
    calls = [*reads, *stages]
    assert len(calls) == 6
    _Scripted.script = [[(name, json.dumps(args)) for name, args in reads]] + [
        [(name, json.dumps(args))] for name, args in stages
    ]
    monkeypatch.setenv("K8_KEY", "EMPTY")
    driver = run_module()
    spec = driver.spec_for("spread:p2")
    client = vf.EvalClientConfig(base_url=scripted_endpoint, api_key_var="K8_KEY")
    with driver.design(driver.Design(seeds=(SEED,), n=1, k_values=(1,))):
        outcome = cal.run_arm(spec, output_dir=tmp_path, model=MODEL, client=client)

    sent = tool_messages(outcome.run_dir)
    assert [status(line) for line in sent] == ["ok"] * 6
    assert [seq(line) for line in sent] == [bundle.seq_start + index for index in range(6)]
    found = answers(bundle)
    for read, line in zip(reads, sent, strict=False):
        assert payload(line) == payload(found[key(read)]), line
    _state, engine = replay(scenario_for(SEED, "eval"), calls, bundle.seq_start)
    assert sent[len(reads) :] == engine[len(reads) :]

    (record,) = cal.records_from_run(outcome.run_dir, model=MODEL)
    assert (record.label, record.strict, record.leaky) == ("passed", True, True)
    assert (record.turns, record.sampled_calls) == (4, 6)
    turns = (
        Turn(content="", calls=tuple(reads), finish_reason="tool_calls"),
        *(Turn(content="", calls=(call,), finish_reason="tool_calls") for call in stages),
        Turn(content="Done.", calls=(), finish_reason="stop"),
    )
    verdict = verify(bundle, turns, True, False, FormatSpec(name="reference", markers=()))
    assert (verdict.label, verdict.format_clause) == ("passed", None)

    built = cal.build_artifact({("spread:p2", MODEL): [record]}, provenance())
    (cell,) = built.cells
    assert (cell["model_calls_mean"], cell["tool_calls_mean"]) == (4, 6)
    assert (cell["pass_at_1"], cell["stopped_short_count"]) == (1, 0)

    traces = outcome.run_dir / cal.TRACES_FILE
    original = traces.read_bytes()
    for index in range(len(calls)):
        planted(outcome.run_dir, index)
        (changed,) = cal.records_from_run(outcome.run_dir, model=MODEL)
        assert (changed.label, changed.strict, changed.leaky) == (
            "replay_mismatch",
            False,
            False,
        ), index
        traces.write_bytes(original)
